from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORM


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ProfileOut(ORM):
    display_name: str | None = None
    diet_pattern: str | None = None
    allergies: list[str] = []
    excluded_ingredients: list[str] = []
    nutrition_goals: dict = {}
    cuisines: list[str] = []


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    diet_pattern: str | None = Field(default=None, pattern="^(omnivore|vegetarian|vegan|pescatarian)$")
    allergies: list[str] | None = Field(default=None, max_length=30)
    excluded_ingredients: list[str] | None = Field(default=None, max_length=50)
    nutrition_goals: dict | None = None
    cuisines: list[str] | None = Field(default=None, max_length=20)


class UserOut(ORM):
    id: str
    email: EmailStr
    role: str
    profile: ProfileOut | None = None
