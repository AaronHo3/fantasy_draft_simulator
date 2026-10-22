.PHONY: install dev backend frontend demo refresh test test-backend test-frontend bench export import typecheck openapi lint link sync season

SESSION ?=
FILE ?=
LEAGUE ?=
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173

install:
	cd backend && uv sync
	cd frontend && npm ci

dev:
	@echo "Starting backend on http://127.0.0.1:$(BACKEND_PORT) and frontend on http://127.0.0.1:$(FRONTEND_PORT)"
	@trap 'kill 0' INT TERM; \
	(cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port $(BACKEND_PORT) --reload) & \
	(cd frontend && COPILOT_BACKEND=http://127.0.0.1:$(BACKEND_PORT) npm run dev -- --host 127.0.0.1 --port $(FRONTEND_PORT) --strictPort) & \
	wait

backend:
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port $(BACKEND_PORT) --reload

frontend:
	cd frontend && COPILOT_BACKEND=http://127.0.0.1:$(BACKEND_PORT) npm run dev -- --host 127.0.0.1 --port $(FRONTEND_PORT) --strictPort

demo:
	cd backend && uv run python -m app.cli demo

refresh:
	cd backend && uv run python -m app.cli refresh

health:
	cd backend && uv run python -m app.cli health

test: test-backend test-frontend typecheck

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npx vitest run

e2e:
	cd frontend && npx playwright test

validate:
	cd backend && uv run python -m app.cli validate

evaluate:
	cd backend && uv run python -m app.cli evaluate-draft

research:
	cd backend && uv run python -m app.cli research

season:
	cd backend && uv run python -m app.cli season $(SESSION) --out ../exports/season_week.xlsx

link:
	cd backend && uv run python -m app.cli espn-link $(SESSION) $(LEAGUE) --apply

sync:
	cd backend && uv run python -m app.cli espn-sync $(SESSION)

performance:
	cd backend && uv run python -m app.cli performance $(SESSION)

build-snapshot:
	cd backend && uv run python -m app.cli build-snapshot

typecheck:
	cd frontend && npx tsc --noEmit -p tsconfig.app.json

lint:
	cd backend && uv run ruff check app tests

openapi:
	cd backend && uv run python -m app.cli openapi > ../frontend/src/api/openapi.json
	cd frontend && npx openapi-typescript src/api/openapi.json -o src/api/schema.d.ts

bench:
	cd backend && uv run python -m app.cli bench

export:
	cd backend && uv run python -m app.cli export $(SESSION)

import:
	cd backend && uv run python -m app.cli import-session $(FILE)
