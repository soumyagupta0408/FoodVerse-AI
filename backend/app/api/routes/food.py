from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.ratelimit import upload_limiter
from app.db.models import Analysis, User
from app.db.session import get_db
from app.schemas.analysis import AnalysisOut, FreshnessMeta, NutritionRequest, RecognitionCorrection
from app.services import freshness as freshness_svc
from app.services import nutrition_service, recognition, storage

food_router = APIRouter(prefix="/food", tags=["food recognition"])
nutrition_router = APIRouter(prefix="/nutrition", tags=["nutrition"])
freshness_router = APIRouter(prefix="/freshness", tags=["freshness"])
media_router = APIRouter(prefix="/media", tags=["media"])


def _image_bytes(file: UploadFile) -> bytes:
    return storage.read_limited(file, get_settings().max_image_mb * 1024 * 1024)


@food_router.post("/recognize", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(upload_limiter)])
def recognize(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return recognition.recognize(db, user, _image_bytes(file), file.filename)


@food_router.get("/recognize/{analysis_id}", response_model=AnalysisOut)
def get_recognition(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return recognition.get_owned(db, analysis_id, user, "recognition")


@food_router.patch("/recognize/{analysis_id}/correction", response_model=AnalysisOut)
def correct_recognition(analysis_id: str, body: RecognitionCorrection, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return recognition.correct(db, user, analysis_id, body.food_name)


@nutrition_router.post("/analyze", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
def analyze_nutrition(body: NutritionRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return nutrition_service.analyze(db, user, recognition_id=body.recognition_id, food_name=body.food_name, grams=body.grams)


@nutrition_router.get("/{analysis_id}", response_model=AnalysisOut)
def get_nutrition(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return nutrition_service.get(db, user, analysis_id)


@freshness_router.get("/categories")
def freshness_categories(user: User = Depends(current_user)):
    from app.ml.registry import get_freshness_registry

    return {"categories": get_freshness_registry().categories()}


@freshness_router.post("/analyze", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(upload_limiter)])
def analyze_freshness(file: UploadFile = File(...), food_category: str | None = Form(default=None),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    meta = FreshnessMeta(food_category=food_category)
    return freshness_svc.analyze(db, user, _image_bytes(file), file.filename, meta.food_category)


@freshness_router.get("/{analysis_id}", response_model=AnalysisOut)
def get_freshness(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return recognition.get_owned(db, analysis_id, user, "freshness")


@media_router.get("/{media_id}")
def get_media(media_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Owner-only access to stored images, evidence frames and videos."""
    media = storage.get_owned_media(db, media_id, user.id)
    return FileResponse(storage.media_path(media), media_type=media.content_type)
