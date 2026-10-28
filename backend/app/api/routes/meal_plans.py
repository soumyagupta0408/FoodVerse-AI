from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.models import MealPlan, User
from app.db.session import get_db, get_sessionmaker
from app.schemas.common import Page
from app.schemas.meal_plans import MealPlanOut, MealPlanPatch, MealPlanRequest
from app.services import meal_plans as svc

router = APIRouter(prefix="/meal-plans", tags=["meal plans"])


@router.post("/generate", response_model=MealPlanOut, status_code=status.HTTP_202_ACCEPTED)
def generate(body: MealPlanRequest, tasks: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Starts generation (slow on CPU). Poll GET /meal-plans/{id} until status is ready or failed."""
    mp = svc.create(db, user, body)
    db.commit()
    tasks.add_task(svc.run_generation, get_sessionmaker(), mp.id)
    return mp


@router.get("", response_model=Page[MealPlanOut])
def list_plans(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(MealPlan).where(MealPlan.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(MealPlan.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{plan_id}", response_model=MealPlanOut)
def get_plan(plan_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.get_owned(db, user, plan_id)


@router.patch("/{plan_id}", response_model=MealPlanOut)
def patch_plan(plan_id: str, body: MealPlanPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mp = svc.get_owned(db, user, plan_id)
    if body.replace:
        return svc.replace_slot(db, user, mp, body.replace.day, body.replace.meal_type, body.replace.instruction)
    return svc.add_feedback(mp, body.feedback.model_dump())


@router.post("/{plan_id}/shopping-list")
def make_shopping_list(plan_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mp = svc.get_owned(db, user, plan_id)
    mp.shopping_list = svc.shopping_list(mp)
    return {"items": mp.shopping_list,
            "note": "Totals are the generated gram weights summed across meals and servings. Round up to package sizes when shopping."}


routers = [router]
