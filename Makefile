.PHONY: install dev-backend dev-frontend migrate migration api-types test test-integration \
	e2e lint typecheck check format up down

install:
	cd backend && uv sync
	cd frontend && npm ci

dev-backend: migrate
	cd backend && uv run uvicorn --factory argus.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

## Apply migrations to ARGUS_DATABASE_URL (default: backend/argus.db).
migrate:
	cd backend && uv run alembic upgrade head

## Generate a migration from model changes: make migration m="add alerts"
migration:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

## Regenerate frontend types from the backend's OpenAPI schema.
api-types:
	cd backend && uv run python -m argus.openapi > ../frontend/openapi.json
	cd frontend && npm run api-types

test:
	cd backend && uv run pytest
	cd frontend && npm test

## Backend tests against throwaway Postgres + Redis containers.
test-integration:
	docker run -d --rm --name argus-it-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=argus_test \
		-p 127.0.0.1:55432:5432 postgres:17-alpine >/dev/null
	docker run -d --rm --name argus-it-redis -p 127.0.0.1:56379:6379 redis:7-alpine >/dev/null
	until docker exec argus-it-pg pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done; sleep 1
	cd backend && ARGUS_TEST_DATABASE_URL=postgresql+asyncpg://postgres:test@127.0.0.1:55432/argus_test \
		ARGUS_TEST_REDIS_URL=redis://127.0.0.1:56379/15 uv run pytest; \
		status=$$?; docker rm -f argus-it-pg argus-it-redis >/dev/null; exit $$status

e2e:
	cd frontend && npm run e2e

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy src tests
	cd frontend && npm run typecheck

## Everything the fast CI jobs run. Run before every commit.
check: lint typecheck test

format:
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && npm run format

up:
	docker compose up --build -d

down:
	docker compose down
