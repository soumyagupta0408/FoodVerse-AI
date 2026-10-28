import logging

from PIL import Image

from app.core.config import get_settings
from app.core.errors import ModelUnavailable
from app.ml.base import Prediction

log = logging.getLogger("foodverse.ml")

INSTALL_HINT = "Install the model weights with `python scripts/download_models.py` (needs internet once), then retry."


class HFImageClassifier:
    """Hugging Face image-classification pipeline (default: a Food-101 fine-tune). Single-label, 101 Western-leaning classes."""

    version = "hf"

    def __init__(self, model_id: str):
        self.name = model_id
        self._pipe = None

    def _load(self):
        if self._pipe is not None:
            return self._pipe
        try:
            from transformers import pipeline  # imported lazily: heavy dependency
        except ImportError as exc:
            raise ModelUnavailable(f"Food recognition needs the 'transformers' and 'torch' packages. {INSTALL_HINT}") from exc
        try:
            self._pipe = pipeline("image-classification", model=self.name, device=-1)
        except Exception as exc:  # missing weights / offline
            log.warning("recognizer load failed: %s", exc)
            raise ModelUnavailable(f"Food recognition model '{self.name}' could not be loaded. {INSTALL_HINT}") from exc
        return self._pipe

    def predict(self, image: Image.Image, top_k: int = 5) -> list[Prediction]:
        out = self._load()(image, top_k=top_k)
        return [Prediction(label=o["label"], confidence=float(o["score"])) for o in out]


class UnavailableRecognizer:
    name, version = "none", "0"

    def predict(self, image, top_k=5):
        raise ModelUnavailable("Food recognition is disabled (RECOGNIZER_PROVIDER=none). Enter the food manually or enable a model.")


def build_recognizer():
    s = get_settings()
    return HFImageClassifier(s.recognizer_model) if s.recognizer_provider == "hf" else UnavailableRecognizer()
