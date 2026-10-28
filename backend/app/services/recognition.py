from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.models import Analysis, User
from app.ml.registry import get_recognizer
from app.services import storage

LOW_CONFIDENCE = 0.4


def recognize(db: Session, user: User, data: bytes, filename: str | None) -> Analysis:
    fmt, w, h = storage.validate_image(data)
    ext, mime = storage.IMAGE_FORMATS[fmt]
    image = storage.load_image(data)
    recognizer = get_recognizer()
    preds = recognizer.predict(image, top_k=5)  # raises ModelUnavailable if no model: no fake predictions
    media = storage.store_bytes(db, user_id=user.id, kind="image", data=data, ext=ext, mime=mime,
                                original_name=filename, meta={"width": w, "height": h})
    ranked = [{"label": p.label.replace("_", " "), "raw_label": p.label, "confidence": round(p.confidence, 4)} for p in preds]
    notes = ["This model labels the whole image with a single dish. Photos with several foods are not split into items."]
    if not ranked or ranked[0]["confidence"] < LOW_CONFIDENCE:
        notes.append("Low confidence: the top prediction may be wrong. Please confirm or correct the food name.")
    analysis = Analysis(
        user_id=user.id, kind="recognition", media_id=media.id, input={"filename": filename, "width": w, "height": h},
        result={"predictions": ranked, "top": ranked[0] if ranked else None, "notes": notes, "multi_item_supported": False},
        model_name=recognizer.name, model_version=recognizer.version,
    )
    db.add(analysis)
    db.flush()
    return analysis


def get_owned(db: Session, analysis_id: str, user: User, kind: str | None = None) -> Analysis:
    a = db.get(Analysis, analysis_id)
    if not a or a.user_id != user.id or (kind and a.kind != kind):
        raise NotFound("Analysis not found")
    return a


def correct(db: Session, user: User, analysis_id: str, food_name: str) -> Analysis:
    a = get_owned(db, analysis_id, user, "recognition")
    a.corrected = {"food_name": food_name.strip()}
    db.flush()
    return a


def effective_food_name(a: Analysis) -> str | None:
    if a.corrected and a.corrected.get("food_name"):
        return a.corrected["food_name"]
    top = (a.result or {}).get("top")
    return top["label"] if top else None
