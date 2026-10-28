from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.ratelimit import upload_limiter
from app.db.models import User
from app.db.session import get_db
from app.services import assistant, storage

router = APIRouter(prefix="/assistant", tags=["assistant"])


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    analysis_id: str | None = None


@router.post("/message")
def message(body: MessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return assistant.handle(db, user, body.text, analysis_id=body.analysis_id).asdict()


@router.post("/audio", dependencies=[Depends(upload_limiter)])
def audio(file: UploadFile = File(...), analysis_id: str | None = Form(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = storage.read_limited(file, get_settings().max_audio_mb * 1024 * 1024)
    ext, _ = storage.validate_audio(data)
    transcript = assistant.transcribe_upload(data, ext)
    reply = assistant.handle(db, user, transcript, analysis_id=analysis_id)
    reply.transcript = transcript
    return reply.asdict()


@router.post("/multimodal", dependencies=[Depends(upload_limiter)])
def multimodal(file: UploadFile = File(...), text: str = Form(default=""), user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = storage.read_limited(file, get_settings().max_image_mb * 1024 * 1024)
    return assistant.handle(db, user, text[:1000], image=data, image_name=file.filename).asdict()


routers = [router]
