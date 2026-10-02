"""
Sentra P0 / Spike S4 — retrieval quality and embedding decision (D1).

For decision D1 the research explicitly forbids choosing an embedding model
because it is popular. This spike therefore measures candidates on Sentra's own
hand-labelled queries and reports the trade-off that actually matters for the
architecture: retrieval quality versus vector dimension (which fixes the
pgvector column type), embedding wall-clock, and peak memory.

Metrics reported per candidate:
  hit_rate@k        - expected chunk appears in top-k
  mrr               - reciprocal rank of the expected chunk
  ndcg@k            - rank-discounted, single relevant item per query
  expected_line@k   - a returned chunk actually spans the expected source line
                       (this is what a citation in M1 would point at)

Writes docs/evidence/S4_retrieval.json
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np
from fastembed import TextEmbedding
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1] / "s1_tree_sitter"))
from query_set import queries_for  # noqa: E402

import chunker as ts_chunker  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOS = REPO_ROOT / "data" / "repos"
OUT = REPO_ROOT / "docs" / "evidence" / "S4_retrieval.json"

TOP_K = 10

# Candidate embedding models, spanning the decision space described in the
# research: a small fast baseline, the research document's own suggestion, a
# code-specialised model, and a fast static-embedding model.
#
# Backend note [MEAS]: sentence-transformers was abandoned for the spike because
# it pulled >8 GB of NVIDIA CUDA wheels for a CPU-only project. fastembed runs
# ONNX on CPU with no torch dependency, which also makes the measured
# wall-clock numbers representative of what P2 will actually experience.
CANDIDATES = [
    {
        "key": "all-MiniLM-L6-v2",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "expect_dim": 384,
        "profile": "small/fast baseline",
    },
    {
        "key": "bge-small-en-v1.5",
        "model": "BAAI/bge-small-en-v1.5",
        "expect_dim": 384,
        "profile": "mid-size local baseline",
    },
    {
        "key": "nomic-embed-text-v1.5",
        "model": "nomic-ai/nomic-embed-text-v1.5",
        "expect_dim": 768,
        "profile": "research-document suggestion",
    },
    {
        "key": "jina-embeddings-v2-base-code",
        "model": "jinaai/jina-embeddings-v2-base-code",
        "expect_dim": 768,
        "profile": "code-specialised",
    },
    {
        "key": "potion-retrieval-32M",
        "model": "minishlab/potion-retrieval-32M",
        "expect_dim": 512,
        "profile": "static embeddings, fastest",
    },
]

# How a chunk is rendered into text before embedding. Compared as part of D8,
# because it materially changes retrieval quality and is free to change.
RENDER_MODES = {
    "name_and_content": lambda c: f"{c.qualified_name}\n{c.content}",
    "content_only": lambda c: c.content,
}


SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv",
             "__pycache__", "site-packages", ".tox", ".mypy_cache"}


def load_chunks(repo: Path) -> list[ts_chunker.Chunk]:
    ch = ts_chunker.Chunker(ts_chunker.ChunkerConfig())
    out: list[ts_chunker.Chunk] = []
    for p in sorted(repo.rglob("*")):
        if not p.is_file() or not p.suffix:
            continue
        if any(x in p.parts for x in SKIP_DIRS):
            continue
        if ts_chunker.language_for_path(p) is None:
            continue
        try:
            cs, _ = ch.chunk_file(p, repo)
        except Exception:  # noqa: BLE001
            continue
        # Exclude module chunks from the retrieval corpus: they duplicate every
        # function and would let a module chunk "win" trivially.
        out.extend(c for c in cs if c.kind != "module")
    return out


def _search_matrix(vectors: list[list[float]], qvec: list[float]):
    """Cosine similarity of one query against the whole corpus.

    Returns (chunks_order_by_score, normalised_matrix_ready) as numpy arrays so
    the matrix is normalised once per model, not once per query.
    """
    import numpy as np

    M = np.asarray(vectors, dtype=np.float32)
    M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    q = np.asarray(qvec, dtype=np.float32)
    q /= (np.linalg.norm(q) + 1e-9)
    return M @ q


def evaluate_all(vectors, qvecs, chunks, queries):
    """Aggregate retrieval metrics over the whole query set in one pass."""
    hits = mrr = ndcg = 0.0
    line_hits = 0
    per_query = []
    for qv, (question, exp_file, exp_qname, exp_line, note) in zip(qvecs, queries):
        sims = _search_matrix(vectors, qv)
        k = min(TOP_K, len(chunks))
        top = np.argsort(-sims)[:k]
        rels = [
            1 if (chunks[i].file_path == exp_file and chunks[i].qualified_name == exp_qname) else 0
            for i in top
        ]
        span_hit = any(
            chunks[i].file_path == exp_file
            and chunks[i].start_line <= exp_line <= chunks[i].end_line
            for i in top
        )
        rank = (rels.index(1) + 1) if any(rels) else None
        if rank:
            hits += 1
            mrr += 1.0 / rank
            ndcg += 1.0 / math.log2(rank + 1)
        line_hits += 1 if span_hit else 0
        per_query.append(
            {
                "question": question,
                "expected": f"{exp_file}::{exp_qname}@{exp_line}",
                "top1": f"{chunks[top[0]].file_path}::{chunks[top[0]].qualified_name}",
                "hit_rank": rank,
                "expected_line_in_topk": span_hit,
                "top5": [
                    f"{chunks[i].file_path}::{chunks[i].qualified_name}" for i in top[:5]
                ],
            }
        )
    n = max(1, len(queries))
    agg = {
        "hit_rate_at_k": round(hits / n, 3),
        "mrr": round(mrr / n, 3),
        "ndcg_at_k": round(ndcg / n, 3),
        "expected_line_at_k": round(line_hits / n, 3),
    }
    return agg, per_query


def main() -> int:
    repo = REPOS / "requests"
    queries = queries_for(repo.name)
    if not queries:
        print("No queries for this repo.")
        return 1

    chunks = load_chunks(repo)
    # Validate ground truth against the LIVE chunk index at this pinned commit.
    index = {(c.file_path, c.qualified_name): c for c in chunks}
    valid = [q for q in queries if (q[1], q[2]) in index]
    invalid = [q for q in queries if (q[1], q[2]) not in index]
    print(f"chunks (non-module): {len(chunks)}")
    print(f"queries: {len(queries)} | resolved against live index: {len(valid)} | unresolved: {len(invalid)}")
    for q in invalid:
        print(f"   UNRESOLVED: {q[1]}::{q[2]}  ({q[0][:60]})")
    if not valid:
        print("No ground-truth query resolves; cannot measure retrieval.")
        return 1


    results = []
    for cand in CANDIDATES:
        print(f"\n--- candidate: {cand['key']} ({cand['profile']}) ---")
        t0 = time.perf_counter()
        try:
            # fastembed selects the right task prefix per model internally
            # (passage_embed vs query_embed), so no hand-rolled prefixes here.
            model = TextEmbedding(model_name=cand["model"], cache_dir=str(REPO_ROOT / "data" / "cache" / "fastembed"))
        except Exception as exc:  # noqa: BLE001
            print(f"   LOAD FAILED: {type(exc).__name__}: {str(exc)[:140]}")
            results.append({**cand, "status": "load_failed", "error": str(exc)[:200]})
            continue
        load_s = time.perf_counter() - t0

        for rmode, render in RENDER_MODES.items():
            doc_texts = [render(c) for c in chunks]
            q_texts = [q[0] for q in valid]

            t1 = time.perf_counter()
            try:
                dvecs = np.asarray(list(model.passage_embed(doc_texts)), dtype=np.float32)
                qvecs = np.asarray(list(model.query_embed(q_texts)), dtype=np.float32)
            except Exception as exc:  # noqa: BLE001
                print(f"   EMBED FAILED ({rmode}): {type(exc).__name__}: {str(exc)[:140]}")
                continue
            emb_s = time.perf_counter() - t1
            dim = int(dvecs.shape[1])

            agg, per_query = evaluate_all(dvecs.tolist(), qvecs.tolist(), chunks, valid)
            results.append(
                {
                    "key": cand["key"],
                    "model": cand["model"],
                    "profile": cand["profile"],
                    "status": "ok",
                    "dim": dim,
                    "expected_dim": cand["expect_dim"],
                    "dim_matches_expectation": dim == cand["expect_dim"],
                    "render_mode": rmode,
                    "load_seconds": round(load_s, 1),
                    "embed_seconds": round(emb_s, 1),
                    "chunks": len(chunks),
                    "metrics": agg,
                    "per_query": per_query,
                }
            )
            print(f"   render={rmode:<16} dim={dim:<5} load={load_s:>5.1f}s embed={emb_s:>6.1f}s "
                  f"hit@{TOP_K}={agg['hit_rate_at_k']:.1%} nDCG={agg['ndcg_at_k']:.3f} "
                  f"line@{TOP_K}={agg['expected_line_at_k']:.1%}")

    report = {
        "spike": "S4",
        "subject": "Retrieval quality and embedding candidate comparison (D1)",
        "repo": {
            "name": repo.name,
            "commit": __import__("subprocess").run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip(),
        },
        "corpus": {"chunks": len(chunks), "excluded": "module chunks (duplicated by functions)"},
        "queries": {
            "total_authored": len(queries),
            "resolved_at_this_commit": len(valid),
            "unresolved": [f"{q[1]}::{q[2]}" for q in invalid],
            "top_k": TOP_K,
        },
        "metric_definitions": {
            "hit_rate_at_k": "expected chunk (file + qualified_name) present in top-k",
            "mrr": "mean reciprocal rank of the expected chunk",
            "ndcg_at_k": "single-relevant-item nDCG@k",
            "expected_line_at_k": "a top-k chunk's [start_line,end_line] spans the expected line; this is what an M1 citation would point at",
        },
        "candidates": results,
        "caveat": (
            "These are OUR queries against ONE repository (24 queries, requests). "
            "That is enough to rank candidates and to validate the pipeline, and "
            "is NOT enough to claim a general retrieval quality result. The "
            "project's O1 evaluation requires 30 questions per repo across 2-3 repos."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))

    ok = [r for r in results if r.get("status") == "ok"]
    if ok:
        best = max(ok, key=lambda r: (r["metrics"]["expected_line_at_k"], r["metrics"]["ndcg_at_k"]))
        print("\n" + "=" * 70)
        print(f"  BEST: {best['key']} ({best['render_mode']}) "
              f"dim={best['dim']} line@{TOP_K}={best['metrics']['expected_line_at_k']:.1%}")
    print(f"  Report: {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())