#!/usr/bin/env python3
"""Seed demo knowledge base into ChromaDB from fixture files.

Usage:
    uv run python scripts/seed_data.py --env demo
    uv run python scripts/seed_data.py --env dev --user-id dev_tester1

All user_ids must start with "demo_" or "dev_" — others are rejected to
prevent accidentally polluting production data.

Expected runtime: < 30 s for the built-in fixtures (bge-m3 warm path < 2 s per chunk).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


_ALLOWED_PREFIXES = ("demo_", "dev_")


def _require_safe_user_id(user_id: str) -> None:
    if not any(user_id.startswith(p) for p in _ALLOWED_PREFIXES):
        raise ValueError(
            f"user_id '{user_id}' must start with one of {_ALLOWED_PREFIXES}. "
            "Refusing to seed to avoid polluting production data."
        )


async def _seed_file(
    chroma_svc: object,
    embed_svc: object,
    user_id: str,
    doc_id: str,
    path: Path,
) -> int:
    """Chunk *path* by paragraph, embed, and add to ChromaDB. Returns chunk count."""
    from app.services.chroma_service import ChromaService
    from app.services.embedding_service import EmbeddingService

    assert isinstance(chroma_svc, ChromaService)
    assert isinstance(embed_svc, EmbeddingService)

    text = path.read_text(encoding="utf-8")
    # Split on double newline → paragraphs; skip empty chunks
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    print(f"  Embedding {len(paragraphs)} chunks from {path.name} …", flush=True)
    t0 = time.perf_counter()
    embeddings = await embed_svc.embed_batch(paragraphs)
    elapsed = time.perf_counter() - t0
    print(f"  Embedded in {elapsed:.2f}s", flush=True)

    for i, (chunk, emb) in enumerate(zip(paragraphs, embeddings, strict=False)):
        chunk_id = f"{doc_id}_chunk_{i}"
        await chroma_svc.add(
            user_id=user_id,
            doc_id=chunk_id,
            text=chunk,
            embedding=emb,
            metadata={"source_file": path.name, "chunk_index": i},
        )

    print(f"  Added {len(paragraphs)} chunks for user={user_id}, doc={doc_id}", flush=True)
    return len(paragraphs)


async def _seed_outline(
    chroma_svc: object,
    embed_svc: object,
    user_id: str,
    doc_id: str,
    path: Path,
) -> int:
    """Embed a JSON outline as a single document chunk."""
    from app.services.chroma_service import ChromaService
    from app.services.embedding_service import EmbeddingService

    assert isinstance(chroma_svc, ChromaService)
    assert isinstance(embed_svc, EmbeddingService)

    data = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(data, ensure_ascii=False, indent=2)
    emb = await embed_svc.embed(text)
    await chroma_svc.add(
        user_id=user_id,
        doc_id=doc_id,
        text=text,
        embedding=emb,
        metadata={"source_file": path.name, "type": "outline"},
    )
    print(f"  Added outline {path.name} for user={user_id}", flush=True)
    return 1


async def _run(env: str, target_user_id: str | None) -> None:
    from app.services.chroma_service import ChromaService
    from app.services.embedding_service import EmbeddingService

    fixtures_root = Path(__file__).parent.parent / "tests" / "fixtures"
    meetings_dir = fixtures_root / "meetings"
    outlines_dir = fixtures_root / "outlines"

    chroma_svc = ChromaService()
    embed_svc = EmbeddingService()

    # env determines which user namespace to use
    prefix = "demo_" if env == "demo" else "dev_"

    user_a = target_user_id or f"{prefix}alice"
    user_b = target_user_id or f"{prefix}bob"

    _require_safe_user_id(user_a)
    _require_safe_user_id(user_b)

    total_chunks = 0
    t_start = time.perf_counter()

    # Seed meeting transcripts
    for i, md_path in enumerate(sorted(meetings_dir.glob("*.md")), start=1):
        uid = user_a if i % 2 == 1 else user_b
        doc_id = f"kb_{uid}_meeting_{i:02d}"
        total_chunks += await _seed_file(chroma_svc, embed_svc, uid, doc_id, md_path)

    # Seed outlines
    for i, json_path in enumerate(sorted(outlines_dir.glob("*.json")), start=1):
        uid = user_a if i % 2 == 1 else user_b
        doc_id = f"kb_{uid}_outline_{i:02d}"
        total_chunks += await _seed_outline(chroma_svc, embed_svc, uid, doc_id, json_path)

    elapsed = time.perf_counter() - t_start
    print(f"\nDone. Seeded {total_chunks} total chunks in {elapsed:.1f}s.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo knowledge base")
    parser.add_argument("--env", choices=["demo", "dev"], default="demo")
    parser.add_argument(
        "--user-id",
        default=None,
        help="Override user_id (must have demo_/dev_ prefix)",
    )
    args = parser.parse_args()

    asyncio.run(_run(env=args.env, target_user_id=args.user_id))


if __name__ == "__main__":
    main()
