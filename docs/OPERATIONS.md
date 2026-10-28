# Operations

## Configuration
All settings come from environment variables (see `.env.example`; it lists only variables the code reads, plus `POSTGRES_PASSWORD` for compose). Required in production: `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS` (your frontend origin). Set `NUTRITION_SEED_DEMO=false` once real nutrition data is loaded.

## Hardware (CPU only)
16 GB RAM is comfortable: a 3B LLM (~3 GB) plus the food model, OWL-ViT and Whisper base, which load lazily on first use. Expect slow generation: a recipe about 30-90 s; a 3-meal day about 1-3 min; a week 10+ min on a 3B model. Hygiene at 1 frame/s with OWL-ViT is about 2-6 s per frame, so a 10-minute clip takes 20-60 min: raise `HYGIENE_FRAME_INTERVAL_S` (e.g. 3) or use shorter clips. These are estimates, not measurements.

## Costs
No paid services. All models are local. Disk: about 4-6 GB for models; media grows with uploads (retention default 30 days).

## Deploying
1. Provision Postgres 16; set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`.
2. `alembic upgrade head` (the backend container does this on start).
3. Run **both** the API (`uvicorn app.main:app`) and the worker (`python -m app.worker`). Without the worker, hygiene jobs stay `queued`.
4. Put both behind HTTPS (Caddy/nginx/traefik). Build the frontend with `VITE_API_URL=https://api.example.com`.
5. Mount a persistent volume at `MEDIA_ROOT` shared by API and worker (or swap `services/storage.py` for object storage).
6. Load nutrition data: `python scripts/load_nutrition.py file.csv --source "USDA SR Legacy" --verified --replace`.
7. Create an admin: `python scripts/make_admin.py you@example.com`.

Health: `GET /health` (liveness), `GET /health/ready` (database). Logs are JSON on stdout.

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `503 model_unavailable` on recognise | `pip install -r requirements-ml.txt` and `python scripts/download_models.py`; check the `RECOGNIZER_MODEL` id |
| `503 llm_unavailable` | Start Ollama; `ollama pull $OLLAMA_MODEL`; check `OLLAMA_URL` (in Docker use `http://ollama:11434`) |
| LLM timeouts | raise `LLM_TIMEOUT_SECONDS`, use a smaller model, shorter requests |
| Hygiene job stuck `queued` | worker not running; check its logs. Jobs left `running` by a crash are failed on worker restart |
| Hygiene job `failed` with a detector message | detector model not downloaded |
| Freshness always "Unable to determine" | no model for that category in `FRESHNESS_MODELS_DIR`; see MODELS.md |
| `413` on upload | raise `MAX_*_MB` (and your proxy's body limit) |
| Browser CORS errors | add the frontend origin to `CORS_ORIGINS` |
| Microphone button does nothing | needs HTTPS or localhost, and permission |
| Video "could not be read" | codec unsupported by OpenCV: re-encode to H.264 MP4 |
