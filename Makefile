.PHONY: backend-setup test-backend test-frontend dev-backend dev-worker dev-frontend migrate
backend-setup:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
test-backend:
	cd backend && . .venv/bin/activate && python -m pytest -q
test-frontend:
	cd frontend && npm test && npm run typecheck
migrate:
	cd backend && . .venv/bin/activate && alembic upgrade head
dev-backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000
dev-worker:
	cd backend && . .venv/bin/activate && python -m app.worker
dev-frontend:
	cd frontend && npm run dev
