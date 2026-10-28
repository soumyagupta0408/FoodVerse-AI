from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import NotFound
from app.db.base import utcnow
from app.db.models import Analysis, HygieneFinding, HygieneJob, HygieneReport, MealPlan, Recipe, User
from app.db.session import get_db
from app.services import hygiene as hygiene_svc
from app.services.recognition import get_owned

router = APIRouter(tags=["history"])
KINDS = ("recognition", "nutrition", "freshness", "hygiene", "recipe", "meal_plan")


def _titles(kind: str, row) -> str:
    if kind == "recognition":
        top = (row.result or {}).get("top")
        return (row.corrected or {}).get("food_name") or (top["label"] if top else "No prediction")
    if kind == "nutrition":
        return (row.result or {}).get("food_name") or "Nutrition analysis"
    if kind == "freshness":
        r = row.result or {}
        return f"{(r.get('category') or 'food').capitalize()}: {r.get('display', 'n/a')}"
    if kind == "hygiene":
        return f"Hygiene video ({row.status})"
    if kind == "recipe":
        return row.title
    return f"{row.params.get('days', 1)}-day meal plan ({row.status})"


@router.get("/history")
def history(kind: str | None = Query(default=None), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    kinds = [kind] if kind else list(KINDS)
    if any(k not in KINDS for k in kinds):
        raise NotFound("Unknown history kind")
    need, total, rows = page * page_size, 0, []
    for k in kinds:
        if k in ("recognition", "nutrition", "freshness"):
            model, cond = Analysis, [Analysis.user_id == user.id, Analysis.kind == k]
        else:
            model = {"hygiene": HygieneJob, "recipe": Recipe, "meal_plan": MealPlan}[k]
            cond = [model.user_id == user.id]
        total += db.scalar(select(func.count()).select_from(model).where(*cond))
        for r in db.scalars(select(model).where(*cond).order_by(model.created_at.desc()).limit(need)).all():
            rows.append({"kind": k, "id": r.id, "title": _titles(k, r), "created_at": r.created_at, "status": getattr(r, "status", "completed")})
    rows.sort(key=lambda x: x["created_at"], reverse=True)
    return {"items": rows[(page - 1) * page_size: need], "total": total, "page": page, "page_size": page_size}


@router.get("/dashboard/summary")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every number here is counted from stored rows. Nothing is hard-coded."""
    uid = user.id
    since = utcnow() - timedelta(days=30)
    counts = {k: db.scalar(select(func.count()).select_from(Analysis).where(Analysis.user_id == uid, Analysis.kind == k)) for k in ("recognition", "nutrition", "freshness")}
    counts["hygiene_jobs"] = db.scalar(select(func.count()).select_from(HygieneJob).where(HygieneJob.user_id == uid))
    counts["recipes"] = db.scalar(select(func.count()).select_from(Recipe).where(Recipe.user_id == uid))
    counts["saved_recipes"] = db.scalar(select(func.count()).select_from(Recipe).where(Recipe.user_id == uid, Recipe.saved.is_(True)))
    counts["meal_plans"] = db.scalar(select(func.count()).select_from(MealPlan).where(MealPlan.user_id == uid))

    fresh = db.scalars(select(Analysis).where(Analysis.user_id == uid, Analysis.kind == "freshness", Analysis.created_at >= since)).all()
    fresh_dist: dict[str, int] = {}
    for a in fresh:
        label = (a.result or {}).get("display", "Unknown")
        fresh_dist[label] = fresh_dist.get(label, 0) + 1

    nut = db.scalars(select(Analysis).where(Analysis.user_id == uid, Analysis.kind == "nutrition", Analysis.created_at >= since).order_by(Analysis.created_at)).all()
    trend = [{"date": a.created_at.date().isoformat(), "food": a.result.get("food_name"), "kcal": a.result["nutrients"]["kcal"]}
             for a in nut if a.result.get("matched") and a.result["nutrients"]["kcal"] is not None]

    job_status = dict(db.execute(select(HygieneJob.status, func.count()).where(HygieneJob.user_id == uid).group_by(HygieneJob.status)).all())
    pending_review = db.scalar(select(func.count()).select_from(HygieneFinding).join(HygieneJob).where(
        HygieneJob.user_id == uid, HygieneFinding.status == "potential_violation_observed", HygieneFinding.review_status == "pending"))
    spoiled = sum(1 for a in fresh if (a.result or {}).get("state") == "spoiled")
    alerts = []
    if pending_review:
        alerts.append({"type": "hygiene_review", "message": f"{pending_review} hygiene finding(s) are waiting for human review."})
    if spoiled:
        alerts.append({"type": "freshness", "message": f"{spoiled} item(s) were assessed as spoiled in the last 30 days."})
    failed_jobs = job_status.get("failed", 0)
    if failed_jobs:
        alerts.append({"type": "job_failed", "message": f"{failed_jobs} hygiene job(s) failed. Open them for the reason."})
    return {"counts": counts, "freshness_last_30d": fresh_dist, "nutrition_trend_30d": trend, "hygiene_job_status": job_status, "alerts": alerts}


def _analysis_markdown(a: Analysis) -> str:
    lines = [f"# FoodVerse AI: {a.kind} analysis", f"- ID: {a.id}", f"- Created: {a.created_at.isoformat()}", f"- Model: {a.model_name or 'n/a'} {a.model_version or ''}", ""]
    if a.corrected:
        lines.append(f"**User correction:** {a.corrected}\n")
    for k, v in (a.result or {}).items():
        lines.append(f"- **{k}**: {v}")
    lines.append("\n_Automated estimate. Not medical or food-safety advice._")
    return "\n".join(lines)


@router.get("/exports/analysis/{analysis_id}")
def export_analysis(analysis_id: str, format: str = Query("json", pattern="^(json|md)$"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = get_owned(db, analysis_id, user)
    if format == "md":
        return PlainTextResponse(_analysis_markdown(a), media_type="text/markdown")
    return {"id": a.id, "kind": a.kind, "created_at": a.created_at, "input": a.input, "result": a.result, "corrected": a.corrected,
            "model": {"name": a.model_name, "version": a.model_version}}


@router.get("/exports/hygiene/{report_id}")
def export_hygiene(report_id: str, format: str = Query("json", pattern="^(json|md)$"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(HygieneReport, report_id)
    if not r or r.user_id != user.id:
        raise NotFound("Report not found")
    data = hygiene_svc.report_dict(db, r.job)
    if format == "json":
        return data
    lines = [f"# Hygiene observation report {data['report_id']}", f"_{data['disclaimer']}_", ""]
    for f in data["findings"]:
        lines.append(f"## {f['label']}: {f['status'].replace('_', ' ')}")
        if f["confidence"] is not None:
            lines.append(f"- Confidence: {f['confidence']}")
        if f["timestamp_s"] is not None:
            lines.append(f"- Evidence at {f['timestamp_s']:.1f}s (media {f['evidence_media_id']})")
        lines += [f"- Potential concern: {f['potential_concern'] or 'none'}", f"- Suggested follow-up: {f['suggested_follow_up']}", f"- Human review: {f['review_status']}", ""]
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


routers = [router]
