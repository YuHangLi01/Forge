# Troubleshooting

## Webhook signature verification fails (401)

Check that `FEISHU_ENCRYPT_KEY` in `.env` matches the encryption key set in the Feishu developer console. The signature is computed over the decrypted body, so the key must be set before the webhook fires.

## ChromaDB connection refused

Default port is 8001. Check `make services-status`. If it's down, look at `.chromadb.log` for the failure reason. Restart with `make services-down && make services-up`.

If the port is in use:

```bash
ss -ltnp | grep 8001        # find what's holding it
```

## PostgreSQL "role forge does not exist"

The install script may have failed silently. Re-run it:

```bash
sudo -u postgres psql -c "CREATE ROLE forge LOGIN PASSWORD 'forge' SUPERUSER"
sudo -u postgres createdb -O forge forge
```

## Redis "Connection refused"

```bash
sudo service redis-server status      # should say active (running)
sudo service redis-server start
redis-cli ping                        # → PONG
```

## LangGraph checkpoint tables missing

Drop and recreate via Alembic:

```bash
make db-rollback
make db-migrate
```

The LangGraph checkpoint tables are created automatically by `AsyncPostgresSaver.setup()` on first worker run.

## Doubao 401 Unauthorized

Do **not** include a trailing `/v1` in `DOUBAO_BASE_URL`. The LangChain OpenAI client appends `/v1` automatically. Correct: `https://ark.cn-beijing.volces.com/api/v3`.

## Celery tasks not running

Ensure the worker is started with both queues. The Makefile target already does this:

```bash
celery -A app.tasks.celery_app worker -Q fast,slow
```

Starting with only the default queue silently drops all routed tasks.

## `make test` fails with import errors

Run `make install` first. If a specific module fails to import, check that all env vars in `.env.example` are present in your `.env` — `get_settings()` is called at import time and will raise `ValidationError` if any required field is missing.

## WSL2 + Docker Desktop issues

This project no longer uses Docker by default. If you want to use Docker anyway (`make docker-up`), enable Docker Desktop's WSL2 integration: Settings → Resources → WSL Integration → toggle your distro → Apply & Restart. Standalone deployment (`make services-up`) is the supported path.

## `sudo: a terminal is required to read the password`

The install/start/stop scripts call `sudo`. Either run them in an interactive terminal, or pre-grant passwordless sudo for `service` and `apt-get`:

```bash
sudo visudo -f /etc/sudoers.d/forge
# Add:  yourusername ALL=(ALL) NOPASSWD: /usr/sbin/service, /usr/bin/apt-get
```
