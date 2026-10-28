import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.db.base import utcnow
from app.db.models import MealPlan, User
from app.llm.base import LLMClient, generate_validated, untrusted
from app.llm.ollama import get_llm
from app.schemas.meal_plans import DayData, MealData, MealPlanRequest
from app.services import nutrition, restrictions, safety

log = logging.getLogger("foodverse.mealplans")

SYSTEM = (
    "You are a meal-planning assistant for healthy home cooking. Return meals as JSON matching the schema. "
    "Each meal needs a realistic ingredient list with gram weights for ONE serving, and a one-sentence rationale. "
    "Do not give medical or disease-specific dietary advice."
)


def _meal_violations(meal: MealData, rules: dict) -> list[dict]:
    return safety.find_violations([i.name for i in meal.ingredients] + [meal.title], rules["terms"])


def _context(req: MealPlanRequest, rules: dict) -> str:
    lines = [restrictions.prompt_text(rules), f"Servings per meal: {req.servings}"]
    if req.cuisines:
        lines.append("Preferred cuisines: " + ", ".join(req.cuisines))
    if req.target_kcal_per_day:
        lines.append(f"Aim for about {req.target_kcal_per_day} kcal per day in total (user-set goal).")
    if req.available_ingredients:
        lines.append("Ingredients already available (prefer them): " + ", ".join(req.available_ingredients))
    if req.budget:
        lines.append("Budget: " + req.budget)
    if req.max_cooking_minutes:
        lines.append(f"Each meal should take at most {req.max_cooking_minutes} minutes to prepare.")
    return "\n".join(lines)


def _finish_meal(db: Session, meal: MealData, meal_type: str, servings: int) -> dict:
    est = nutrition.estimate_ingredients(db, [i.model_dump() for i in meal.ingredients])
    d = meal.model_dump()
    d["meal_type"] = meal_type
    d["servings"] = servings
    d["nutrition_estimate"] = {**est, "per": "one serving"}
    d["origin"] = "ai_generated"
    return d


def _single_meal(llm: LLMClient, ctx: str, meal_type: str, avoid: list[str], rules: dict, extra: str = "") -> MealData:
    prompt = f"{ctx}\nCreate ONE {meal_type}."
    if avoid:
        prompt += " Do not repeat these meals: " + "; ".join(avoid[-12:]) + "."
    if extra:
        prompt += "\nUser instruction: " + untrusted("instruction", extra, 300)
    for _ in range(get_settings().llm_max_retries + 1):
        meal = generate_validated(llm, MealData, SYSTEM, prompt)
        bad = _meal_violations(meal, rules)
        if not bad:
            meal.meal_type = meal_type
            return meal
        prompt += "\nYour last attempt contained forbidden ingredients: " + ", ".join(sorted({b["ingredient"] for b in bad})) + ". Choose a different meal."
    raise AppError(f"Could not create a {meal_type} that respects your restrictions", code="restriction_violation", status_code=422)


def build(db: Session, user: User, req: MealPlanRequest, llm: LLMClient | None = None) -> tuple[dict, list[str]]:
    llm = llm or get_llm()
    rules = restrictions.resolve(user, allergies=req.allergies, excluded=req.excluded_ingredients, diet=req.diet_pattern, use_profile=req.use_profile)
    ctx = _context(req, rules)
    days, titles = [], []
    for d in range(1, req.days + 1):
        got: dict[str, MealData] = {}
        try:  # one call per day is cheaper on CPU; fall back to per-meal calls for anything missing or invalid
            day = generate_validated(llm, DayData, SYSTEM, f"{ctx}\nCreate day {d} with these meals, one each: {', '.join(req.meals)}. "
                                     + ("Do not repeat: " + "; ".join(titles[-12:]) if titles else ""), retries=1)
            for m in day.meals:
                mt = m.meal_type if m.meal_type in req.meals else None
                if mt and mt not in got and not _meal_violations(m, rules):
                    m.meal_type = mt
                    got[mt] = m
        except AppError as exc:
            if exc.code not in ("llm_bad_response",):
                raise
        for mt in req.meals:
            if mt not in got:
                got[mt] = _single_meal(llm, ctx, mt, titles, rules)
        meals = [_finish_meal(db, got[mt], mt, req.servings) for mt in req.meals]
        titles += [m["title"] for m in meals]
        days.append({"day": d, "meals": meals, "daily_nutrition": _daily(meals)})
    plan = {"days": days, "restrictions_applied": rules["reasons"], "caveat": safety.ALLERGEN_CAVEAT,
            "notes": ["All meals are AI-generated suggestions, not medical or clinical nutrition advice.",
                      "Nutrition figures cover only ingredients matched in the nutrition database; see each meal's coverage."]}
    if req.target_kcal_per_day:
        plan["target_kcal_per_day"] = req.target_kcal_per_day
    return plan, rules["reasons"]


