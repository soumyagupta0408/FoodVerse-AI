from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise Unauthorized("Authentication required")
    payload = decode_token(creds.credentials, "access")
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise Unauthorized("User not found or disabled")
    return user


def require_role(*roles: str):
    def _dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise Forbidden("You do not have permission to do this")
        return user

    return _dep
