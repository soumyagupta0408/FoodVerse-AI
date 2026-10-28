"""Restaurant hygiene analysis: frame sampling -> detection -> temporal aggregation -> evidence-backed report.

Principles (from the spec): a missing detection in one frame is never a violation; findings are
"potential" and need human review; no regulatory or compliance claims are made.
"""
import logging
from dataclasses import dataclass, field

import cv2
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound
from app.db.base import utcnow
from app.db.models import HygieneFinding, HygieneJob, HygieneReport, MediaFile, User
from app.ml.base import FrameObservation, HygieneDetector
from app.ml.registry import get_hygiene_detector
from app.services import storage

log = logging.getLogger("foodverse.hygiene")

MIN_PERSON_FRAMES = 5          # need at least this many frames with a person visible to judge anything
COMPLIANT_RATIO = 0.7          # share of person-frames with positive evidence to call it observed compliance
VIOLATION_RATIO = 0.1          # at or below this share (with enough frames) we flag a potential violation
MAX_CONFIDENCE_FOR_ZERO_SHOT = 0.6  # zero-shot detectors are unvalidated: cap the confidence we report

INDICATORS = {
    "hair_cap": "Hair cap / hairnet visible",
    "gloves": "Gloves visible on hands",
    "handwashing": "Handwashing observed",
    "surface_cleanliness": "Visible surface cleanliness",
    "raw_ready_separation": "Raw vs ready-to-eat separation",
    "cross_contamination": "Potential cross-contamination events",
}
DISCLAIMER = ("This is an automated, unvalidated observation of limited video evidence. It is not a food-safety inspection, "
              "does not establish that anyone broke a rule, and does not indicate regulatory compliance. Every finding needs human review.")


@dataclass
class IndicatorStats:
    person_frames: int = 0
    positive_frames: int = 0
    best_positive: tuple[float, float, int] | None = None   # (confidence, timestamp, frame_index)
    first_negative: tuple[float, int] | None = None          # (timestamp, frame_index) with a person but no detection
    confidences: list[float] = field(default_factory=list)


def judge(stats: IndicatorStats, supported: bool) -> dict:
    """Pure temporal decision for one indicator. Unit-tested without any model."""
    if not supported:
        return {"status": "insufficient_evidence", "confidence": None, "concern": "No detector is configured for this indicator, so it was not assessed.",
                "follow_up": "Assess this manually or add a detector for it."}
    if stats.person_frames < MIN_PERSON_FRAMES:
        return {"status": "insufficient_evidence", "confidence": None,
                "concern": f"A person was visible in only {stats.person_frames} sampled frame(s); at least {MIN_PERSON_FRAMES} are needed to judge this indicator.",
                "follow_up": "Provide footage where staff are clearly visible for longer, or review the video manually."}
    ratio = stats.positive_frames / stats.person_frames
    mean_conf = sum(stats.confidences) / len(stats.confidences) if stats.confidences else 0.0
    if ratio >= COMPLIANT_RATIO:
        return {"status": "observed_compliance", "confidence": round(min(mean_conf, MAX_CONFIDENCE_FOR_ZERO_SHOT), 3), "ratio": round(ratio, 3),
                "concern": None, "follow_up": "No action suggested from this footage. Spot-check the evidence frame."}
    if ratio <= VIOLATION_RATIO:
        return {"status": "potential_violation_observed", "confidence": round(min(0.5 + (1 - ratio) * 0.1, MAX_CONFIDENCE_FOR_ZERO_SHOT), 3), "ratio": round(ratio, 3),
                "concern": f"The item was detected in {stats.positive_frames} of {stats.person_frames} frames where a person was visible. "
                           "It may simply be out of view or missed by the detector.",
                "follow_up": "Review the evidence frame and the surrounding video, then confirm or dismiss this finding."}
    return {"status": "insufficient_evidence", "confidence": None, "ratio": round(ratio, 3),
            "concern": f"Mixed evidence: detected in {stats.positive_frames} of {stats.person_frames} frames where a person was visible.",
            "follow_up": "Review the video manually."}


