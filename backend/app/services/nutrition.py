"""Nutrition lookup and calculation. All maths here is deterministic application code.

Source records are per-100 g. Values are converted to the requested portion; unknown nutrients
stay None (never zero-filled).
"""
import difflib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NutritionFood
from app.services.safety import normalize

NUTRIENTS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")

HEALTH_SCORE_CRITERIA = (
    "Simple transparent heuristic on per-100 g values, starting at 50 and clamped to 0-100. "
    "Energy density: <=100 kcal +15, <=200 +5, <=300 -5, >300 -15. Protein: >=10 g +10, >=5 g +5. "
    "Fibre: >=3 g +10, >=1.5 g +5. Sugar: >=15 g -10, >=8 g -5. Total fat: >=20 g -10, >=10 g -5. "
    "Criteria whose input is unknown are skipped and listed. It is a rough guide, not medical advice."
)

# Approximate per-100 g values from general nutrition knowledge, for demo mode ONLY.
# None = not recorded (unknown), which is deliberately different from 0.
DEMO_FOODS = [
    # name, kcal, protein, carbs, fat, fiber, sugar, serving_g, serving_desc
    ("banana", 89, 1.1, 22.8, 0.3, 2.6, 12.2, 118, "1 medium"),
    ("apple", 52, 0.3, 13.8, 0.2, 2.4, 10.4, 182, "1 medium"),
    ("orange", 47, 0.9, 11.8, 0.1, 2.4, 9.4, 131, "1 medium"),
    ("white rice cooked", 130, 2.7, 28.2, 0.3, 0.4, 0.1, 158, "1 cup"),
    ("fried rice", 163, 4.1, 24.0, 5.5, None, None, 198, "1 cup"),
    ("boiled egg", 155, 12.6, 1.1, 10.6, 0.0, 1.1, 50, "1 large"),
    ("chicken breast cooked", 165, 31.0, 0.0, 3.6, 0.0, 0.0, 120, "1 small breast"),
    ("pizza", 266, 11.0, 33.0, 10.0, 2.3, 3.6, 107, "1 slice"),
    ("french fries", 312, 3.4, 41.0, 15.0, 3.8, None, 117, "1 medium serving"),
    ("spaghetti bolognese", 140, 7.0, 16.0, 5.0, None, None, 250, "1 plate"),
    ("hamburger", 250, 13.0, 24.0, 11.0, None, None, 150, "1 burger"),
    ("omelette", 154, 10.6, 0.6, 12.0, None, None, 100, "1 omelette"),
]
DEMO_SOURCE = "demo-seed (approximate values, NOT verified: load USDA/IFCT for real use)"


def seed_demo(db: Session) -> int:
    if db.scalar(select(NutritionFood.id).where(NutritionFood.source == DEMO_SOURCE).limit(1)):
        return 0
    for name, kcal, p, c, f, fib, sug, serv, desc in DEMO_FOODS:
        dec = lambda v: None if v is None else Decimal(str(v))  # noqa: E731
        db.add(NutritionFood(source=DEMO_SOURCE, name=name, name_norm=normalize(name), kcal=dec(kcal), protein_g=dec(p), carbs_g=dec(c),
                             fat_g=dec(f), fiber_g=dec(fib), sugar_g=dec(sug), default_serving_g=dec(serv), serving_description=desc, verified=False))
    db.flush()
    return len(DEMO_FOODS)


def match_food(db: Session, query: str, min_score: float = 0.72) -> tuple[NutritionFood, float] | None:
    """Exact normalised match first, then closest name above min_score. Returns (record, score)."""
    q = normalize(query.replace("_", " "))
    if not q:
        return None
    foods = db.scalars(select(NutritionFood)).all()
    best, best_score = None, 0.0
    for food in foods:
        if food.name_norm == q:
            return food, 1.0
        score = difflib.SequenceMatcher(None, q, food.name_norm).ratio()
        if q in food.name_norm.split() or food.name_norm in q.split():
            score = max(score, 0.8)
        if score > best_score:
            best, best_score = food, score
    return (best, round(best_score, 3)) if best and best_score >= min_score else None


