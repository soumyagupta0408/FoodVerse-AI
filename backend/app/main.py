import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import request_id_ctx, setup_logging
from app.db.session import get_db, get_sessionmaker

log = logging.getLogger("foodverse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.nutrition_seed_demo:
        from app.services.nutrition import seed_demo

        with get_sessionmaker()() as db:
            try:
                seed_demo(db)
                db.commit()
            except Exception:  # tables may not exist yet before migrations; seeding is retried on next start
                db.rollback()
                log.warning("nutrition demo seed skipped (run migrations first)")
    yield


def create_app() -> FastAPI:
    setup_logging()
    s = get_settings()
    app = FastAPI(title="FoodVerse AI", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    from app.api.routes import auth, food

    api.include_router(auth.router)
    api.include_router(auth.users_router)
    api.include_router(food.food_router)
    api.include_router(food.nutrition_router)
    api.include_router(food.freshness_router)
    api.include_router(food.media_router)
    for mod in ("hygiene", "recipes", "meal_plans", "assistant", "history", "admin"):
        try:
            module = __import__(f"app.api.routes.{mod}", fromlist=["routers"])
        except ModuleNotFoundError as exc:
            if exc.name != f"app.api.routes.{mod}":
                raise
            continue
        for r in module.routers:
            api.include_router(r)
    app.include_router(api)

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}

    return app


app = create_app()
