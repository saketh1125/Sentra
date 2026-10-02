"""
Sentra P0 / Spike S4 — retrieval quality and embedding decision (D1).

MEMORY-SAFETY CONTRACT (added after the 2026-10-02 OOM incident)
----------------------------------------------------------------
The first version of this spike ran all candidates in one process, embedded the
whole corpus in one unbounded call, and converted matrices with .tolist(). It
reached ~51.9 GB RSS and was OOM-killed, taking the OpenCode session with it
(see docs/resource-incident.md).

This version therefore:
  * runs EXACTLY ONE candidate per process (selected by --candidate), so peak
    memory is bounded by a single model;
  * embeds in bounded slices (--slice, default 64) rather than one giant call;
  * scores with numpy only and never materialises Python float lists;
  * caps thread counts before onnxruntime is imported;
  * logs RSS after each stage so growth is observable;
  * refuses to run unbounded if invoked with --all.

Usage (safe):
    for c in all-MiniLM-L6-v2 bge-small-en-v1.5 nomic-embed-text-v1.5 \
             jina-embeddings-v2-base-code potion-retrieval-32M; do
      ulimit -v 8388608        # 8 GB address space; fails fast, never OOM-kills the session
      OMP_NUM_THREADS=4 python spikes/s4_retrieval/spike.py --candidate "$c"
    done

Metrics are written per candidate to docs/evidence/S4_<candidate>.json and are
merged into docs/evidence/S4_retrieval.json only for candidates that completed.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import sys
import time
from pathlib import Path

# Thread caps MUST be set before onnxruntime is imported.
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OMP_THREAD_LIMIT", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1] / "s1_tree_sitter"))
from query_set import queries_for  # noqa: E402

import chunker as ts_chunker  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOS = REPO_ROOT / "data" / "repos"
EVIDENCE = REPO_ROOT / "docs" / "evidence"

TOP_K = 10
DEFAULT_SLICE = 64

CANDIDATES: dict[str, dict] = {
    "all-MiniLM-L6-v2": {
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
        "profile": "small/fast baseline",
    },
    "bge-small-en-v1.5": {
        "model": "BAAI/bge-small-en-v1.5",
        "dim": 384,
        "profile": "mid-size local baseline",
    },
    "nomic-embed-text-v1.5": {
        "model": "nomic-ai/nomic-embed-text-v1.5",
        "dim": 768,
        "profile": "research-document suggestion",
    },
    "jina-embeddings-v2-base-code": {
        "model": "jinaai/jina-embeddings-v2-base-code",
        "dim": 768,
        "profile": "code-specialised",
    },
    "potion-retrieval-32M": {
        "model": "minishlab/potion-retrieval-32M",
        "dim": 512,
        "profile": "static embeddings, fastest",
    },
}

# How a chunk is rendered before embedding. Compared as part of D8.
RENDER_MODES = {
    "name_and_content": lambda c: f"{c.qualified_name}\n{c.content}",
    "content_only": lambda c: c.content,
}

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".venv", "venv",
    "__pycache__", "site-packages", ".tox", ".mypy_cache",
}


def rss_mb() -> float:
    """Resident set size in MiB, read from /proc. Used for observability."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return -1.0


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
        # Module chunks contain all their functions and would win queries
        # trivially, so they are excluded from the retrieval corpus (kept for M6).
        out.extend(c for c in cs if c.kind != "module")
    return out


def embed_batched(model, texts: list[str], slice_size: int, kind: str):
    """Embed in bounded slices. Returns a single float32 numpy array.

    Slicing bounds peak memory inside the ONNX runtime; a single call over the
    whole corpus does not.
    """
    import numpy as np

    fn = model.passage_embed if kind == "passage" else model.query_embed
    parts: list = []
    for i in range(0, len(texts), slice_size):
        batch = texts[i : i + slice_size]
        parts.append(np.asarray(list(fn(batch)), dtype=np.float32))
        print(f"      {kind} {i + len(batch)}/{len(texts)}  rss={rss_mb()}MB", flush=True)
    return np.vstack(parts)


def score_corpus(dvecs, qvec):
    """Normalise once per matrix, then cosine via dot product. numpy only —
    no .tolist(), which previously multiplied memory by ~30x."""
    import numpy as np

    M = dvecs / (np.linalg.norm(dvecs, axis=1, keepdims=True) + 1e-9)
    Q = qvecs = qvec / (np.linalg.norm(qvec, axis=1, keepdims=True) + 1e-9)
    return M, Q


