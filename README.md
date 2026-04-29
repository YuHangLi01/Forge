# Forge

Forge is a Feishu AI office assistant that processes messages, creates documents and presentations, and answers questions using Doubao LLM.

## Architecture

```mermaid
graph TD
    User[Feishu User] -->|webhook| WH[FastAPI :8000]
    WH -->|Celery slow| Worker[Celery Worker]
    Worker --> LLM[Doubao LLM]
    Worker --> Adapter[FeishuAdapter]
    Worker --> DB[(PostgreSQL :5432)]
    Adapter -->|reply| User
    Worker -.->|vectors| Chroma[(ChromaDB :8001)]
    WH -.->|dedup| Redis[(Redis :6379)]
    WH -.->|queue| Redis
```

---

## Standalone Deployment (recommended for WSL2)

WSL2 + Docker Desktop is unreliable for this stack, so the default deployment runs PostgreSQL, Redis, and ChromaDB **directly on the host** (no containers).

Tested on Ubuntu 22.04 / 24.04 (WSL2). Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

### One-time setup

```bash
# 1. Clone & enter project
cd forge

# 2. Install Python deps + git hooks
make install

# 3. Install PostgreSQL + Redis via apt, create forge DB & user (idempotent)
make services-install

# 4. Copy and fill in environment variables
cp .env.example .env
# Required minimum to chat:
#   FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_VERIFICATION_TOKEN, FEISHU_ENCRYPT_KEY
#   DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_MODEL_PRO, DOUBAO_MODEL_LITE
# DATABASE_URL / DATABASE_URL_SYNC default to postgresql+psycopg://forge:forge@localhost:5432/forge
```

### Daily start (3 terminals)

```bash
# Terminal 1: Start PostgreSQL + Redis + ChromaDB
make services-up
make services-status     # verify all three are reachable
make db-migrate          # first time only, or after schema changes

# Terminal 2: FastAPI on :8000
make run-api

# Terminal 3: Celery worker (fast + slow queues)
make run-worker

# Terminal 4 (optional): expose webhook to public internet
ngrok http 8000
# Paste the ngrok HTTPS URL + /api/v1/webhook/feishu into the Feishu developer console
```

### Stop everything

```bash
# In each app terminal: Ctrl+C
make services-down       # stops PostgreSQL, Redis, ChromaDB
```

### Service map

| Service    | Port | Started by                   | Data path        |
|------------|------|------------------------------|------------------|
| PostgreSQL | 5432 | `service postgresql` (apt)   | system default   |
| Redis      | 6379 | `service redis-server` (apt) | system default   |
| ChromaDB   | 8001 | `uv run chroma run` (bg)     | `./.chroma_data` |

ChromaDB runs as a background `uv` process; pid is stored in `.chromadb.pid` and logs in `.chromadb.log`. Tail with `make services-logs`.

---

## Verification

```bash
make services-status                  # PG / Redis / Chroma heartbeat
curl http://localhost:8000/healthz    # → {"status":"ok"}
curl http://localhost:8000/readyz     # → 200 if Redis + PG up
make lint                             # ruff + mypy strict
make test                             # pytest, ≥70% coverage required
```

End-to-end smoke (after webhook URL is registered in Feishu):
- Send "你好" to the bot → reply within 10s
- Send a voice message → reply within 15s

---

## Make targets

| Target | Description |
|--------|-------------|
| `make install`           | Install Python deps via uv + pre-commit hooks |
| `make fmt`               | Format code (ruff + black) |
| `make lint`              | ruff + mypy strict |
| `make test`              | Run pytest with coverage |
| `make run-api`           | FastAPI on :8000 (auto-reload) |
| `make run-worker`        | Celery worker, queues: fast,slow |
| `make services-install`  | apt install + bootstrap forge DB |
| `make services-up`       | Start PostgreSQL, Redis, ChromaDB |
| `make services-down`     | Stop all three |
| `make services-status`   | Health check all three |
| `make services-logs`     | Tail ChromaDB log |
| `make db-migrate`        | Apply Alembic migrations |
| `make db-rollback`       | Roll back one migration |
| `make clean`             | Remove caches |
| `make docker-up/down`    | Optional Docker fallback (not recommended on WSL2) |

---

## Documentation

- [Setup guide](docs/setup.md)
- [Architecture](docs/architecture.md)
- [Feishu app configuration](docs/feishu-app-setup.md)
- [Troubleshooting](docs/troubleshooting.md)
