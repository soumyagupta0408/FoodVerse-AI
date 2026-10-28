from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./foodverse.db"
    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    cors_origins: str = "http://localhost:5173"

    # storage
    media_root: Path = Path("./media")
    retention_days: int = 30
    max_image_mb: int = 10
    max_video_mb: int = 200
    max_audio_mb: int = 25
    max_video_seconds: int = 900
    max_image_pixels: int = 40_000_000

    # LLM (local, Ollama)
    llm_provider: str = "ollama"  # ollama | none
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    llm_timeout_seconds: int = 180
    llm_max_retries: int = 2

    # models (Hugging Face ids or local directories)
    recognizer_provider: str = "hf"  # hf | none
    recognizer_model: str = "nateraw/food"
    freshness_models_dir: Path = Path("./models/freshness")
    freshness_min_confidence: float = 0.6
    hygiene_detector_provider: str = "owlvit"  # owlvit | none
    hygiene_detector_model: str = "google/owlvit-base-patch32"
    hygiene_frame_interval_s: float = 1.0
    stt_provider: str = "faster-whisper"  # faster-whisper | none
    stt_model: str = "base"

    # nutrition
    nutrition_seed_demo: bool = True  # approximate demo values, clearly labelled

    # rate limits (per client, per minute)
    rate_limit_auth_per_min: int = 20
    rate_limit_upload_per_min: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _check_secret(self):
        if self.env == "production" and self.secret_key == "change-me-in-production":
            raise ValueError("SECRET_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