def _scale(value: Decimal | None, grams: Decimal) -> float | None:
    if value is None:
        return None
    return float(round(value * grams / Decimal(100), 2))


def compute(food: NutritionFood, grams: float, *, portion_source: str) -> dict:
    """Scale per-100 g record to `grams`. portion_source: 'user' | 'default_serving'."""
    g = Decimal(str(grams))
    values = {n: _scale(getattr(food, n), g) for n in NUTRIENTS}
    unknown = [n for n, v in values.items() if v is None]
    return {
        "food": {"id": food.id, "name": food.name, "source": food.source, "verified": food.verified},
        "portion": {"grams": float(g), "basis": portion_source, "estimated": portion_source != "user",
                    "serving_description": food.serving_description if portion_source == "default_serving" else None},
        "nutrients": values,
        "unknown_nutrients": unknown,
        "per_100g": {n: (float(getattr(food, n)) if getattr(food, n) is not None else None) for n in NUTRIENTS},
        "health_score": health_score(food),
        "notes": ([] if food.verified else ["Source values are unverified demo data."])
        + (["Portion size is an estimate: adjust the grams for a more accurate result."] if portion_source != "user" else [])
        + ([f"Not available in the source record: {', '.join(unknown)}."] if unknown else []),
    }


def health_score(food: NutritionFood) -> dict:
    k, p, fib, sug, fat = (None if getattr(food, n) is None else float(getattr(food, n)) for n in ("kcal", "protein_g", "fiber_g", "sugar_g", "fat_g"))
    score, parts, skipped = 50, [], []

    def add(label: str, delta: int):
        nonlocal score
        score += delta
        parts.append({"criterion": label, "points": delta})

    if k is None:
        skipped.append("energy density")
    else:
        add("energy density", 15 if k <= 100 else 5 if k <= 200 else -5 if k <= 300 else -15)
    if p is None:
        skipped.append("protein")
    elif p >= 5:
        add("protein", 10 if p >= 10 else 5)
    if fib is None:
        skipped.append("fibre")
    elif fib >= 1.5:
        add("fibre", 10 if fib >= 3 else 5)
    if sug is None:
        skipped.append("sugar")
    elif sug >= 8:
        add("sugar", -10 if sug >= 15 else -5)
    if fat is None:
        skipped.append("total fat")
    elif fat >= 10:
        add("total fat", -10 if fat >= 20 else -5)
    return {"score": max(0, min(100, score)), "components": parts, "skipped": skipped, "criteria": HEALTH_SCORE_CRITERIA}


def estimate_ingredients(db: Session, ingredients: list[dict]) -> dict:
    """Sum nutrition over ingredients that have a gram weight and a database match.

    Returns totals for the *matched* subset plus coverage, so partial sums are never presented as complete.
    """
    totals: dict[str, float | None] = {n: 0.0 for n in NUTRIENTS}
    unknown_any: set[str] = set()
    matched, unmatched = [], []
    for ing in ingredients:
        grams, name = ing.get("grams"), ing.get("name", "")
        hit = match_food(db, name) if grams else None
        if not hit:
            unmatched.append(name)
            continue
        res = compute(hit[0], grams, portion_source="user")
        matched.append(name)
        for n in NUTRIENTS:
            if res["nutrients"][n] is None:
                unknown_any.add(n)
            elif totals[n] is not None:
                totals[n] += res["nutrients"][n]
    for n in unknown_any:
        totals[n] = None  # a nutrient missing for any matched ingredient cannot be totalled honestly
    return {
        "totals": {n: (round(v, 1) if v is not None else None) for n, v in totals.items()},
        "matched_ingredients": matched,
        "unmatched_ingredients": unmatched,
        "complete": not unmatched,
        "note": "Estimate from database-matched ingredients only." + (" Unmatched ingredients are NOT included, so totals are a lower bound." if unmatched else ""),
    }
