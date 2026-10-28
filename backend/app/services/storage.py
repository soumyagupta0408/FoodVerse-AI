"""Media storage: validation, safe paths, retention. Files live on disk, metadata in the DB."""
import io
import os
from datetime import timedelta
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound, PayloadTooLarge, ValidationFailed
from app.core.security import sha256_hex
from app.db.base import new_id, utcnow
from app.db.models import MediaFile

IMAGE_FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
CHUNK = 1024 * 1024


def media_root() -> Path:
    root = get_settings().media_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_join(relative: str) -> Path:
    """Resolve a stored relative path and refuse anything that escapes media_root."""
    root = media_root()
    path = (root / relative).resolve()
    if root not in path.parents and path != root:
        raise ValidationFailed("Invalid storage path")
    return path


def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = upload.file.read(CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise PayloadTooLarge(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit")
    if not buf:
        raise ValidationFailed("Uploaded file is empty")
    return bytes(buf)


def validate_image(data: bytes) -> tuple[str, int, int]:
    """Check the bytes really are a supported, uncorrupted image. Returns (format, width, height)."""
    limit = get_settings().max_image_pixels
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt, (w, h) = probe.format, probe.size
            if w * h > limit:
                raise ValidationFailed(f"Image is too large ({w}x{h}); maximum is {limit} pixels")
            probe.verify()
        with Image.open(io.BytesIO(data)) as full:
            full.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationFailed("File is not a valid image. Supported formats: JPEG, PNG, WEBP")
    if fmt not in IMAGE_FORMATS:
        raise ValidationFailed("Unsupported image format. Supported formats: JPEG, PNG, WEBP")
    return fmt, w, h


def load_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img.convert("RGB")


_AUDIO_SIGNATURES = (
    (b"RIFF", 0, "wav", "audio/wav"),
    (b"ID3", 0, "mp3", "audio/mpeg"),
    (b"\xff\xfb", 0, "mp3", "audio/mpeg"),
    (b"\xff\xf3", 0, "mp3", "audio/mpeg"),
    (b"OggS", 0, "ogg", "audio/ogg"),
    (b"fLaC", 0, "flac", "audio/flac"),
    (b"ftyp", 4, "m4a", "audio/mp4"),
    (b"\x1a\x45\xdf\xa3", 0, "webm", "audio/webm"),
)
_VIDEO_SIGNATURES = (
    (b"ftyp", 4, "mp4", "video/mp4"),
    (b"\x1a\x45\xdf\xa3", 0, "webm", "video/webm"),
    (b"RIFF", 0, "avi", "video/x-msvideo"),
)


def sniff(head: bytes, table) -> tuple[str, str] | None:
    for sig, offset, ext, mime in table:
        if head[offset : offset + len(sig)] == sig:
            return ext, mime
    return None


def validate_audio(data: bytes) -> tuple[str, str]:
    found = sniff(data[:16], _AUDIO_SIGNATURES)
    if not found:
        raise ValidationFailed("Unsupported audio format. Supported: WAV, MP3, OGG, FLAC, M4A, WEBM")
    return found


def _store_record(db: Session, *, user_id: str, kind: str, rel: str, size: int, sha: str, mime: str,
                  original_name: str | None, meta: dict | None, media_id: str) -> MediaFile:
    s = get_settings()
    record = MediaFile(
        id=media_id, user_id=user_id, kind=kind, storage_path=rel, original_name=(os.path.basename(original_name)[:255] if original_name else None),
        content_type=mime, size_bytes=size, sha256=sha, meta=meta or {},
        expires_at=utcnow() + timedelta(days=s.retention_days),
    )
    db.add(record)
    db.flush()
    return record


def store_bytes(db: Session, *, user_id: str, kind: str, data: bytes, ext: str, mime: str,
                original_name: str | None = None, meta: dict | None = None) -> MediaFile:
    media_id = new_id()
    rel = f"{user_id}/{kind}/{media_id}.{ext}"
    path = safe_join(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _store_record(db, user_id=user_id, kind=kind, rel=rel, size=len(data), sha=sha256_hex(data), mime=mime,
                         original_name=original_name, meta=meta, media_id=media_id)


def store_video(db: Session, *, user_id: str, upload: UploadFile) -> tuple[MediaFile, dict]:
    """Stream a video to disk, enforce size, and verify OpenCV can read it."""
    import cv2

    s = get_settings()
    max_bytes = s.max_video_mb * 1024 * 1024
    head = upload.file.read(16)
    found = sniff(head, _VIDEO_SIGNATURES)
    if not found:
        raise ValidationFailed("Unsupported video format. Supported: MP4/MOV, WEBM, AVI")
    ext, mime = found
    media_id = new_id()
    rel = f"{user_id}/video/{media_id}.{ext}"
    path = safe_join(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    import hashlib

    digest, total = hashlib.sha256(head), len(head)
    try:
        with open(path, "wb") as out:
            out.write(head)
            while True:
                chunk = upload.file.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise PayloadTooLarge(f"Video exceeds the {s.max_video_mb} MB limit")
                digest.update(chunk)
                out.write(chunk)
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                raise ValidationFailed("Video could not be read. The file may be corrupted or use an unsupported codec")
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
            width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            ok, _ = cap.read()
        finally:
            cap.release()
        if not ok or fps <= 0 or frames <= 0:
            raise ValidationFailed("Video has no readable frames")
        duration = frames / fps
        if duration > s.max_video_seconds:
            raise ValidationFailed(f"Video is too long ({duration:.0f}s); maximum is {s.max_video_seconds}s")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    meta = {"fps": round(fps, 3), "frame_count": int(frames), "width": width, "height": height, "duration_s": round(duration, 2)}
    record = _store_record(db, user_id=user_id, kind="video", rel=rel, size=total, sha=digest.hexdigest(), mime=mime,
                           original_name=upload.filename, meta=meta, media_id=media_id)
    return record, meta


def get_owned_media(db: Session, media_id: str, user_id: str) -> MediaFile:
    media = db.get(MediaFile, media_id)
    if not media or media.user_id != user_id:
        raise NotFound("Media not found")
    return media


def media_path(media: MediaFile) -> Path:
    path = safe_join(media.storage_path)
    if not path.exists():
        raise NotFound("Media file is no longer available (it may have passed its retention period)")
    return path


def delete_media(db: Session, media: MediaFile) -> None:
    try:
        safe_join(media.storage_path).unlink(missing_ok=True)
    except ValidationFailed:
        pass
    db.delete(media)


def purge_expired(db: Session) -> int:
    rows = db.scalars(select(MediaFile).where(MediaFile.expires_at.is_not(None), MediaFile.expires_at < utcnow())).all()
    for m in rows:
        delete_media(db, m)
    return len(rows)
