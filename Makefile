.PHONY: install fmt lint test run-api run-worker \
        services-install services-up services-down services-status services-logs \
        db-migrate db-rollback clean \
        docker-up docker-down

# ---- Application ------------------------------------------------------------

install:
	uv sync --all-extras && uv run pre-commit install

fmt:
	uv run ruff check --fix . && uv run ruff format . && uv run black --line-length 100 .

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy app

test:
	uv run pytest

run-api:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-worker:
	uv run celery -A app.tasks.celery_app worker -Q fast,slow --loglevel=info --concurrency=4

# ---- Standalone services (no Docker) ----------------------------------------

services-install:
	./scripts/install-services.sh

services-up:
	./scripts/start-services.sh

services-down:
	./scripts/stop-services.sh

services-status:
	./scripts/status-services.sh

services-logs:
	tail -f .chromadb.log

# ---- Database ---------------------------------------------------------------

db-migrate:
	uv run alembic upgrade head

db-rollback:
	uv run alembic downgrade -1

# ---- Optional Docker fallback (not recommended on WSL2) --------------------

docker-up:
	docker compose up -d redis postgres chromadb

docker-down:
	docker compose down

# ---- Housekeeping -----------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	rm -rf .pytest_cache .mypy_cache .ruff_cache; \
	echo "cleaned"
