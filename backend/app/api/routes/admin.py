from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import User
from app.db.session import get_db
from app.services import storage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active, "created_at": u.created_at} for u in db.scalars(select(User).order_by(User.created_at)).all()]


@router.post("/retention/run")
def run_retention(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return {"deleted_media": storage.purge_expired(db)}


routers = [router]