def evaluate_all(dvecs, qvecs, chunks, queries):
    """Aggregate retrieval metrics over the whole query set in one pass."""
    hits = mrr = ndcg = 0.0
    line_hits = 0
    per_query = []
    for row, (question, exp_file, exp_qname, exp_line, note) in zip(qvecs, queries):
        sims = dvecs @ row
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True, choices=sorted(CANDIDATES))
    ap.add_argument("--slice", type=int, default=DEFAULT_SLICE)
    ap.add_argument("--limit-chunks", type=int, default=0,
                    help="cap corpus size for a smoke test (0 = all)")
    ap.add_argument("--all", action="store_true",
                    help="REFUSED: running all candidates in one process caused the OOM")
    args = ap.parse_args()

    if args.all:
        print("REFUSED: --all caused the 2026-10-02 OOM (51.9 GB RSS, session killed).")
        print("Run one candidate per process; see the module docstring.")
        return 2

    import numpy as np  # noqa: F401  (ensure loaded before heavy work)

    from fastembed import TextEmbedding

    cand = CANDIDATES[args.candidate]
    repo = REPOS / "requests"
    queries = queries_for(repo.name)
    if not queries:
        print("No queries for this repo.")
        return 1

    chunks = load_chunks(repo)
    index = {(c.file_path, c.qualified_name): c for c in chunks}
    valid = [q for q in queries if (q[1], q[2]) in index]
    invalid = [q for q in queries if (q[1], q[2]) not in index]
    if args.limit_chunks:
        chunks = chunks[: args.limit_chunks]
    print(f"candidate : {args.candidate} ({cand['profile']})")
    print(f"chunks    : {len(chunks)}  (slice={args.slice})")
    print(f"queries   : {len(queries)} | resolved={len(valid)} | unresolved={len(invalid)}")
    for q in invalid:
        print(f"   UNRESOLVED: {q[1]}::{q[2]}")
    if not valid:
        print("No ground-truth query resolves; cannot measure retrieval.")
        return 1
    print(f"rss@start : {rss_mb()} MB")

    t0 = time.perf_counter()
    try:
        model = TextEmbedding(
            model_name=cand["model"],
            cache_dir=str(REPO_ROOT / "data" / "cache" / "fastembed"),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"LOAD FAILED: {type(exc).__name__}: {str(exc)[:200]}")
        return 1
    load_s = time.perf_counter() - t0
    print(f"loaded in {load_s:.1f}s  rss={rss_mb()} MB")

    results = []
    for rmode, render in RENDER_MODES.items():
        doc_texts = [render(c) for c in chunks]
        q_texts = [q[0] for q in valid]
        t1 = time.perf_counter()
        try:
            dvecs = embed_batched(model, doc_texts, args.slice, "passage")
            qvecs = embed_batched(model, q_texts, args.slice, "query")
        except Exception as exc:  # noqa: BLE001
            print(f"   EMBED FAILED ({rmode}): {type(exc).__name__}: {str(exc)[:160]}")
            continue
        emb_s = time.perf_counter() - t1
        dim = int(dvecs.shape[1])

        D, Q = score_corpus(dvecs, qvecs)
        agg, per_query = evaluate_all(D, Q, chunks, valid)
        results.append(
            {
                "key": args.candidate,
                "model": cand["model"],
                "profile": cand["profile"],
                "status": "ok",
                "dim": dim,
                "expected_dim": cand["dim"],
                "dim_matches_expectation": dim == cand["dim"],
                "render_mode": rmode,
                "load_seconds": round(load_s, 1),
                "embed_seconds": round(emb_s, 1),
                "chunks": len(chunks),
                "slice_size": args.slice,
                "peak_rss_mb": rss_mb(),
                "metrics": agg,
                "per_query": per_query,
            }
        )
        print(f"   render={rmode:<16} dim={dim:<5} load={load_s:>5.1f}s embed={emb_s:>6.1f}s "
              f"hit@{TOP_K}={agg['hit_rate_at_k']:.1%} nDCG={agg['ndcg_at_k']:.3f} "
              f"line@{TOP_K}={agg['expected_line_at_k']:.1%} rss={rss_mb()}MB")

        # Release aggressively before the next render mode.
        del D, Q, dvecs, qvecs, doc_texts, q_texts
        gc.collect()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"S4_{args.candidate}.json"
    out.write_text(
        json.dumps(
            {
                "spike": "S4",
                "subject": "Retrieval quality and embedding candidate comparison (D1)",
                "candidate": args.candidate,
                "repo": {
                    "name": repo.name,
                    "commit": __import__("subprocess").run(
                        ["git", "-C", str(repo), "rev-parse", "HEAD"],
                        capture_output=True, text=True,
                    ).stdout.strip(),
                },
                "corpus": {"chunks": len(chunks), "excluded": "module chunks"},
                "queries": {
                    "total_authored": len(queries),
                    "resolved_at_this_commit": len(valid),
                    "unresolved": [f"{q[1]}::{q[2]}" for q in invalid],
                    "top_k": TOP_K,
                },
                "metric_definitions": {
                    "hit_rate_at_k": "expected chunk (file + qualified_name) in top-k",
                    "mrr": "mean reciprocal rank of the expected chunk",
                    "ndcg_at_k": "single-relevant-item nDCG@k",
                    "expected_line_at_k": "a top-k chunk spans the expected source line; what an M1 citation would point at",
                },
                "results": results,
                "caveat": (
                    "OUR queries against ONE repository (24 queries, requests). Enough to "
                    "rank candidates and validate the pipeline; NOT a general retrieval "
                    "quality claim. O1 requires 30 questions per repo across 2-3 repos."
                ),
            },
            indent=2,
        )
    )

    del model
    gc.collect()
    print(f"\n  peak rss {rss_mb()} MB")
    print(f"  wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    import numpy as np  # noqa: E402

    raise SystemExit(main())