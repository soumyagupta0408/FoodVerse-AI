from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class JobOut(ORM):
    id: str
    status: str
    progress: float
    video_meta: dict
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    report_id: str | None = None


class ReviewIn(BaseModel):
    review_status: str = Field(pattern="^(confirmed|dismissed|pending)$")
    note: str | None = Field(default=None, max_length=500)
