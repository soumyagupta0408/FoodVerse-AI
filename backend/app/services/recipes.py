import copy
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound, ValidationFailed
from app.db.models import Recipe, User
from app.llm.base import LLMClient, generate_validated, untrusted
from app.llm.ollama import get_llm
from app.schemas.recipes import RecipeData, RecipeRequest, SubstitutionOut
from app.services import nutrition, restrictions, safety

log = logging.getLogger("foodverse.recipes")

SYSTEM = (
    "You are a careful cooking assistant. Produce one practical home recipe as JSON matching the schema. "
    "Give every ingredient an approximate weight in grams in `grams`. Steps must be short, numbered by order, and include "
    "safe-cooking temperatures for meat, poultry, fish and eggs. Only use equipment the user listed if they listed any."
)


def _all_text(data: RecipeData) -> list[str]:
    return [i.name for i in data.ingredients] + data.steps + [data.title]


def check(data: RecipeData, rules: dict) -> list[dict]:
    return safety.find_violations(_all_text(data), rules["terms"])


def _build_prompt(req: RecipeRequest, rules: dict, previous: RecipeData | None) -> str:
    lines = [f"Servings: {req.servings}", restrictions.prompt_text(rules)]
    if req.ingredients:
        lines.append("Ingredients on hand (use mostly these; staples like salt, oil, water are fine): " + ", ".join(req.ingredients))
    for label, value in (("Cuisine", req.cuisine), ("Meal type", req.meal_type), ("Max total cooking time (min)", req.cooking_minutes),
                         ("Skill level", req.skill_level), ("Budget", req.budget), ("Nutrition goal", req.nutrition_goal)):
        if value:
            lines.append(f"{label}: {value}")
    if req.equipment:
        lines.append("Equipment available: " + ", ".join(req.equipment))
    prompt = "\n".join(lines)
    if req.dietary_notes:
        prompt += "\n" + untrusted("dietary_notes", req.dietary_notes, 300)
    if previous is not None:
        prompt += "\nModify this existing recipe instead of starting over:\n" + untrusted("previous_recipe", previous.model_dump_json(), 6000)
    if req.request:
        prompt += "\nUser request: " + untrusted("request", req.request, 500)
    return prompt


def generate(db: Session, user: User, req: RecipeRequest, *, previous: RecipeData | None = None, llm: LLMClient | None = None, parent_id: str | None = None) -> Recipe:
    llm = llm or get_llm()
    rules = restrictions.resolve(user, allergies=req.allergies, excluded=req.excluded_ingredients, diet=req.diet_pattern, use_profile=req.use_profile)
    prompt = _build_prompt(req, rules, previous)
    violations: list[dict] = []
    data = None
    for _attempt in range(get_settings().llm_max_retries + 1):
        data = generate_validated(llm, RecipeData, SYSTEM, prompt)
        violations = check(data, rules)
        if not violations:
            break
        bad = ", ".join(sorted({v["ingredient"] for v in violations}))
        prompt += f"\n\nYour last recipe broke the restrictions with: {bad}. Write a new recipe without them or any ingredient derived from them."
    if violations:
        log.warning("recipe rejected: restriction violations %s", violations)
        raise ValidationFailed("A safe recipe that respects your restrictions could not be produced. Nothing was saved: try different ingredients.",
                               code="restriction_violation", details=violations)
    return _persist(db, user, data, rules, llm.name, saved=req.save, parent_id=parent_id)


def _enrich(db: Session, data: RecipeData, rules: dict) -> dict:
    est = nutrition.estimate_ingredients(db, [i.model_dump() for i in data.ingredients])
    return {
        "restriction_check": {"applied": rules["reasons"], "violations": [], "caveat": safety.ALLERGEN_CAVEAT},
        "nutrition_estimate": {**est, "basis": "database-matched ingredients; per whole recipe", "servings": data.servings},
        "provenance": {"generated_by_llm": ["title", "description", "ingredients", "quantities", "steps", "tips", "food_safety", "substitutions"],
                       "database_verified": ["nutrition_estimate (only for matched ingredients)"],
                       "note": "Recipe text is AI-generated and not tested in a kitchen. Ingredient weights are the model's estimates."},
    }


def _persist(db: Session, user: User, data: RecipeData, rules: dict, model_name: str, *, saved: bool, parent_id: str | None) -> Recipe:
    payload = data.model_dump()
    payload["_meta"] = _enrich(db, data, rules)
    payload["_meta"]["restrictions"] = {"allergies": rules["allergies"], "excluded": rules["excluded"], "diet": rules["diet"]}
    r = Recipe(user_id=user.id, title=data.title, data=payload, saved=saved, model_name=model_name, parent_id=parent_id,
               ingredient_names=[safety.normalize(i.name) for i in data.ingredients])
    db.add(r)
    db.flush()
    return r


