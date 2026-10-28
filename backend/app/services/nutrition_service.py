from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.db.models import Analysis, User
from app.services import nutrition, recognition


def analyze(db: Session, user: User, *, recognition_id: str | None, food_name: str | None, grams: float | None) -> Analysis:
    parent = None
    name = food_name
    if recognition_id:
        parent = recognition.get_owned(db, recognition_id, user, "recognition")
        name = name or recognition.effective_food_name(parent)
    if not name:
        raise ValidationFailed("No food name available. Enter one manually.")
    hit = nutrition.match_food(db, name)
    if not hit:
        analysis = Analysis(user_id=user.id, kind="nutrition", parent_id=parent.id if parent else None, status="completed",
                            input={"food_name": name, "grams": grams},
                            result={"matched": False, "food_name": name,
                                    "message": f"No nutrition record found for '{name}'. Nothing was estimated: try a more common name or load a larger nutrition database."})
        db.add(analysis)
        db.flush()
        return analysis
    food, score = hit
    if grams:
        res = nutrition.compute(food, grams, portion_source="user")
    elif food.default_serving_g:
        res = nutrition.compute(food, float(food.default_serving_g), portion_source="default_serving")
    else:
        raise ValidationFailed("This food has no default serving size in the database. Provide a portion in grams.")
    res.update({"matched": True, "food_name": name, "match_score": score,
                "match_note": None if score >= 0.95 else f"Matched to '{food.name}' by name similarity ({score:.0%}). Check this is the right food."})
    analysis = Analysis(user_id=user.id, kind="nutrition", parent_id=parent.id if parent else None,
                        input={"food_name": name, "grams": grams}, result=res, model_name="nutrition-db", model_version=food.source)
    db.add(analysis)
    db.flush()
    return analysis


def get(db: Session, user: User, analysis_id: str) -> Analysis:
    a = recognition.get_owned(db, analysis_id, user, "nutrition")
    if not a:
        raise NotFound("Analysis not found")
    return a
