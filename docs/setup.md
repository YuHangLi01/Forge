# Setup Guide (Standalone, no Docker)

This guide walks through a fresh install on Ubuntu 22.04+ (WSL2 supported).

## Prerequisites

- Python 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- `sudo` access (for `apt install` of postgresql + redis-server)
- A Feishu developer account with an app created

## 1. Python dependencies

```bash
make install     # uv sync + pre-commit install
```

## 2. System services (PostgreSQL + Redis + ChromaDB)

```bash
make services-install
```

This script (`scripts/install-services.sh`) does:
- `apt install postgresql postgresql-contrib redis-server`
- Starts both as system services
- Creates a `forge` Postgres role with password `forge` (SUPERUSER, idempotent)
- Creates the `forge` database owned by that role
- Creates `forge` and `langgraph` schemas

ChromaDB does **not** need apt install — it ships as a Python package via `uv` and is launched by `make services-up`.

## 3. Environment variables

```bash
cp .env.example .env
```

Required for chat (text + voice):

| Variable | Description |
|----------|-------------|
| `FEISHU_APP_ID` | Feishu app ID |
| `FEISHU_APP_SECRET` | Feishu app secret |
| `FEISHU_VERIFICATION_TOKEN` | Webhook verification token |
| `FEISHU_ENCRYPT_KEY` | Webhook encryption key |
| `DOUBAO_API_KEY` | Volcano Ark API key |
| `DOUBAO_BASE_URL` | Ark API URL (no trailing `/v1`) |
| `DOUBAO_MODEL_PRO` | Doubao endpoint ID (Pro tier) |
| `DOUBAO_MODEL_LITE` | Doubao endpoint ID (Lite tier) |
| `VOLC_ASR_APP_ID` | Volcano ASR app ID (voice only) |
| `VOLC_ASR_ACCESS_TOKEN` | Volcano ASR token (voice only) |

Database URLs default to the local install — leave them as-is unless you customised the install script:

```
DATABASE_URL=postgresql+psycopg://forge:forge@localhost:5432/forge
DATABASE_URL_SYNC=postgresql+psycopg://forge:forge@localhost:5432/forge
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8001
```

## 4. Start services

```bash
make services-up         # PostgreSQL, Redis, ChromaDB
make services-status     # all three should report [OK]
make db-migrate          # apply Alembic migrations
```

## 5. Run the application

In two separate terminals:

```bash
# Terminal A
make run-api             # uvicorn on :8000

# Terminal B
make run-worker          # celery -Q fast,slow
```

## 6. Expose webhook for Feishu

```bash
ngrok http 8000
```

Set `https://<ngrok>.ngrok.io/api/v1/webhook/feishu` as the webhook URL in the Feishu developer console.

## 7. Stop / restart

```bash
make services-down       # stop PG + Redis + ChromaDB
make services-up         # restart
```

PostgreSQL and Redis are managed via `service` (Ubuntu) so they persist data between restarts. ChromaDB stores data under `./.chroma_data` in the project directory.
