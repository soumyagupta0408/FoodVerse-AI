# FoodVerse AI

A multimodal food-intelligence platform: food recognition, nutrition analysis, freshness assessment, restaurant hygiene monitoring from video, a cooking assistant and personalised meal planning, with a voice/text/photo assistant on top.

**React + TypeScript + Vite + Tailwind** frontend · **FastAPI + SQLAlchemy + Alembic** backend · **PostgreSQL** (SQLite for dev/tests) · **local LLM via Ollama** · **CPU-only** model stack.

> **Read [docs/STATUS.md](docs/STATUS.md) first.** It states exactly what was built, what was tested, and what still needs real models, data, or your machine to verify. This project is **not production-ready** until that list is cleared.

## Quick start (Docker, CPU)

```bash
cp .env.example .env              # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build -d
docker compose exec ollama ollama pull qwen2.5:3b-instruct
docker compose exec backend python scripts/download_models.py     # recogniser, hygiene detector, Whisper (needs internet once)
# app: http://localhost:5173    API docs: http://localhost:8000/docs
```

## Quick start (no Docker)

```bash
# backend (SQLite is fine for development)
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu   # optional: real models
cp ../.env.example .env && sed -i 's#^DATABASE_URL=.*#DATABASE_URL=sqlite:///./foodverse.db#' .env
alembic upgrade head
python scripts/download_models.py          # optional
uvicorn app.main:app --reload              # terminal 1
python -m app.worker                       # terminal 2: processes hygiene videos
# LLM: install Ollama, then `ollama pull qwen2.5:3b-instruct`
cd ../frontend && npm install && npm run dev      # terminal 3 -> http://localhost:5173
```

Without model weights or Ollama the app still runs: features that need a missing model return a clear **503 "model unavailable"** message rather than fake output. Nutrition lookup, auth, history, dashboard and the allergy/diet checks work with no models at all.

## Tests

```bash
make test-backend     # 82 tests, no models or network needed
make test-frontend    # 26 tests + type-check
```

## Documents

| | |
|---|---|
| [docs/STATUS.md](docs/STATUS.md) | Requirement traceability matrix, what was verified, known limitations |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component map, data flows, API summary, data model |
| [docs/MODELS.md](docs/MODELS.md) | Every model: task, licence, size, evaluation, limitations, how to train freshness models |
| [docs/SECURITY.md](docs/SECURITY.md) | Security, privacy, retention, food-safety rules |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Deployment, configuration, troubleshooting |
