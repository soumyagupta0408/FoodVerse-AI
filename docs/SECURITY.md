# Security, privacy and food-safety rules

## Implemented (covered by tests unless noted)

- **Authentication**: Argon2 password hashes; short-lived access JWT; rotating refresh tokens stored server-side and revoked on use/logout; refresh tokens rejected as access tokens.
- **Authorisation**: every query is scoped by `user_id`; other users' resources return 404. Role checks (`admin`) enforced in the backend. Media (photos, video, evidence frames) is served only to its owner via `/media/{id}`.
- **Uploads**: size limits enforced while streaming; magic-byte/format sniffing; Pillow decode check + pixel limit (decompression bombs); OpenCV must read the video; stored under generated names (the original filename is never used in a path); resolved paths must stay inside `MEDIA_ROOT`.
- **Prompt injection**: user text is fenced in `<user_data>` tags with delimiter stripping and a system rule to treat it as data; LLM output is schema-validated and **allergy/diet rules are enforced by code on ingredients and recipe steps, never by the prompt alone**. Limit: matching is by name, so hidden allergens inside compound ingredients are invisible: this caveat is shown on every recipe and plan.
- **Rate limiting**: in-memory per-IP limits on auth and uploads (single process; use a reverse proxy or shared store when running several instances).
- **Errors/logging**: JSON logs with request ids; no stack traces to clients; passwords/tokens are not logged.
- **Secrets**: only from environment; `SECRET_KEY` must be set when `ENV=production`.
- **Retention/deletion**: uploaded media expires after `RETENTION_DAYS` (default 30); the worker purges hourly; users can delete a hygiene job (video + evidence) or their whole account (all rows and files). Audio sent to the assistant is transcribed from a temp file and deleted, never stored.

## Not done / your responsibility

- TLS, HSTS and a reverse proxy are deployment concerns (see OPERATIONS.md).
- The refresh token lives in browser `localStorage` (readable by XSS). Acceptable because the app loads no third-party scripts; move to an httpOnly cookie for stricter setups.
- No email verification or password reset, no account lockout, no audit-log table, no malware scanning of uploads, no encryption at rest beyond your disk/DB.
- Dependency vulnerability scanning was not run (`pip-audit`, `npm audit`).
- Kitchen video can identify people. Get consent and a lawful basis (staff notices, local labour/privacy law) before use; this software does not provide them.

## Food-safety rules the product follows

1. A model prediction is never presented as proof food is safe. Freshness always shows the "visual check cannot show microbiological safety" note.
2. A video finding is a **potential concern for human review**, never proof of misconduct or regulatory non-compliance.
3. Unknown nutrition is shown as unknown, never zero; estimated portions are labelled.
4. The health score is a documented heuristic and not medical advice; meal plans are not disease-specific nutrition.
