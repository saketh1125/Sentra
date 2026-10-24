from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OMP_THREAD_LIMIT", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
import logging
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Chunk, Embedding

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "fastembed"
SLICE = 64


def _render(c: Chunk) -> str:
    return f"{c.qualified_name}\n{c.content}"


async def embed_repo(repo_id: uuid.UUID, model: str = DEFAULT_MODEL) -> dict:
    async with SessionLocal() as session:
        q = select(Chunk).where(Chunk.repo_id == repo_id, Chunk.kind != "module").order_by(Chunk.start_line)
        rows: list[Chunk] = (await session.execute(q)).scalars().all()
        if not rows:
            return {"repo_id": str(repo_id), "model": model, "chunks": 0, "embedded": 0, "message": "no chunks to embed (kind != module)"}
        existing = set((await session.execute(select(Embedding.chunk_id).where(Embedding.chunk_id.in_([r.id for r in rows])))).scalars().all())
        to_embed = [r for r in rows if r.id not in existing]
        if not to_embed:
            return {"repo_id": str(repo_id), "model": model, "chunks": len(rows), "embedded": 0, "skipped_existing": len(existing)}

    def _embed_sync():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        from fastembed import TextEmbedding
        te = TextEmbedding(model_name=model, cache_dir=str(CACHE_DIR))
        texts = [_render(c) for c in to_embed]
        vecs: list[list[float]] = []
        for i in range(0, len(texts), SLICE):
            batch = texts[i:i+SLICE]
            batch_vecs = list(te.passage_embed(batch))
            vecs.extend([list(v) for v in batch_vecs])
            logger.info("embed %s %d/%d", repo_id, min(i+SLICE, len(texts)), len(texts))
        return vecs

    vecs = await asyncio.to_thread(_embed_sync)

    async with SessionLocal() as session:
        for ch, vec in zip(to_embed, vecs):
            session.add(Embedding(chunk_id=ch.id, embedding=vec, model=model, render_mode="name_and_content"))
        await session.commit()

    logger.info("embed %s done: %d vectors model=%s", repo_id, len(vecs), model)
    return {"repo_id": str(repo_id), "model": model, "chunks": len(rows), "embedded": len(vecs)}
