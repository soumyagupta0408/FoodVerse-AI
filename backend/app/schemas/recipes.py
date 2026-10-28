from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORM

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


class Ingredient(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=30)
    grams: float | None = Field(default=None, gt=0, le=5000, description="Approximate weight in grams, if it can be stated")


class SubstitutionHint(BaseModel):
    ingredient: str
    alternatives: list[str] = []


class RecipeData(BaseModel):
    """Schema the LLM must fill. Validated before anything is shown or stored."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    servings: int = Field(ge=1, le=24)
    prep_minutes: int = Field(ge=0, le=1440)
    cook_minutes: int = Field(ge=0, le=1440)
    ingredients: list[Ingredient] = Field(min_length=1, max_length=60)
    steps: list[str] = Field(min_length=1, max_length=40)
    substitutions: list[SubstitutionHint] = []
    tips: list[str] = []
    food_safety: list[str] = []


class RecipeRequest(BaseModel):
    ingredients: list[str] = Field(default=[], max_length=40)
    cuisine: str | None = Field(default=None, max_length=60)
    meal_type: str | None = Field(default=None, pattern="^(breakfast|lunch|dinner|snack|dessert)$")
    cooking_minutes: int | None = Field(default=None, ge=5, le=480)
    skill_level: str | None = Field(default=None, pattern="^(beginner|intermediate|advanced)$")
    equipment: list[str] = Field(default=[], max_length=20)
    servings: int = Field(default=2, ge=1, le=24)
    dietary_notes: str | None = Field(default=None, max_length=300)
    allergies: list[str] = Field(default=[], max_length=20)
    excluded_ingredients: list[str] = Field(default=[], max_length=30)
    diet_pattern: str | None = Field(default=None, pattern="^(omnivore|vegetarian|vegan|pescatarian)$")
    budget: str | None = Field(default=None, max_length=60)
    nutrition_goal: str | None = Field(default=None, max_length=200)
    request: str | None = Field(default=None, max_length=500, description="Free-text request or follow-up change")
    use_profile: bool = True
    save: bool = False


class RecipeSearch(BaseModel):
    ingredients: list[str] = Field(min_length=1, max_length=30)
    saved_only: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class ScaleRequest(BaseModel):
    servings: int = Field(ge=1, le=48)


class SubstituteRequest(BaseModel):
    ingredient: str = Field(min_length=1, max_length=120)
    replacement: str | None = Field(default=None, max_length=120)
    reason: str | None = Field(default=None, max_length=200)


class AlternativeOut(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = None
    unit: str | None = None
    note: str = Field(default="", max_length=300)


class SubstitutionOut(BaseModel):
    alternatives: list[AlternativeOut] = Field(min_length=1, max_length=6)


class RecipeOut(ORM):
    id: str
    title: str
    data: dict
    saved: bool
    parent_id: str | None = None
    model_name: str | None = None
    created_at: datetime
    meta: dict = {}


class SaveRequest(BaseModel):
    saved: bool = True
