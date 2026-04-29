#!/usr/bin/env python3
"""Smoke test: verify all infra services (PostgreSQL, Redis, ChromaDB) are reachable."""

import asyncio
import os
import sys


async def check_postgres(url: str) -> None:
    import psycopg

    async with await psycopg.AsyncConnection.connect(url) as conn:
        await conn.execute("SELECT 1")
    print("[OK] PostgreSQL")


async def check_redis(url: str) -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(url, decode_responses=True)
    await client.set("forge:smoke", "1")
    val = await client.get("forge:smoke")
    await client.aclose()
    assert val == "1", f"Expected '1', got {val!r}"
    print("[OK] Redis")


def check_chromadb(host: str, port: int) -> None:
    import chromadb

    client = chromadb.HttpClient(host=host, port=port)
    client.heartbeat()
    print("[OK] ChromaDB")


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "postgresql://forge:forge@localhost:5432/forge")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    chroma_host = os.environ.get("CHROMA_HOST", "localhost")
    chroma_port = int(os.environ.get("CHROMA_PORT", "8001"))

    errors: list[str] = []

    try:
        await check_postgres(db_url)
    except Exception as exc:
        errors.append(f"PostgreSQL: {exc}")

    try:
        await check_redis(redis_url)
    except Exception as exc:
        errors.append(f"Redis: {exc}")

    try:
        check_chromadb(chroma_host, chroma_port)
    except Exception as exc:
        errors.append(f"ChromaDB: {exc}")

    if errors:
        for e in errors:
            print(f"[FAIL] {e}", file=sys.stderr)
        sys.exit(1)

    print("[OK] all infra services ready")


if __name__ == "__main__":
    asyncio.run(main())
