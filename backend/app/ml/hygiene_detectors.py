"""Frame-level detectors for kitchen hygiene. These report POSITIVE evidence only.

Absence of a detection in a frame is never treated as a violation here: the temporal analysis in
services/hygiene.py decides, across many frames, whether the evidence is sufficient.

OWL-ViT is a zero-shot detector. It is NOT trained or validated on kitchen PPE, so its output is
low-reliability and every finding is routed to human review.
"""
import logging

from app.core.config import get_settings
from app.core.errors import ModelUnavailable
from app.ml.base import FrameObservation

log = logging.getLogger("foodverse.ml")

QUERIES = {
    "person": ["a person"],
    "hair_cap": ["a hair net on a head", "a chef hat", "a cap on a head"],
    "gloves": ["a hand wearing a disposable glove", "a gloved hand"],
}
SCORE_THRESHOLD = 0.15


class OwlVitHygieneDetector:
    version = "zero-shot"
    supported_indicators = ("hair_cap", "gloves")

    def __init__(self, model_id: str):
        self.name = model_id
        self._pipe = None

    def _load(self):
        if self._pipe is None:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise ModelUnavailable("Hygiene detection needs 'transformers' and 'torch'. Run scripts/download_models.py") from exc
            try:
                self._pipe = pipeline("zero-shot-object-detection", model=self.name, device=-1)
            except Exception as exc:
                raise ModelUnavailable(f"Hygiene detector '{self.name}' could not be loaded. Run scripts/download_models.py") from exc
        return self._pipe

    def observe(self, frame_bgr, timestamp_s: float) -> FrameObservation:
        from PIL import Image

        rgb = frame_bgr[:, :, ::-1]
        image = Image.fromarray(rgb)
        labels = [q for qs in QUERIES.values() for q in qs]
        results = self._load()(image, candidate_labels=labels)
        obs = FrameObservation(timestamp_s=timestamp_s)
        for r in results:
            if r["score"] < SCORE_THRESHOLD:
                continue
            for indicator, qs in QUERIES.items():
                if r["label"] in qs:
                    b = r["box"]
                    obs.boxes.append({"label": indicator, "score": float(r["score"]), "box": [b["xmin"], b["ymin"], b["xmax"], b["ymax"]]})
                    if indicator == "person":
                        obs.persons += 1
                    else:
                        obs.detected[indicator] = max(obs.detected.get(indicator, 0.0), float(r["score"]))
        return obs


class UnavailableHygieneDetector:
    name, version, supported_indicators = "none", "0", ()

    def observe(self, frame_bgr, timestamp_s):
        raise ModelUnavailable("Hygiene detection is disabled (HYGIENE_DETECTOR_PROVIDER=none).")


def build_hygiene_detector():
    s = get_settings()
    return OwlVitHygieneDetector(s.hygiene_detector_model) if s.hygiene_detector_provider == "owlvit" else UnavailableHygieneDetector()
