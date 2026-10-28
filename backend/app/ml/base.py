"""Interfaces between the application and model implementations. Swap a model by implementing one of these."""
from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image


@dataclass
class Prediction:
    label: str
    confidence: float


class FoodRecognizer(Protocol):
    name: str
    version: str

    def predict(self, image: Image.Image, top_k: int = 5) -> list[Prediction]: ...


class FreshnessClassifier(Protocol):
    category: str
    name: str
    version: str
    labels: list[str]  # e.g. ["fresh", "moderate", "spoiled"]

    def predict_proba(self, image: Image.Image) -> dict[str, float]: ...


class FreshnessRegistry(Protocol):
    def categories(self) -> list[str]: ...

    def get(self, category: str) -> FreshnessClassifier | None: ...


@dataclass
class FrameObservation:
    """What a detector saw in one frame. `detected` holds positive evidence only."""

    timestamp_s: float
    persons: int = 0
    detected: dict[str, float] = field(default_factory=dict)  # indicator -> best confidence among positive detections
    boxes: list[dict] = field(default_factory=list)  # [{"label","score","box":[x0,y0,x1,y1]}] for evidence drawing


class HygieneDetector(Protocol):
    name: str
    version: str
    supported_indicators: tuple[str, ...]

    def observe(self, frame_bgr, timestamp_s: float) -> FrameObservation: ...


class SpeechToText(Protocol):
    name: str

    def transcribe(self, path: str) -> dict: ...  # {"text": str, "language": str | None}
