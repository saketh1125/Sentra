from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OMP_THREAD_LIMIT", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

from pathlib import Path

from spikes.s1_tree_sitter.chunker import Chunk, Chunker, ChunkerConfig, language_for_path

EXCLUDE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".venv", "venv",
    "__pycache__", "site-packages", ".tox", ".mypy_cache",
}

__all__ = ["Chunk", "Chunker", "ChunkerConfig", "language_for_path", "EXCLUDE_DIRS", "chunk_repo"]


def chunk_repo(repo_path: Path) -> list[Chunk]:
    chunker = Chunker(ChunkerConfig())
    out: list[Chunk] = []
    for p in sorted(repo_path.rglob("*")):
        if not p.is_file() or not p.suffix:
            continue
        if any(x in p.parts for x in EXCLUDE_DIRS):
            continue
        if language_for_path(p) is None:
            continue
        try:
            cs, _ = chunker.chunk_file(p, repo_path)
        except Exception:
            continue
        out.extend(cs)
    out.sort(key=lambda c: (c.file_path, c.start_line))
    return out
