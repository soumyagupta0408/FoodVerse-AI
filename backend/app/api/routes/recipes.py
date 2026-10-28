from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.models import Recipe, User
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.recipes import RecipeOut, RecipeRequest, RecipeSearch, SaveRequest, ScaleRequest, SubstituteRequest
from app.services import recipes as svc

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.post("/generate", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def generate(body: RecipeRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.to_out(svc.generate(db, user, body))


@router.post("/{recipe_id}/revise", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def revise(recipe_id: str, body: RecipeRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Conversational follow-up: change an existing recipe ('make it spicier', 'no oven')."""
    from app.schemas.recipes import RecipeData

    src = svc.get_owned(db, user, recipe_id)
    prev = RecipeData.model_validate({k: v for k, v in src.data.items() if k != "_meta"})
    stored = (src.data.get("_meta") or {}).get("restrictions") or {}
    body = body.model_copy(update={"allergies": [*body.allergies, *stored.get("allergies", [])],
                                   "excluded_ingredients": [*body.excluded_ingredients, *stored.get("excluded", [])],
                                   "diet_pattern": body.diet_pattern or stored.get("diet")})
    return svc.to_out(svc.generate(db, user, body, previous=prev, parent_id=src.id))


@router.post("/search")
def search(body: RecipeSearch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"results": svc.search(db, user, body.ingredients, body.saved_only, body.limit),
            "note": "Searches your own generated and saved recipes. Use /recipes/generate to create a new one."}


@router.get("", response_model=Page[RecipeOut])
def list_recipes(saved: bool | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Recipe).where(Recipe.user_id == user.id)
    if saved is not None:
        q = q.where(Recipe.saved.is_(saved))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Recipe.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[svc.to_out(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.to_out(svc.get_owned(db, user, recipe_id))


@router.post("/{recipe_id}/save", response_model=RecipeOut)
def save_recipe(recipe_id: str, body: SaveRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = svc.get_owned(db, user, recipe_id)
    r.saved = body.saved
    return svc.to_out(r)


@router.post("/{recipe_id}/scale", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def scale(recipe_id: str, body: ScaleRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.to_out(svc.scale(db, user, recipe_id, body.servings))


@router.post("/{recipe_id}/substitute")
def substitute(recipe_id: str, body: SubstituteRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.substitute(db, user, recipe_id, body.ingredient, body.replacement, body.reason)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(svc.get_owned(db, user, recipe_id))


routers = [router]
