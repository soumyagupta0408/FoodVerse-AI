from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORM


class MealIngredient(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    grams: float = Field(gt=0, le=3000)


class MealData(BaseModel):
    meal_type: str = Field(default="", max_length=20)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    ingredients: list[MealIngredient] = Field(min_length=1, max_length=25)
    rationale: str = Field(default="", max_length=500)
    prep_minutes: int | None = Field(default=None, ge=0, le=600)


class DayData(BaseModel):
    meals: list[MealData] = Field(min_length=1, max_length=8)


class MealPlanRequest(BaseModel):
    days: int = Field(default=1, ge=1, le=7)
    meals: list[str] = Field(default=["breakfast", "lunch", "dinner"], min_length=1, max_length=4)
    include_snack: bool = False
    servings: int = Field(default=1, ge=1, le=12)
    cuisines: list[str] = Field(default=[], max_length=10)
    allergies: list[str] = Field(default=[], max_length=20)
    excluded_ingredients: list[str] = Field(default=[], max_length=30)
    diet_pattern: str | None = Field(default=None, pattern="^(omnivore|vegetarian|vegan|pescatarian)$")
    target_kcal_per_day: int | None = Field(default=None, ge=800, le=6000, description="User-defined goal, not medical advice")
    available_ingredients: list[str] = Field(default=[], max_length=40)
    budget: str | None = Field(default=None, max_length=60)
    max_cooking_minutes: int | None = Field(default=None, ge=5, le=240)
    use_profile: bool = True

    @model_validator(mode="after")
    def _meals_ok(self):
        allowed = {"breakfast", "lunch", "dinner", "snack"}
        bad = [m for m in self.meals if m not in allowed]
        if bad:
            raise ValueError(f"Unknown meal type(s): {', '.join(bad)}")
        if self.include_snack and "snack" not in self.meals:
            self.meals = [*self.meals, "snack"]
        return self


class ReplaceSlot(BaseModel):
    day: int = Field(ge=1, le=7)
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack)$")
    instruction: str | None = Field(default=None, max_length=300)


class FeedbackIn(BaseModel):
    day: int = Field(ge=1, le=7)
    meal_type: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=300)


class MealPlanPatch(BaseModel):
    replace: ReplaceSlot | None = None
    feedback: FeedbackIn | None = None

    @model_validator(mode="after")
    def _one(self):
        if bool(self.replace) == bool(self.feedback):
            raise ValueError("Provide exactly one of 'replace' or 'feedback'")
        return self


class MealPlanOut(ORM):
    id: str
    status: str
    params: dict
    plan: dict
    shopping_list: list | None = None
    error: str | None = None
    feedback: list = []
    created_at: datetime
    updated_at: datetime
