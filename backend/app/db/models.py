from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_id, utcnow


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    diet_pattern: Mapped[str | None] = mapped_column(String(30))  # omnivore | vegetarian | vegan | ...
    allergies: Mapped[list] = mapped_column(JSON, default=list)
    excluded_ingredients: Mapped[list] = mapped_column(JSON, default=list)
    nutrition_goals: Mapped[dict] = mapped_column(JSON, default=dict)
    cuisines: Mapped[list] = mapped_column(JSON, default=list)
    user: Mapped[User] = relationship(back_populates="profile")


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"
    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class MediaFile(Base, TimestampMixin):
    __tablename__ = "media_files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # image | video | audio | evidence
    storage_path: Mapped[str] = mapped_column(String(500))  # relative to media_root
    original_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Analysis(Base, TimestampMixin):
    """One row per recognition / nutrition / freshness analysis."""

    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # recognition | nutrition | freshness
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed | failed
    media_id: Mapped[str | None] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id", ondelete="SET NULL"))
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    corrected: Mapped[dict | None] = mapped_column(JSON)
    model_name: Mapped[str | None] = mapped_column(String(200))
    model_version: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("ix_analyses_user_kind_created", "user_id", "kind", "created_at"),)


class NutritionFood(Base):
    __tablename__ = "nutrition_foods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_id: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))
    name_norm: Mapped[str] = mapped_column(String(300), index=True)
    # per-100g values; NULL means unknown, never zero-filled
    kcal: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    carbs_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sugar_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    default_serving_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    serving_description: Mapped[str | None] = mapped_column(String(100))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class HygieneJob(Base, TimestampMixin):
    __tablename__ = "hygiene_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("media_files.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|completed|failed|cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    video_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    findings: Mapped[list["HygieneFinding"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    report: Mapped["HygieneReport"] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")


class HygieneFinding(Base):
    __tablename__ = "hygiene_findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("hygiene_jobs.id", ondelete="CASCADE"), index=True)
    indicator: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))  # observed_compliance|potential_violation_observed|insufficient_evidence|not_applicable
    confidence: Mapped[float | None] = mapped_column(Float)
    timestamp_s: Mapped[float | None] = mapped_column(Float)
    concern: Mapped[str | None] = mapped_column(Text)
    suggested_follow_up: Mapped[str | None] = mapped_column(Text)
    evidence_media_id: Mapped[str | None] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|confirmed|dismissed
    review_note: Mapped[str | None] = mapped_column(Text)
    job: Mapped[HygieneJob] = relationship(back_populates="findings")


class HygieneReport(Base, TimestampMixin):
    __tablename__ = "hygiene_reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("hygiene_jobs.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    job: Mapped[HygieneJob] = relationship(back_populates="report")


class Recipe(Base, TimestampMixin):
    __tablename__ = "recipes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)
    ingredient_names: Mapped[list] = mapped_column(JSON, default=list)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("recipes.id", ondelete="SET NULL"))
    model_name: Mapped[str | None] = mapped_column(String(200))


class MealPlan(Base, TimestampMixin):
    __tablename__ = "meal_plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="generating")  # generating|ready|failed
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    shopping_list: Mapped[list | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    feedback: Mapped[list] = mapped_column(JSON, default=list)
