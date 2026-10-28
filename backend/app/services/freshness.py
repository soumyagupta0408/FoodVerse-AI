import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ModelUnavailable, ValidationFailed
from app.db.models import Analysis, User
from app.ml.registry import get_freshness_registry
from app.services import storage
from app.services.safety import normalize

DISPLAY = {"fresh": "Fresh", "moderate": "Moderately Fresh", "spoiled": "Spoiled", "unable_to_determine": "Unable to determine"}
ALIASES = {"moderately fresh": "moderate", "moderately_fresh": "moderate", "medium": "moderate", "rotten": "spoiled", "stale": "spoiled"}

SAFETY_NOTE = (
    "A visual check cannot show whether food is microbiologically safe. Food that looks fresh can still be unsafe, and a "
    "photo cannot detect bacteria or toxins. Also consider storage temperature, how long it has been stored, the expiry "
    "date, and food-specific safety guidance. When in doubt, throw it out."
)

RECOMMENDATIONS = {
    "fresh": "No visible signs of spoilage were detected. Keep refrigerated as appropriate and use before the expiry date.",
    "moderate": "Some signs of ageing were detected. Use soon, inspect closely, and discard if you notice smell, sliminess, or mould.",
    "spoiled": "Visible signs of spoilage were detected. Do not eat it. Discard it safely.",
    "unable_to_determine": "The result is uncertain. Do not rely on it: check smell, texture, storage time, and expiry date.",
}


def assess_quality(image) -> dict:
    """Cheap objective checks on blur, brightness and size."""
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    h, w = gray.shape
    issues = []
    if min(h, w) < 128:
        issues.append("image is very small")
    if blur < 20:
        issues.append("image looks blurry")
    if brightness < 40:
        issues.append("image is too dark")
    elif brightness > 225:
        issues.append("image is overexposed")
    return {"blur_score": round(blur, 1), "brightness": round(brightness, 1), "issues": issues, "ok": not issues}


def _canon(label: str) -> str:
    key = normalize(label.replace("_", " "))
    return ALIASES.get(key, key.split()[0] if key else key)


def analyze(db: Session, user: User, data: bytes, filename: str | None, food_category: str | None) -> Analysis:
    fmt, w, h = storage.validate_image(data)
    ext, mime = storage.IMAGE_FORMATS[fmt]
    image = storage.load_image(data)
    registry = get_freshness_registry()
    supported = registry.categories()
    category = normalize(food_category) if food_category else None
    quality = assess_quality(image)
    media = storage.store_bytes(db, user_id=user.id, kind="image", data=data, ext=ext, mime=mime, original_name=filename, meta={"width": w, "height": h})

    base = {"supported_categories": supported, "quality": quality, "safety_note": SAFETY_NOTE, "category": category}
    classifier = registry.get(category) if category else None
    reason = None
    probs: dict[str, float] = {}
    if not category:
        reason = "Choose the food category (e.g. banana) so the matching freshness model can be used."
    elif classifier is None:
        reason = (f"No freshness model is installed for '{category}'." +
                  (f" Supported categories: {', '.join(supported)}." if supported else " No freshness models are installed yet: see docs/MODELS.md to train one."))
    elif not quality["ok"]:
        reason = "Image quality is too low for a reliable assessment (" + ", ".join(quality["issues"]) + "). Retake the photo in good light."

    if reason is None:
        raw = classifier.predict_proba(image)
        probs = {_canon(k): round(v, 4) for k, v in raw.items()}
        state, conf = max(probs.items(), key=lambda kv: kv[1])
        if conf < get_settings().freshness_min_confidence or state not in DISPLAY:
            reason = f"The model was not confident enough ({conf:.0%}) to give a reliable classification."
            base["probabilities"] = probs
    if reason is not None:
        result = {**base, "state": "unable_to_determine", "display": DISPLAY["unable_to_determine"], "confidence": None,
                  "reason": reason, "recommendation": RECOMMENDATIONS["unable_to_determine"], "indicators": []}
        name, version = (classifier.name, classifier.version) if classifier else (None, None)
    else:
        result = {**base, "state": state, "display": DISPLAY[state], "confidence": conf, "probabilities": probs, "reason": None,
                  "recommendation": RECOMMENDATIONS[state],
                  "indicators": ["Classification is based on overall visual appearance (colour, surface and texture patterns); the model does not name individual indicators."]}
        name, version = classifier.name, classifier.version
    analysis = Analysis(user_id=user.id, kind="freshness", media_id=media.id, input={"filename": filename, "food_category": category},
                        result=result, model_name=name, model_version=version)
    db.add(analysis)
    db.flush()
    return analysis
