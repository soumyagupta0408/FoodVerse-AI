"""Background worker: claims queued hygiene jobs from the database and processes them.

Run:  python -m app.worker
No Redis needed: the job table is the queue. Safe with several workers on PostgreSQL (SKIP LOCKED).
"""
import logging
import signal
import time

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.base import utcnow
from app.db.models import HygieneJob
from app.db.session import get_sessionmaker
from app.services import hygiene, storage

log = logging.getLogger("foodverse.worker")
_running = True


def claim_next(session_factory) -> str | None:
    with session_factory() as db:
        q = select(HygieneJob.id).where(HygieneJob.status == "queued").order_by(HygieneJob.created_at).limit(1)
        if db.bind.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        job_id = db.scalar(q)
        if not job_id:
            return None
        claimed = db.execute(update(HygieneJob).where(HygieneJob.id == job_id, HygieneJob.status == "queued").values(status="running", started_at=utcnow()))
        db.commit()
        return job_id if claimed.rowcount == 1 else None


def recover_stuck(session_factory) -> int:
    """On start-up, jobs left 'running' by a crashed worker are failed so users are not left waiting forever."""
    with session_factory() as db:
        res = db.execute(update(HygieneJob).where(HygieneJob.status == "running").values(status="failed", error="Worker stopped while processing; please resubmit.", finished_at=utcnow()))
        db.commit()
        return res.rowcount


def run_once(session_factory=None) -> bool:
    sf = session_factory or get_sessionmaker()
    job_id = claim_next(sf)
    if not job_id:
        return False
    hygiene.process_job(sf, job_id)
    return True


def main() -> None:
    setup_logging()
    sf = get_sessionmaker()
    log.info("worker started; recovered %s stuck job(s)", recover_stuck(sf))
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("_running", False))
    last_purge = 0.0
    while _running:
        if time.monotonic() - last_purge > 3600:
            with sf() as db:
                log.info("retention purge removed %s expired media file(s)", storage.purge_expired(db))
                db.commit()
            last_purge = time.monotonic()
        if not run_once(sf):
            time.sleep(2)


if __name__ == "__main__":
    main()
