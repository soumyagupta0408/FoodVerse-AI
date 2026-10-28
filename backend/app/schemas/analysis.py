from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class AnalysisOut(ORM):
    id: str
    kind: str
    status: str
    media_id: str | None = None
    parent_id: str | None = None
    input: dict = {}
    result: dict = {}
    corrected: dict | None = None
    model_name: str | None = None
    model_version: str | None = None
    error: str | None = None
    created_at: datetime


class RecognitionCorrection(BaseModel):
    food_name: str = Field(min_length=1, max_length=200)


class NutritionRequest(BaseModel):
    recognition_id: str | None = None
    food_name: str | None = Field(default=None, max_length=200)
    grams: float | None = Field(default=None, gt=0, le=5000)

    def model_post_init(self, _ctx):
        if not self.recognition_id and not self.food_name:
            raise ValueError("Provide recognition_id or food_name")


class FreshnessMeta(BaseModel):
    food_category: str | None = Field(default=None, max_length=100)
