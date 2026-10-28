from datetime import timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import Conflict, Unauthorized
from app.core.ratelimit import auth_limiter
from app.core.security import (create_access_token, create_refresh_token, decode_token, hash_password, verify_password)
from app.db.base import utcnow
from app.db.models import RefreshToken, User, UserProfile
from app.db.session import get_db
from app.schemas.auth import LoginIn, ProfileOut, ProfileUpdate, RefreshIn, RegisterIn, TokenPair, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


def _issue(db: Session, user: User) -> TokenPair:
    refresh, jti, exp = create_refresh_token(user.id)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=exp))
    return TokenPair(access_token=create_access_token(user.id, user.role), refresh_token=refresh)


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_limiter)])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise Conflict("An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    user.profile = UserProfile(display_name=body.display_name)
    db.add(user)
    db.flush()
    return _issue(db, user)


@router.post("/login", response_model=TokenPair, dependencies=[Depends(auth_limiter)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Incorrect email or password", code="invalid_credentials")
    return _issue(db, user)


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(auth_limiter)])
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token, "refresh")
    record = db.get(RefreshToken, payload["jti"])
    expires = record.expires_at.replace(tzinfo=timezone.utc) if record and record.expires_at.tzinfo is None else (record.expires_at if record else None)
    if not record or record.revoked or expires < utcnow():
        raise Unauthorized("Refresh token is no longer valid", code="invalid_token")
    record.revoked = True  # rotate
    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise Unauthorized("User not found or disabled")
    return _issue(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except Unauthorized:
        return
    record = db.get(RefreshToken, payload["jti"])
    if record:
        record.revoked = True


@users_router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@users_router.patch("/me/profile", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = user.profile or UserProfile(user_id=user.id)
    user.profile = profile
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.flush()
    return profile


@users_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the account, all history, and all stored media files."""
    from app.db.models import MediaFile
    from app.services.storage import delete_media

    for media in db.scalars(select(MediaFile).where(MediaFile.user_id == user.id)).all():
        delete_media(db, media)
    db.flush()
    db.delete(user)
