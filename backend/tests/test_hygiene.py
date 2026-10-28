import io
import os

import cv2
import numpy as np

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.ml import registry
from app.ml.base import FrameObservation
from app.services import hygiene as svc
from app.worker import recover_stuck, run_once


def make_video(seconds=10, fps=10, size=(96, 96)) -> bytes:
    path = os.path.join(get_settings().media_root.parent, f"v{seconds}{fps}.avi")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    rng = np.random.default_rng(0)
    for _ in range(seconds * fps):
        w.write(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    w.release()
    return open(path, "rb").read()


class FakeDetector:
    name, version, supported_indicators = "fake-detector", "test", ("hair_cap", "gloves")

    def __init__(self, persons=1, detected=None, boom=False):
        self.persons, self.detected, self.boom = persons, detected if detected is not None else {"hair_cap": 0.8}, boom

    def observe(self, frame, ts):
        if self.boom:
            raise RuntimeError("detector exploded")
        return FrameObservation(timestamp_s=ts, persons=self.persons, detected=dict(self.detected),
                                boxes=[{"label": "person", "score": 0.9, "box": [5, 5, 50, 80]}] if self.persons else [])


def submit(client, auth, data=None, name="kitchen.avi"):
    return client.post("/api/v1/hygiene/analyze", headers=auth, files={"file": (name, io.BytesIO(data or make_video()), "video/x-msvideo")})


def test_judge_rules():
    S = svc.IndicatorStats
    assert svc.judge(S(person_frames=2, positive_frames=0), True)["status"] == "insufficient_evidence"
    assert svc.judge(S(person_frames=10, positive_frames=9, confidences=[0.8] * 9), True)["status"] == "observed_compliance"
    v = svc.judge(S(person_frames=10, positive_frames=0), True)
    assert v["status"] == "potential_violation_observed" and v["confidence"] <= svc.MAX_CONFIDENCE_FOR_ZERO_SHOT and "out of view" in v["concern"]
    assert svc.judge(S(person_frames=10, positive_frames=4, confidences=[0.5] * 4), True)["status"] == "insufficient_evidence"
    assert svc.judge(S(person_frames=10, positive_frames=10), False)["status"] == "insufficient_evidence"


def test_one_missing_frame_is_not_a_violation():
    S = svc.IndicatorStats
    assert svc.judge(S(person_frames=20, positive_frames=19, confidences=[0.7] * 19), True)["status"] == "observed_compliance"


def test_full_job_lifecycle_with_evidence(client, auth):
    registry.set_override("hygiene", FakeDetector())
    r = submit(client, auth)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    job = r.json()
    assert job["video_meta"]["duration_s"] == 10.0
    assert run_once() is True and run_once() is False
    done = client.get(f"/api/v1/hygiene/jobs/{job['id']}", headers=auth).json()
    assert done["status"] == "completed" and done["progress"] == 1.0 and done["report_id"]
    rep = client.get(f"/api/v1/hygiene/reports/{done['report_id']}", headers=auth).json()
    by = {f["indicator"]: f for f in rep["findings"]}
    assert by["hair_cap"]["status"] == "observed_compliance" and by["hair_cap"]["evidence_media_id"]
    assert by["gloves"]["status"] == "potential_violation_observed" and by["gloves"]["evidence_media_id"] and by["gloves"]["review_status"] == "pending"
    for ind in ("handwashing", "surface_cleanliness", "raw_ready_separation", "cross_contamination"):
        assert by[ind]["status"] == "insufficient_evidence" and "No detector" in by[ind]["potential_concern"]
    assert "not a food-safety inspection" in rep["disclaimer"] and rep["summary"]["frames_analysed"] == 10
    ev = client.get(f"/api/v1/media/{by['gloves']['evidence_media_id']}", headers=auth)
    assert ev.status_code == 200 and ev.headers["content-type"] == "image/jpeg"
    rv = client.patch(f"/api/v1/hygiene/findings/{by['gloves']['id']}/review", headers=auth, json={"review_status": "dismissed", "note": "out of frame"})
    assert rv.json()["review_status"] == "dismissed"


def test_no_people_means_insufficient_evidence_not_violation(client, auth):
    registry.set_override("hygiene", FakeDetector(persons=0, detected={}))
    submit(client, auth)
    run_once()
    jid = client.get("/api/v1/hygiene/jobs", headers=auth).json()["items"][0]
    rep = client.get(f"/api/v1/hygiene/reports/{jid['report_id']}", headers=auth).json()
    assert {f["status"] for f in rep["findings"]} == {"insufficient_evidence"}


def test_isolation(client, auth, auth_b):
    registry.set_override("hygiene", FakeDetector())
    jid = submit(client, auth).json()["id"]
    run_once()
    rid = client.get(f"/api/v1/hygiene/jobs/{jid}", headers=auth).json()["report_id"]
    rep = client.get(f"/api/v1/hygiene/reports/{rid}", headers=auth).json()
    fid, mid = rep["findings"][1]["id"], next(f["evidence_media_id"] for f in rep["findings"] if f["evidence_media_id"])
    for url in (f"/api/v1/hygiene/jobs/{jid}", f"/api/v1/hygiene/reports/{rid}", f"/api/v1/media/{mid}"):
        assert client.get(url, headers=auth_b).status_code == 404
    assert client.patch(f"/api/v1/hygiene/findings/{fid}/review", headers=auth_b, json={"review_status": "confirmed"}).status_code == 404
    assert client.post(f"/api/v1/hygiene/jobs/{jid}/cancel", headers=auth_b).status_code == 404
    assert client.delete(f"/api/v1/hygiene/jobs/{jid}", headers=auth_b).status_code == 404
    assert client.get("/api/v1/hygiene/jobs", headers=auth_b).json()["total"] == 0


def test_upload_validation(client, auth, monkeypatch):
    assert submit(client, auth, b"not a video at all").status_code == 422
    assert submit(client, auth, b"RIFF" + b"\x00" * 100).status_code == 422  # right magic, unreadable
    monkeypatch.setattr(get_settings(), "max_video_seconds", 5)
    assert submit(client, auth).status_code == 422  # too long
    monkeypatch.setattr(get_settings(), "max_video_seconds", 900)
    monkeypatch.setattr(get_settings(), "max_video_mb", 0)
    assert submit(client, auth).status_code == 413
    assert client.get("/api/v1/hygiene/jobs", headers=auth).json()["total"] == 0


def test_detector_not_installed_fails_job_with_clear_message(client, auth):
    jid = submit(client, auth).json()["id"]  # real (unavailable) detector: transformers is not installed here
    run_once()
    job = client.get(f"/api/v1/hygiene/jobs/{jid}", headers=auth).json()
    assert job["status"] == "failed" and "transformers" in job["error"] and job["report_id"] is None


def test_detector_crash_fails_job(client, auth):
    registry.set_override("hygiene", FakeDetector(boom=True))
    jid = submit(client, auth).json()["id"]
    run_once()
    job = client.get(f"/api/v1/hygiene/jobs/{jid}", headers=auth).json()
    assert job["status"] == "failed" and "exploded" in job["error"]


def test_cancel_queued_and_running(client, auth):
    registry.set_override("hygiene", FakeDetector())
    a = submit(client, auth).json()["id"]
    assert client.post(f"/api/v1/hygiene/jobs/{a}/cancel", headers=auth).json()["status"] == "cancelled"
    assert run_once() is False
    assert client.post(f"/api/v1/hygiene/jobs/{a}/cancel", headers=auth).status_code == 409
    b = submit(client, auth).json()["id"]
    from app.db.models import HygieneJob

    with get_sessionmaker()() as db:  # simulate: running, then the user asks to cancel
        j = db.get(HygieneJob, b)
        j.status, j.cancel_requested = "running", True
        db.commit()
    svc.process_job(get_sessionmaker(), b)
    assert client.get(f"/api/v1/hygiene/jobs/{b}", headers=auth).json()["status"] == "cancelled"


def test_worker_recovers_stuck_jobs(client, auth):
    jid = submit(client, auth).json()["id"]
    from app.db.models import HygieneJob

    with get_sessionmaker()() as db:
        db.get(HygieneJob, jid).status = "running"
        db.commit()
    assert recover_stuck(get_sessionmaker()) == 1
    assert client.get(f"/api/v1/hygiene/jobs/{jid}", headers=auth).json()["status"] == "failed"


def test_delete_job_removes_files(client, auth):
    registry.set_override("hygiene", FakeDetector())
    jid = submit(client, auth).json()["id"]
    run_once()
    root = get_settings().media_root
    before = sum(len(f) for _, _, f in os.walk(root))
    assert client.delete(f"/api/v1/hygiene/jobs/{jid}", headers=auth).status_code == 204
    after = sum(len(f) for _, _, f in os.walk(root))
    assert after < before and client.get(f"/api/v1/hygiene/jobs/{jid}", headers=auth).status_code == 404
