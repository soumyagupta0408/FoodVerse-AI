import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import Unauthorized

_ph = PasswordHasher()
ALGO = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, role: str) -> str:
    s = get_settings()
    payload = {"sub": user_id, "role": role, "type": "access", "iat": _now(), "exp": _now() + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, s.secret_key, algorithm=ALGO)


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    s = get_settings()
    jti = uuid.uuid4().hex
    exp = _now() + timedelta(days=s.refresh_token_days)
    token = jwt.encode({"sub": user_id, "jti": jti, "type": "refresh", "iat": _now(), "exp": exp}, s.secret_key, algorithm=ALGO)
    return token, jti, exp


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired", code="token_expired")
    except jwt.PyJWTError:
        raise Unauthorized("Invalid token", code="invalid_token")
    if payload.get("type") != expected_type:
        raise Unauthorized("Wrong token type", code="invalid_token")
    return payload


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
