from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import NotFound
from app.core.ratelimit import upload_limiter
from app.db.models import HygieneFinding, HygieneJob, HygieneReport, User
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.hygiene import JobOut, ReviewIn
from app.services import hygiene as svc

router = APIRouter(prefix="/hygiene", tags=["restaurant hygiene"])


def _job_out(job: HygieneJob) -> dict:
    return {"id": job.id, "status": job.status, "progress": job.progress, "video_meta": job.video_meta, "error": job.error,
            "created_at": job.created_at, "started_at": job.started_at, "finished_at": job.finished_at,
            "report_id": job.report.id if job.report else None}


@router.post("/analyze", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(upload_limiter)])
def analyze(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Validates the video and queues a background job. Poll /hygiene/jobs/{id}."""
    return _job_out(svc.create_job(db, user, file))


@router.get("/jobs", response_model=Page[JobOut])
def list_jobs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(HygieneJob).where(HygieneJob.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(HygieneJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[_job_out(j) for j in rows], total=total, page=page, page_size=page_size)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _job_out(svc.get_owned_job(db, user, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _job_out(svc.cancel(db, svc.get_owned_job(db, user, job_id)))


@router.get("/reports/{report_id}")
def get_report(report_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(HygieneReport, report_id)
    if not r or r.user_id != user.id:
        raise NotFound("Report not found")
    return svc.report_dict(db, r.job)


@router.patch("/findings/{finding_id}/review")
def review_finding(finding_id: str, body: ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(HygieneFinding, finding_id)
    if not f or f.job.user_id != user.id:
        raise NotFound("Finding not found")
    f.review_status, f.review_note = body.review_status, body.note
    return {"id": f.id, "review_status": f.review_status, "review_note": f.review_note}


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete a job, its report, evidence frames and the uploaded video."""
    from app.db.models import MediaFile
    from app.services import storage

    job = svc.get_owned_job(db, user, job_id)
    ids = {job.media_id, *(f.evidence_media_id for f in job.findings if f.evidence_media_id)}
    db.delete(job)
    db.flush()
    for mid in ids:
        m = db.get(MediaFile, mid)
        if m:
            storage.delete_media(db, m)


routers = [router]
