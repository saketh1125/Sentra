from __future__ import annotations
import hashlib
from pathlib import Path

try:
    from app.chunker import get_language, Parser
    _HAS_CHUNKER = True
except ImportError:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes" / "s1_tree_sitter"))
        from chunker import get_language, Parser
        _HAS_CHUNKER = True
    except ImportError:
        _HAS_CHUNKER = False


def sha256_text(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def ast_fingerprint(text: str, language: str) -> str | None:
    if not _HAS_CHUNKER:
        return None
    try:
        root = Parser(get_language(language)).parse(text.encode()).root_node
    except Exception:
        return None
    parts: list[str] = []
    stack = [root]
    while stack:
        n = stack.pop()
        parts.append(f"{n.type}:{n.child_count}")
        for c in reversed(n.children):
            stack.append(c)
    return sha256_text("|".join(parts))


def drift_check(
    current_text: str,
    reference_text: str | None = None,
    reference_hash: str | None = None,
    reference_ast: str | None = None,
    reference_embedding: list[float] | None = None,
    current_embedding: list[float] | None = None,
    language: str = "python",
    threshold: float = 0.8,
) -> dict:
    cur_hash = sha256_text(current_text)
    ref_hash = reference_hash or (sha256_text(reference_text) if reference_text is not None else None)
    hash_drift = (cur_hash != ref_hash) if ref_hash else None

    cur_ast = ast_fingerprint(current_text, language)
    ast_drift = (cur_ast != reference_ast) if reference_ast and cur_ast else None
    if reference_text is not None and reference_ast is None and _HAS_CHUNKER:
        reference_ast = ast_fingerprint(reference_text, language)
        ast_drift = (cur_ast != reference_ast) if cur_ast and reference_ast else None

    sim: float | None = None
    sim_drift: bool | None = None
    if reference_embedding is not None and current_embedding is not None:
        import math
        a = reference_embedding; b = current_embedding
        dot = sum(x*y for x,y in zip(a,b))
        na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(x*x for x in b))
        sim = dot / (na*nb + 1e-9)
        sim = max(-1.0, min(1.0, sim))
        sim_drift = sim < threshold

    drift = bool(hash_drift) if sim_drift is None else bool(sim_drift or hash_drift)
    if ast_drift is not None:
        drift = drift or bool(ast_drift)

    return {
        "hash_drift": hash_drift,
        "ast_drift": ast_drift,
        "similarity": sim,
        "similarity_drift": sim_drift,
        "drift": drift,
        "threshold": threshold,
        "cur_hash": cur_hash,
        "cur_ast": cur_ast,
    }