def get_owned(db: Session, user: User, recipe_id: str) -> Recipe:
    r = db.get(Recipe, recipe_id)
    if not r or r.user_id != user.id:
        raise NotFound("Recipe not found")
    return r


def to_out(r: Recipe) -> dict:
    data = dict(r.data)
    meta = data.pop("_meta", {})
    return {"id": r.id, "title": r.title, "data": data, "saved": r.saved, "parent_id": r.parent_id, "model_name": r.model_name,
            "created_at": r.created_at, "meta": meta}


def _rules_from_recipe(user: User, r: Recipe) -> dict:
    stored = (r.data.get("_meta") or {}).get("restrictions") or {}
    return restrictions.resolve(user, allergies=stored.get("allergies", []), excluded=stored.get("excluded", []), diet=stored.get("diet"), use_profile=True)


def scale(db: Session, user: User, recipe_id: str, servings: int) -> Recipe:
    src = get_owned(db, user, recipe_id)
    data = RecipeData.model_validate({k: v for k, v in src.data.items() if k != "_meta"})
    factor = servings / data.servings
    scaled = copy.deepcopy(data)
    for ing in scaled.ingredients:
        if ing.quantity is not None:
            ing.quantity = round(ing.quantity * factor, 2)
        if ing.grams is not None:
            ing.grams = min(round(ing.grams * factor, 1), 5000)
    scaled.servings = servings
    scaled.tips = [*scaled.tips, f"Scaled from {data.servings} to {servings} servings. Cooking times may need adjusting for larger or smaller batches."]
    return _persist(db, user, scaled, _rules_from_recipe(user, src), src.model_name or "scaled", saved=False, parent_id=src.id)


def substitute(db: Session, user: User, recipe_id: str, ingredient: str, replacement: str | None, reason: str | None, llm: LLMClient | None = None) -> dict:
    src = get_owned(db, user, recipe_id)
    data = RecipeData.model_validate({k: v for k, v in src.data.items() if k != "_meta"})
    target = safety.normalize(ingredient)
    idx = next((i for i, ing in enumerate(data.ingredients) if safety.normalize(ing.name) == target), None)
    if idx is None:
        raise ValidationFailed(f"'{ingredient}' is not an ingredient of this recipe")
    rules = _rules_from_recipe(user, src)
    if replacement:
        if safety.find_violations([replacement], rules["terms"]):
            raise ValidationFailed(f"'{replacement}' conflicts with your dietary restrictions", code="restriction_violation")
        new = copy.deepcopy(data)
        new.ingredients[idx].name = replacement
        new.steps = [s.replace(data.ingredients[idx].name, replacement) for s in new.steps]
        if check(new, rules):
            raise ValidationFailed("The substituted recipe conflicts with your dietary restrictions", code="restriction_violation")
        return {"applied": True, "recipe": to_out(_persist(db, user, new, rules, src.model_name or "manual", saved=False, parent_id=src.id))}
    llm = llm or get_llm()
    prompt = (f"Recipe: {data.title}\nIngredient to replace: {data.ingredients[idx].name}\n{restrictions.prompt_text(rules)}\n"
              + (untrusted("reason", reason, 200) if reason else "") + "\nSuggest 2-4 realistic substitutes that work in this recipe.")
    out = generate_validated(llm, SubstitutionOut, "You suggest ingredient substitutions for home cooking.", prompt)
    safe = [a for a in out.alternatives if not safety.find_violations([a.name], rules["terms"])]
    if not safe:
        raise ValidationFailed("No substitute that respects your restrictions could be found", code="restriction_violation")
    return {"applied": False, "ingredient": data.ingredients[idx].name, "alternatives": [a.model_dump() for a in safe],
            "removed_for_restrictions": len(out.alternatives) - len(safe), "note": "AI-suggested: taste and texture may differ."}


def search(db: Session, user: User, ingredients: list[str], saved_only: bool, limit: int) -> list[dict]:
    wanted = {safety.normalize(i) for i in ingredients if i.strip()}
    q = select(Recipe).where(Recipe.user_id == user.id)
    if saved_only:
        q = q.where(Recipe.saved.is_(True))
    scored = []
    for r in db.scalars(q).all():
        names = " | ".join(r.ingredient_names or [])
        hits = sorted(w for w in wanted if w and w in names)
        if hits:
            scored.append({"score": round(len(hits) / len(wanted), 3), "matched": hits, "missing_from_query": len(r.ingredient_names or []) - len(hits), "recipe": to_out(r)})
    scored.sort(key=lambda s: (-s["score"], s["missing_from_query"]))
    return scored[:limit]
