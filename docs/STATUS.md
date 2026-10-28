# Implementation status

Statuses use the master prompt's scale: **Implemented and tested** · **Implemented but not fully tested** · **Partially implemented** · **Blocked** · **Not implemented**.

"Tested" means automated tests that I ran: **backend 82 passed (pytest)**, **frontend 26 passed (vitest) + clean TypeScript check + production build**. Those tests use stand-ins for the ML models and the LLM (none could be downloaded in the build environment), so they prove wiring, validation, calculations, persistence, safety rules and access control: **not model accuracy**. One live check was also run: a real `uvicorn` server on an Alembic-migrated SQLite database answered health, register, nutrition and OpenAPI correctly, and returned the intended 503 for recognition and recipes when no model/LLM was present.

## Requirement traceability

| # | Requirement | Where | Verification run | Status |
|---|---|---|---|---|
| 1 | Food recognition (upload, validation, top-k + confidence, correction, no fake output) | `services/recognition.py`, `ml/recognizers.py` | API tests with a stub model; 503 when no model | **Implemented but not fully tested**: real model never loaded |
| 2 | Nutrition (per-100 g → portion, unknowns stay null, source shown, health score documented, manual override) | `services/nutrition*.py` | calculation, null-vs-zero, default-serving, no-match tests | **Implemented and tested** with *demo* data; real USDA/IFCT data not loaded (**blocked on you**) |
| 3 | Freshness (3 display classes + unable-to-determine, quality check, safety note) | `services/freshness.py`, `ml/freshness_models.py` | tests with stub classifier incl. low confidence, bad quality, unsupported category | **Partially implemented**: no trained model exists; training script unexecuted |
| 4 | Hygiene monitoring (async job, frame sampling, temporal judging, evidence, human review, cancel/fail, retention) | `services/hygiene.py`, `worker.py` | real synthetic video through the real worker with a stub detector; judge rules unit-tested | **Partially implemented**: only gloves & hair-cap attempted, zero-shot detector unvalidated and never loaded; other four indicators report "insufficient evidence" |
| 5 | Cooking assistant (structured recipes, deterministic allergy/exclusion checks, scale, substitute, revise, search, save) | `services/recipes.py` | allergy retry/reject, hidden-in-steps, injection fencing, scaling, substitution tests with a fake LLM | **Implemented but not fully tested**: never run against a real LLM |
| 6 | Meal planning (daily/weekly, validated, replace slot, shopping list, feedback, explanations) | `services/meal_plans.py` | constraint enforcement, fallback, failure-not-stuck, shopping aggregation tests | **Implemented but not fully tested**: never run against a real LLM; weekly plans will be slow on CPU |
| 7 | Multimodal layer (image, video, audio, text, image+text) | `services/assistant.py`, `ml/stt.py` | text/image+text/audio routes tested with stub STT | **Implemented but not fully tested**: Whisper never loaded; no native real-time audio/video understanding is claimed or built |
| 8 | LLM reasoning layer (provider abstraction, schema validation, retries, timeouts, grounding, source labels) | `llm/*` | malformed output → 502, unavailable → 503, retry-with-feedback | **Implemented but not fully tested** (Ollama never contacted) |
| 9 | Dashboard, history, exports | `api/routes/history.py`, `pages/Dashboard.tsx`, `History.tsx` | real counts, empty states, pagination, isolation | **Implemented and tested** (PDF export not built: JSON and Markdown only) |
| 10 | Auth, roles, profile, deletion | `api/routes/auth.py`, `deps.py` | register/login/refresh rotation/logout, role guard, isolation, account deletion | **Implemented and tested** (no email verification / password reset) |
| 11 | Database + migrations | `db/models.py`, `alembic/` | upgrade → downgrade → upgrade on SQLite; all tests on SQLite | **Implemented but not fully tested**: **never run on PostgreSQL** |
| 12 | Frontend (all pages wired to the API, loading/error/empty states, accessible forms) | `frontend/src` | 26 component/flow tests with mocked fetch; type-check; production build | **Implemented but not fully tested**: never opened in a real browser, no Playwright E2E, no accessibility audit |
| 13 | Security controls | see SECURITY.md | upload, path, token, isolation, rate-limit tests | **Implemented but not fully tested**: no dependency audit, no penetration test |
| 14 | Docker Compose / CI | `docker-compose.yml`, Dockerfiles, `.github/workflows/ci.yml` | none | **Implemented but not tested**: Docker and CI were never run (no Docker in the build environment) |
| 15 | Integration journeys (the 8 in the spec) | `tests/test_e2e_journeys.py` | one test walks all 8 through HTTP with stand-in models | **Implemented and tested** (stand-ins, as noted) |
| 16 | Model provenance & evaluation docs | `docs/MODELS.md` | n/a | Documented; **no model was evaluated** |

## What you must do before this is usable for real

1. Run `python scripts/download_models.py` and confirm each Hugging Face id actually loads (`nateraw/food`, `google/owlvit-base-patch32`; Whisper). If an id is wrong, change it in `.env`.
2. `ollama pull qwen2.5:3b-instruct` and try the recipe and meal-plan flows. Check the JSON-schema output works with your model; try another model if not.
3. Load real nutrition data (`scripts/load_nutrition.py`). The bundled 12 foods are **approximate demo values, labelled unverified**; the UI shows that.
4. Obtain and **license-check** freshness datasets, train per-category models, read `metrics.json`.
5. Test on PostgreSQL and in Docker; run `make test-backend test-frontend` on your machine; click through the app in a browser.
6. Evaluate hygiene findings against human-labelled kitchen clips before showing them to anyone. Consider training a dedicated glove/cap detector.
7. Run `pip-audit` and `npm audit`; set up HTTPS.

## Known limitations

- Recognition: single label, 101 Western-leaning classes, no multi-item detection.
- Allergy checks work on ingredient *names*; hidden allergens in packaged products are not detectable (caveat shown in the UI).
- Nutrition fuzzy matching can pick the wrong record; the match score and a warning are shown below 95 %.
- Meal-plan nutrition covers only database-matched ingredients, reported as a lower bound when incomplete; calorie goals are reported against, not enforced.
- Generation and video analysis are slow on CPU (see OPERATIONS.md); the meal-plan background task runs inside the API process.
- In-memory rate limiter is per process. Refresh token is in `localStorage`.
- The frontend bundle is one ~860 kB chunk (not code-split).
- Not built: PDF export, email flows, audit log, object-storage backend, Redis queue, real-time audio/video streaming, multi-item food detection, portion estimation from images.

## Deliverables checklist (master prompt §26)

Frontend ✔ · Backend ✔ · Schema & migration ✔ (SQLite-verified) · AI/ML adapters ✔ (weights not bundled) · Provenance doc ✔ · API docs ✔ (OpenAPI at `/docs`, summary in ARCHITECTURE.md) · `.env.example` ✔ · Dependency files ✔ (+ `requirements.lock.txt` snapshot) · Tests ✔ with recorded results above · Diagrams ✔ (Mermaid) · Install/deploy/troubleshooting ✔ · Security & privacy ✔ · Traceability matrix ✔ · Status report ✔ · Limitations ✔.