def _daily(meals: list[dict]) -> dict:
    kcal, complete = 0.0, True
    for m in meals:
        est = m["nutrition_estimate"]
        if est["totals"]["kcal"] is None or not est["complete"]:
            complete = False
        kcal += est["totals"]["kcal"] or 0
    return {"kcal_matched": round(kcal, 0), "complete": complete,
            "note": "Estimated from database-matched ingredients." + ("" if complete else " Some ingredients were not found, so this is a lower bound.")}


def validate_plan(plan: dict, rules_terms: dict) -> list[dict]:
    """Final gate before a plan is shown as ready."""
    out = []
    for day in plan["days"]:
        for m in day["meals"]:
            for v in safety.find_violations([i["name"] for i in m["ingredients"]] + [m["title"]], rules_terms):
                out.append({**v, "day": day["day"], "meal_type": m["meal_type"]})
    return out


def run_generation(session_factory, plan_id: str, llm: LLMClient | None = None) -> None:
    """Background task: fills the plan row, never leaves it stuck in 'generating'."""
    with session_factory() as db:
        mp = db.get(MealPlan, plan_id)
        if not mp:
            return
        try:
            user = db.get(User, mp.user_id)
            req = MealPlanRequest.model_validate(mp.params)
            plan, _ = build(db, user, req, llm)
            rules = restrictions.resolve(user, allergies=req.allergies, excluded=req.excluded_ingredients, diet=req.diet_pattern, use_profile=req.use_profile)
            problems = validate_plan(plan, rules["terms"])
            if problems:
                raise AppError("Generated plan violated your restrictions and was rejected", code="restriction_violation", details=problems)
            mp.plan, mp.status, mp.error = plan, "ready", None
        except AppError as exc:
            mp.status, mp.error = "failed", exc.message
        except Exception:  # noqa: BLE001 - record and surface, never swallow
            log.exception("meal plan generation crashed")
            mp.status, mp.error = "failed", "Unexpected error while generating the plan"
        mp.updated_at = utcnow()
        db.commit()


def create(db: Session, user: User, req: MealPlanRequest) -> MealPlan:
    mp = MealPlan(user_id=user.id, params=req.model_dump(), status="generating", plan={})
    db.add(mp)
    db.flush()
    return mp


def get_owned(db: Session, user: User, plan_id: str) -> MealPlan:
    mp = db.get(MealPlan, plan_id)
    if not mp or mp.user_id != user.id:
        raise NotFound("Meal plan not found")
    return mp


def replace_slot(db: Session, user: User, mp: MealPlan, day: int, meal_type: str, instruction: str | None, llm: LLMClient | None = None) -> MealPlan:
    if mp.status != "ready":
        raise Conflict("The plan is not ready yet")
    llm = llm or get_llm()
    req = MealPlanRequest.model_validate(mp.params)
    rules = restrictions.resolve(user, allergies=req.allergies, excluded=req.excluded_ingredients, diet=req.diet_pattern, use_profile=req.use_profile)
    plan = {**mp.plan, "days": [dict(d) for d in mp.plan["days"]]}
    target = next((d for d in plan["days"] if d["day"] == day), None)
    if not target or not any(m["meal_type"] == meal_type for m in target["meals"]):
        raise NotFound("That day/meal is not in this plan")
    titles = [m["title"] for d in plan["days"] for m in d["meals"]]
    meal = _single_meal(llm, _context(req, rules), meal_type, titles, rules, instruction or "")
    target["meals"] = [_finish_meal(db, meal, meal_type, req.servings) if m["meal_type"] == meal_type else m for m in target["meals"]]
    target["daily_nutrition"] = _daily(target["meals"])
    mp.plan, mp.shopping_list = plan, None  # list is stale after a change
    mp.updated_at = utcnow()
    return mp


def add_feedback(mp: MealPlan, fb: dict) -> MealPlan:
    mp.feedback = [*(mp.feedback or []), {**fb, "at": utcnow().isoformat()}]
    return mp


def shopping_list(mp: MealPlan) -> list[dict]:
    if mp.status != "ready":
        raise Conflict("The plan is not ready yet")
    have = {safety.normalize(i) for i in (mp.params.get("available_ingredients") or [])}
    servings = mp.params.get("servings", 1)
    agg: dict[str, dict] = defaultdict(lambda: {"total_grams": 0.0, "used_in": []})
    for day in mp.plan["days"]:
        for m in day["meals"]:
            for ing in m["ingredients"]:
                key = safety.normalize(ing["name"])
                row = agg[key]
                row["name"] = row.get("name") or ing["name"]
                row["total_grams"] += ing["grams"] * servings
                row["used_in"].append(f"day {day['day']} {m['meal_type']}")
    items = [{"name": r["name"], "total_grams": round(r["total_grams"], 1), "used_in": r["used_in"], "have_at_home": key in have}
             for key, r in sorted(agg.items())]
    return items
