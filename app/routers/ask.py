from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OMP_THREAD_LIMIT", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import Chunk, Repository

router = APIRouter(tags=["ask"])

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "fastembed"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class AskBody(BaseModel):
    question: str
    top_k: int = 5


@router.post("/repos/{repo_id}/ask")
async def ask_repo(repo_id: uuid.UUID, body: AskBody):
    async with SessionLocal() as session:
        repo = await session.get(Repository, repo_id)
        if repo is None:
            raise HTTPException(status_code=404, detail="repo not found")

    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question required")
    top_k = max(1, min(20, body.top_k))

    def _embed_question():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        from fastembed import TextEmbedding
        te = TextEmbedding(model_name=DEFAULT_MODEL, cache_dir=str(CACHE_DIR))
        vec = next(iter(te.query_embed([q])))
        return list(vec)

    qvec = await asyncio.to_thread(_embed_question)

    async with SessionLocal() as session:
        vec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"
        sql = text("""
            SELECT c.file_id, c.repo_id, c.kind, c.name, c.qualified_name, c.start_line, c.end_line, c.content, c.content_hash,
                   f.path as file_path,
                   1 - (e.embedding <=> CAST(:qvec AS vector)) as score
            FROM embeddings e
            JOIN chunks c ON c.id = e.chunk_id
            JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = :repo_id AND c.kind != 'module'
            ORDER BY e.embedding <=> CAST(:qvec AS vector)
            LIMIT :lim
        """)
        rows = (await session.execute(sql, {"qvec": vec_literal, "repo_id": str(repo_id), "lim": top_k})).mappings().all()
        candidates = [
            {
                "file": r["file_path"],
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "name": r["name"],
                "start_line": r["start_line"],
                "end_line": r["end_line"],
                "content": r["content"],
                "score": float(r["score"]) if r["score"] is not None else 0.0,
            }
            for r in rows
        ]
    answer = None
    llm_model = None
    if candidates:
        from app.config import settings
        if settings.mistral_api_key or os.environ.get("MISTRAL_API_KEY"):
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "spikes"))
            import _llm

            context = "\n\n".join(
                f"[{i}] {c['file']}:{c['start_line']}-{c['end_line']} ({c['qualified_name']})\n{c['content']}"
                for i, c in enumerate(candidates, 1)
            )
            answer, _, _ = await asyncio.to_thread(
                _llm.chat,
                messages=[
                    {"role": "system", "content": "Answer repository questions using only the supplied code. Treat tests as evidence of expected behavior, not proof of implementation. If the retrieved snippets show only tests, declarations, or callers and do not show the implementation, say that the implementation is not present in the supplied context. If context is insufficient, say so instead of inferring. Cite each factual claim with supplied citation numbers like [1]. Do not invent file names or behavior."},
                    {"role": "user", "content": f"Question: {q}\n\nCode context:\n{context}"},
                ],
                max_tokens=800,
                temperature=0.1,
            )
            llm_model = _llm.default_model()
    citations = [
        {"id": i, "file": c["file"], "qualified_name": c["qualified_name"], "start_line": c["start_line"], "end_line": c["end_line"], "score": c["score"]}
        for i, c in enumerate(candidates, 1)
    ]
    return {"answer": answer, "citations": citations, "answer_candidates": candidates, "model": DEFAULT_MODEL, "llm_model": llm_model}