def sample_frames(path: str, interval_s: float, should_stop):
    """Yield (timestamp_s, frame_bgr, index, total_samples). Stops early when should_stop() is true."""
    cap = cv2.VideoCapture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, int(round(fps * interval_s)))
        samples = max(1, total // step)
        idx = 0
        for n in range(samples):
            if should_stop():
                return
            cap.set(cv2.CAP_PROP_POS_FRAMES, n * step)
            ok, frame = cap.read()
            if not ok:
                break
            yield n * step / fps, frame, idx, samples
            idx += 1
    finally:
        cap.release()


def _evidence(db: Session, job: HygieneJob, frame, observation: FrameObservation, label: str) -> str:
    img = frame.copy()
    for b in observation.boxes:
        x0, y0, x1, y1 = (int(v) for v in b["box"])
        cv2.rectangle(img, (x0, y0), (x1, y1), (0, 200, 0), 2)
        cv2.putText(img, f"{b['label']} {b['score']:.2f}", (x0, max(12, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1)
    cv2.putText(img, f"{label} t={observation.timestamp_s:.1f}s", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    media = storage.store_bytes(db, user_id=job.user_id, kind="evidence", data=buf.tobytes(), ext="jpg", mime="image/jpeg",
                                meta={"job_id": job.id, "timestamp_s": round(observation.timestamp_s, 2)})
    return media.id


def create_job(db: Session, user: User, upload) -> HygieneJob:
    media, meta = storage.store_video(db, user_id=user.id, upload=upload)
    job = HygieneJob(user_id=user.id, media_id=media.id, status="queued", video_meta=meta,
                     params={"frame_interval_s": get_settings().hygiene_frame_interval_s})
    db.add(job)
    db.flush()
    return job


def get_owned_job(db: Session, user: User, job_id: str) -> HygieneJob:
    job = db.get(HygieneJob, job_id)
    if not job or job.user_id != user.id:
        raise NotFound("Hygiene job not found")
    return job


def cancel(db: Session, job: HygieneJob) -> HygieneJob:
    if job.status in ("completed", "failed", "cancelled"):
        raise Conflict(f"Job already {job.status}")
    if job.status == "queued":
        job.status, job.finished_at = "cancelled", utcnow()
    else:
        job.cancel_requested = True  # the worker stops at the next frame
    return job


def process_job(session_factory, job_id: str, detector: HygieneDetector | None = None) -> None:
    """Run one job end to end. Always leaves the job in a terminal state (completed/failed/cancelled)."""
    with session_factory() as db:
        job = db.get(HygieneJob, job_id)
        if not job or job.status not in ("queued", "running"):
            return
        job.status, job.started_at = "running", utcnow()
        db.commit()
        try:
            detector = detector or get_hygiene_detector()
            media = db.get(MediaFile, job.media_id)
            path = str(storage.media_path(media))
            stats = {k: IndicatorStats() for k in detector.supported_indicators}
            frame_bank: dict[str, dict] = {}   # indicator -> {"positive": (conf, frame, obs), "negative": (frame, obs)}
            interval = float(job.params.get("frame_interval_s", 1.0))
            analysed = 0

            def stop():
                # a plain column query: does not refresh (and so discard) the job's pending progress
                return bool(db.scalar(select(HygieneJob.cancel_requested).where(HygieneJob.id == job_id)))

            for ts, frame, i, total in sample_frames(path, interval, stop):
                obs = detector.observe(frame, ts)
                analysed += 1
                if obs.persons > 0:
                    for ind, st in stats.items():
                        st.person_frames += 1
                        conf = obs.detected.get(ind)
                        bank = frame_bank.setdefault(ind, {})
                        if conf is not None:
                            st.positive_frames += 1
                            st.confidences.append(conf)
                            if st.best_positive is None or conf > st.best_positive[0]:
                                st.best_positive = (conf, ts, i)
                                bank["positive"] = (frame.copy(), obs)
                        elif st.first_negative is None:
                            st.first_negative = (ts, i)
                            bank["negative"] = (frame.copy(), obs)
                job.progress = round((i + 1) / total, 3)
                if i % 5 == 0:
                    db.commit()
            db.refresh(job)
            if job.cancel_requested:
                job.status, job.finished_at = "cancelled", utcnow()
                db.commit()
                return
            _write_report(db, job, detector, stats, frame_bank, analysed)
            job.status, job.progress, job.finished_at = "completed", 1.0, utcnow()
        except Exception as exc:  # noqa: BLE001 - recorded on the job and visible to the user
            log.exception("hygiene job %s failed", job_id)
            db.rollback()
            job = db.get(HygieneJob, job_id)
            job.status, job.error, job.finished_at = "failed", getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"[:500], utcnow()
        db.commit()


def _write_report(db: Session, job: HygieneJob, detector, stats, frame_bank, analysed: int) -> None:
    findings = []
    for ind in INDICATORS:
        st = stats.get(ind)
        verdict = judge(st or IndicatorStats(), supported=st is not None)
        bank = frame_bank.get(ind, {})
        ts, evidence_id = None, None
        if verdict["status"] == "observed_compliance" and "positive" in bank:
            frame, obs = bank["positive"]
            ts, evidence_id = obs.timestamp_s, _evidence(db, job, frame, obs, f"{ind}: detected")
        elif verdict["status"] == "potential_violation_observed" and "negative" in bank:
            frame, obs = bank["negative"]
            ts, evidence_id = obs.timestamp_s, _evidence(db, job, frame, obs, f"{ind}: not detected")
        f = HygieneFinding(job_id=job.id, indicator=ind, status=verdict["status"], confidence=verdict["confidence"], timestamp_s=ts,
                           concern=verdict["concern"], suggested_follow_up=verdict["follow_up"], evidence_media_id=evidence_id,
                           detail={"label": INDICATORS[ind], "person_frames": st.person_frames if st else None,
                                   "positive_frames": st.positive_frames if st else None, "ratio": verdict.get("ratio")})
        db.add(f)
        findings.append(f)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    db.add(HygieneReport(job_id=job.id, user_id=job.user_id, summary={
        "frames_analysed": analysed, "frame_interval_s": job.params.get("frame_interval_s"), "detector": detector.name,
        "detector_version": detector.version, "status_counts": counts, "disclaimer": DISCLAIMER,
        "reliability": "Zero-shot detection is not validated on kitchen footage. Treat all results as leads for a human reviewer.",
    }))
    db.flush()


def report_dict(db: Session, job: HygieneJob) -> dict:
    r = job.report
    return {
        "report_id": r.id if r else None, "job_id": job.id, "status": job.status, "video": job.video_meta, "created_at": job.created_at,
        "summary": r.summary if r else None, "disclaimer": DISCLAIMER,
        "findings": [{"id": f.id, "indicator": f.indicator, "label": f.detail.get("label"), "status": f.status, "confidence": f.confidence,
                      "timestamp_s": f.timestamp_s, "potential_concern": f.concern, "suggested_follow_up": f.suggested_follow_up,
                      "evidence_media_id": f.evidence_media_id, "review_status": f.review_status, "review_note": f.review_note,
                      "detail": f.detail} for f in job.findings],
    }
