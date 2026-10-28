"""Promote a user to admin: python scripts/make_admin.py someone@example.com"""
import sys

from sqlalchemy import select

from app.db.models import User
from app.db.session import get_sessionmaker

with get_sessionmaker()() as db:
    user = db.scalar(select(User).where(User.email == sys.argv[1].lower()))
    if not user:
        sys.exit("No such user")
    user.role = "admin"
    db.commit()
    print("ok")
