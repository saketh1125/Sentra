"""
Sentra P0 / Spike S6 — Documentation drift detection (D11 doc-time reference
vector, D13 drift methodology).

Measures, with no claim beyond what is measured (Sentra_research.md §9, row S6):
  1. Detection rate of three detectors on three controlled mutation classes
     applied to the CODE side of linked doc/chunk pairs (the doc text stays as
     S5 generated it — that is exactly the stale-doc condition S6 measures):
       M1 identity   — rename the chunk's qualified name in the chunk text
       M2 behavior   — alter one string / integer literal
       M3 structure  — remove one parameter, or add one statement
  2. False-positive rate on negatives: unmutated chunks plus §9's requested
     cosmetic negatives (comment-only, whitespace-only).
  3. A threshold sweep for the similarity detector over
     {0.50, 0.60, 0.70, 0.80, 0.90, 0.95}; the chosen threshold is the lowest
     sweep point with zero FP on unmutated chunks.
  4. Per-detector cost in ms per check, so the "cost" column of D13 is measured
     rather than asserted.

DOC<->CHUNK LINKAGE
  The only S5 data that enters this spike is docs/evidence/S5_sample_docs.json.
  S5's own sampler is imported (load_chunks / chunk_id / sample_chunks live at
  module level in spikes/s5_docgen/spike.py and import cleanly without running
  its main), the requests corpus is re-chunked at the same commit S5 used, and
  each sample doc is matched to its chunk by exact chunk_id. The reproduced
  sample of size 3 is verified to be identical to the set S5 actually documented,
  so the linkage is exact rather than name-guessed.

MEMORY-SAFETY CONTRACT (docs/resource-incident.md — the rule that exists
because one embedding spike once OOM-killed the session):
  * runs in ONE process whose address space is capped by the caller
    (`ulimit -v 8388608`, see the docstring footer / run command);
  * OMP/MKL thread caps are set BEFORE onnxruntime is imported;
  * texts are short; the embedding model is loaded once and every embed call is
    a single short text (batch of 1) — no corpus-scale batch ever forms;
  * RSS is logged after each stage so growth is observable;
  * `del` + gc.collect() before exit.

Writes docs/evidence/S6_drift.json

Run (exactly this, one memory-bounded process):
    OMP_NUM_THREADS=4 ulimit -v 8388608 && \\
    .venv/bin/python spikes/s6_drift/spike.py
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

# Thread caps MUST be set before onnxruntime is imported (fastembed loads it).
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OMP_THREAD_LIMIT", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "s1_tree_sitter"))
from chunker import Parser, get_language, language_for_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO = REPO_ROOT / "data" / "repos" / "requests"
S5_SPIKE = Path(__file__).resolve().parents[1] / "s5_docgen" / "spike.py"
SAMPLE_DOCS = REPO_ROOT / "docs" / "evidence" / "S5_sample_docs.json"
S5_MAIN_EVIDENCE = REPO_ROOT / "docs" / "evidence" / "S5_docgen.json"
OUT = REPO_ROOT / "docs" / "evidence" / "S6_drift.json"

EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # S4 candidate; local, cached
CACHE_DIR = REPO_ROOT / "data" / "cache" / "fastembed"

# D13 sweep set, as specified in the S6 task.
THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)

# Mutation classes. "None" pseudo-classes are FP controls, not drift.
DRIFT_CLASSES = ("M1_identity", "M2_behavior", "M3_structure")
NEGATIVE_CLASSES = ("unmutated", "N1_comment_only", "N2_whitespace_only")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def rss_mb() -> float:
    """Resident set size in MiB from /proc — observability per §6 rule 9."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return -1.0


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def doc_text(doc: dict) -> str:
    """The S5 doc's text as a single embedding target."""
    d = doc["doc"] if "doc" in doc and isinstance(doc["doc"], dict) else doc
    return "\n".join([d.get("summary", "")] + list(d.get("key_behaviors", [])) + [d.get("complexity_note", "")])


def _parse(text: str, language: str):
    return Parser(get_language(language)).parse(text.encode("utf8"))


def parse_ok(text: str, language: str) -> bool:
    """A mutated chunk that no longer parses measures the harness, not drift."""
    try:
        return not _parse(text, language).root_node.has_error
    except Exception:  # noqa: BLE001
        return False


def ast_fingerprint(text: str, language: str) -> str:
    """D2's signature: sha256 over the pre-order sequence of
    (node_type, child_count) for ALL nodes (named + anonymous).

    Deliberately content-free: renaming an identifier or editing a literal
    leaves the sequence identical, so this measures structural drift only.
    Whitespace never appears as a node; `comment` is a named node and DOES
    appear — that is measured as an FP on comment-only edits, not hidden.
    """
    root = _parse(text, language).root_node
    parts: list[str] = []
    stack = [root]
    while stack:
        node = stack.pop()
        parts.append(f"{node.type}:{node.child_count}")
        for child in reversed(node.children):
            stack.append(child)
    return sha256_text("|".join(parts))


_FUNC_TYPES = {
    "function_definition",          # python
    "method_definition",            # js/ts
    "function_declaration",         # js/ts
    "generator_function_declaration",
}


def _first_function(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _FUNC_TYPES:
            return node
        stack.extend(reversed(node.children))
    return None


def _last_body_statement(body):
    stmts = [c for c in body.named_children if c.type != "comment"]
    return stmts[-1] if stmts else None


# --------------------------------------------------------------------------
# Mutation classes (mutate the CHUNK text; the doc stays as S5 wrote it)
# --------------------------------------------------------------------------

def mutate_m1_rename(content: str, language: str, chunk) -> tuple[str | None, str]:
    """M1 identity: rename the chunk's qualified name everywhere in its text."""
    name = chunk.name
    if chunk.kind == "module" or not name or name.startswith("<"):
        return None, "M1 not applicable: chunk has no renameable name (module/qualified '<module>')"
    total = 0
    text = content
    # The qualified name first, so "Class.method" does not become "Class.method_x.method"
    if chunk.qualified_name != name and chunk.qualified_name in text:
        text, n = re.subn(re.escape(chunk.qualified_name), chunk.qualified_name + "_s6renamed", text)
        total += n
    new = name + "_s6renamed"
    text, n = re.subn(r"\b" + re.escape(name) + r"\b", new, text)
    total += n
    if total == 0:
        return None, "M1 not applicable: name does not occur in chunk text"
    return text, f"renamed {name!r} -> {new!r} ({total} occurrence(s) in chunk text)"


def _alter_first_literal(text: str) -> tuple[str | None, str]:
    """Deterministic single-literal edit, node-type preserving where possible.

    Order: integer, single-line string, triple-quoted string. Integer and
    string-value edits keep the literal's node type, which is precisely what
    makes them invisible to an AST-type fingerprint.
    """
    m = re.search(r"\b\d+\b", text)
    if m:
        new = str(int(m.group(0)) + 1)
        return text[: m.start()] + new + text[m.end():], f"integer literal {m.group(0)} -> {new}"
    m = re.search(r'"[^"\n]*"|\'[^\'\n]*\'', text)
    if m:
        inner = m.group(0)[1:-1]
        new_inner = (inner + "_s6") if inner else "s6"
        q = m.group(0)[0]
        altered = q + new_inner + q
        return text[: m.start()] + altered + text[m.end():], f"string literal {m.group(0)} -> {altered}"
    m = re.search(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'', text)
    if m:
        inner = m.group(0)[3:-3]
        new_inner = (inner + "_s6") if inner else "s6"
        altered = m.group(0)[:3] + new_inner + m.group(0)[-3:]
        return text[: m.start()] + altered + text[m.end():], f"docstring literal altered (+_s6)"
    return None, "M2 not applicable: no string or numeric literal in chunk text"


def mutate_m2_behavior(content: str, language: str, chunk) -> tuple[str | None, str]:
    """M2 behavior: alter exactly one literal's VALUE, not a node's type."""
    return _alter_first_literal(content)


def _insert_one_statement(text: str, language: str, where: str) -> str:
    """Add one statement: at the end of a function body (matching its indent),
    or at module level for a module chunk."""
    tree = _parse(text, language)
    if where == "module" or tree is None:
        return text.rstrip("\n") + "\n\nS6_M3_MARKER = None\n"
    root = tree.root_node
    fd = _first_function(root)
    if fd is None:
        return text.rstrip("\n") + "\n\nS6_M3_MARKER = None\n"
    body = fd.child_by_field_name("body")
    if body is None:
        return text.rstrip("\n") + "\n\nS6_M3_MARKER = None\n"
    last = _last_body_statement(body)
    if last is None:
        # Body with no named statement (impossible for a def): insert after the header
        indent = "    "
        return text[: body.start_byte] + "\n" + indent + "S6_M3_MARKER = None" + text[body.start_byte:]
    line_start = text.rfind("\n", 0, last.start_byte) + 1
    indent = re.match(r"[ \t]*", text[line_start:]).group(0)
    stmt = "\n" + indent + "S6_M3_MARKER = None"
    return text[: last.end_byte] + stmt + text[last.end_byte:]


def _remove_one_parameter(text: str, language: str) -> tuple[str | None, str]:
    """Remove the last named parameter of the first function (self/cls kept)."""
    tree = _parse(text, language)
    root = tree.root_node
    fd = _first_function(root)
    if fd is None:
        return None, "no function found"
    params = fd.child_by_field_name("parameters")
    if params is None:
        return None, "no parameters node"
    candidates = [c for c in params.named_children if c.type != "comment" and
                  (c.type == "identifier" and c.text.decode("utf8", "replace") not in ("self", "cls")
                   or c.type in ("default_parameter", "typed_parameter", "typed_default_parameter",
                                 "dictionary_splat_pattern", "list_splat_pattern", "keyword_identifier"))]
    if not candidates:
        return None, "no removable parameter (only self/cls, or none)"
    target = candidates[-1]
    kids = params.children
    i = next(ii for ii, k in enumerate(kids) if k is target)
    start, end = target.start_byte, target.end_byte
    j = i
    while j - 1 >= 0 and kids[j - 1].type in ("*", "**"):  # absorb **kwargs markers
        j -= 1
        start = kids[j].start_byte
    k = i + 1
    while k < len(kids) and kids[k].type == "comment":
        k += 1
    if k < len(kids) and kids[k].type == ",":
        end = kids[k].end_byte
    elif j - 1 >= 0 and kids[j - 1].type == ",":
        start = kids[j - 1].start_byte
    return text[:start] + text[end:], f"removed last parameter {target.text.decode('utf8', 'replace')!r}"


def mutate_m3_structure(content: str, language: str, chunk) -> tuple[str | None, str]:
    """M3 structure: remove one signature parameter, or add one statement."""
    try:
        removed, note = _remove_one_parameter(content, language)
    except Exception as exc:  # noqa: BLE001
        removed, note = None, f"parameter surgery failed: {type(exc).__name__}"
    if removed and parse_ok(removed, language):
        return removed, note + " (parse ok)"
    where = "module" if chunk.kind == "module" else "function"
    added = _insert_one_statement(content, language, where)
    if parse_ok(added, language):
        return added, f"added one statement 'S6_M3_MARKER = None' ({where} level; {note})"
    return None, f"M3 failed: no structural edit produced a parseable chunk ({note})"


def mutate_n1_comment(content: str, language: str, chunk) -> tuple[str | None, str]:
    """§9 negative: a comment-only edit — doc is NOT stale."""
    return content + "\n# s6 negative: comment-only edit\n", "appended one comment line"


def mutate_n2_whitespace(content: str, language: str, chunk) -> tuple[str | None, str]:
    """§9 negative: a whitespace-only edit — doc is NOT stale."""
    return content + "   \n", "appended a whitespace-only line"


MUTATIONS = {
    "unmutated": lambda c, l, k: (c, "control: chunk text unchanged"),
    "M1_identity": mutate_m1_rename,
    "M2_behavior": mutate_m2_behavior,
    "M3_structure": mutate_m3_structure,
    "N1_comment_only": mutate_n1_comment,
    "N2_whitespace_only": mutate_n2_whitespace,
}


# --------------------------------------------------------------------------
# Linkage: sample docs -> chunks, via S5's own sampler
# --------------------------------------------------------------------------

def load_s5_module():
    if not S5_SPIKE.exists():
        raise FileNotFoundError(S5_SPIKE)
    spikes_root = str(Path(__file__).resolve().parents[1])
    for p in (spikes_root, str(Path(__file__).resolve().parents[1] / "s1_tree_sitter")):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("s5_spike_module", S5_SPIKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # module level only; main() guarded
    return mod


def link_docs_to_chunks(sample: dict) -> tuple[list[dict], dict]:
    """Map each S5 sample doc back to its chunk. Exact chunk_id match is the
    primary method; qualified-name match is the documented fallback."""
    s5 = load_s5_module()
    corpus = s5.load_chunks(REPO)          # sorted by chunk_id, same as S5
    by_id = {s5.chunk_id(c): c for c in corpus}
    reproduced = [s5.chunk_id(c) for c in s5.sample_chunks(corpus, len(sample["docs"]))]
    by_name: dict[tuple[str, str], object] = {}
    for c in corpus:
        by_name.setdefault((c.file_path, c.qualified_name), c)

    linked: list[dict] = []
    stats = {
        "docs_in_sample": len(sample["docs"]),
        "s5_corpus_chunks_at_same_commit": len(corpus),
        "reproduced_sample_ids": reproduced,
        "reproduced_sample_matches_sample_file": sorted(reproduced) == sorted(d["chunk_id"] for d in sample["docs"]),
    }
    for d in sample["docs"]:
        cid = d["chunk_id"]
        chunk = by_id.get(cid)
        method = "imported S5 sampler + exact chunk_id match"
        if chunk is None:
            chunk = by_name.get((d.get("file_path", ""), d.get("qualified_name", "")))
            method = "fallback: file_path + qualified_name match"
        if chunk is None:
            stats.setdefault("unlinked", []).append(cid)
            continue
        linked.append({
            "chunk_id": cid,
            "chunk": chunk,
            "doc": d["doc"],
            "match_method": method,
            "in_reproduced_sample": cid in reproduced,
        })
    stats["docs_linked"] = len(linked)
    stats["match_methods"] = sorted({l["match_method"] for l in linked})
    return linked, stats


# --------------------------------------------------------------------------
# Experiment
# --------------------------------------------------------------------------

def _cosine(a, b) -> float:
    import numpy as np
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-9))


def run_experiment(linked: list[dict], embed_fn) -> tuple[list[dict], list[dict], dict, float]:
    import numpy as np
    checks: list[dict] = []
    skipped: list[dict] = []
    cost = {"hash_ms": [], "hash_ast_ms": [], "hash_similarity_ms": []}
    doc_embed_times: list[float] = []
    for item in linked:
        chunk, doc = item["chunk"], item["doc"]
        content = chunk.content
        base_hash = sha256_text(content)
        base_fp = ast_fingerprint(content, chunk.language)
        t0 = time.perf_counter()
        doc_vec = embed_fn([doc_text(doc)])[0]
        doc_embed_times.append((time.perf_counter() - t0) * 1000.0)
        doc_np = np.asarray(doc_vec, dtype=np.float32)
        dn = float(np.linalg.norm(doc_np))
        for cls in list(MUTATIONS):
            text, note = MUTATIONS[cls](content, chunk.language, chunk)
            if text is None:
                skipped.append({"chunk_id": item["chunk_id"], "variant": cls, "reason": note})
                continue
            if not parse_ok(text, chunk.language):
                skipped.append({"chunk_id": item["chunk_id"], "variant": cls, "reason": "mutated chunk does not parse (harness defect)"})
                continue
            t0 = time.perf_counter()
            d1_fired = sha256_text(text) != base_hash
            cost["hash_ms"].append((time.perf_counter() - t0) * 1000.0)
            t0 = time.perf_counter()
            d2_fired = ast_fingerprint(text, chunk.language) != base_fp
            cost["hash_ast_ms"].append((time.perf_counter() - t0) * 1000.0)
            t0 = time.perf_counter()
            vec = embed_fn([text])[0]
            vec_np = np.asarray(vec, dtype=np.float32)
            dot = float(np.dot(vec_np, doc_np))
            n1 = float(np.linalg.norm(vec_np))
            sim = float(dot / (n1 * dn + 1e-9))
            if sim > 1.0:
                sim = 1.0
            elif sim < -1.0:
                sim = -1.0
            cost["hash_similarity_ms"].append((time.perf_counter() - t0) * 1000.0)
            checks.append({
                "chunk_id": item["chunk_id"],
                "variant": cls,
                "mutation_note": note,
                "d1_hash_fired": d1_fired,
                "d2_ast_fired": d2_fired,
                "d3_similarity": round(sim, 6),
            })
    doc_embed_ms = float(sum(doc_embed_times) / len(doc_embed_times)) if doc_embed_times else 0.0
    order = {k: i for i, k in enumerate(MUTATIONS)}
    checks.sort(key=lambda r: (r["chunk_id"], order.get(r["variant"], 99)))
    skipped.sort(key=lambda r: (r["chunk_id"], r.get("variant", r.get("mutation_class", ""))))
    return checks, skipped, cost, doc_embed_ms


def cosine_scores(vec, doc_vec) -> float:
    import numpy as np
    v = np.asarray(vec, dtype=np.float32)
    d = np.asarray(doc_vec, dtype=np.float32)
    return float(np.dot(v, d) / (np.linalg.norm(v) * np.linalg.norm(d) + 1e-9))


def _repo_commit() -> str | None:
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", default=",".join(str(t) for t in THRESHOLDS), help="comma-separated D3 sweep thresholds")
    args = ap.parse_args()
    thresholds = tuple(float(x) for x in args.thresholds.split(","))
    import numpy as np  # noqa: F401
    from fastembed import TextEmbedding
    sample = json.loads(SAMPLE_DOCS.read_text())
    linked, linkage = link_docs_to_chunks(sample)
    if not linked:
        print("No sample doc could be linked to a chunk; nothing to measure.")
        return 1
    t0 = time.perf_counter()
    try:
        model = TextEmbedding(model_name=EMBED_MODEL, cache_dir=str(CACHE_DIR))
    except Exception as exc:  # noqa: BLE001
        print(f"EMBED MODEL LOAD FAILED: {type(exc).__name__}: {str(exc)[:200]}")
        return 1
    load_s = time.perf_counter() - t0
    print(f"loaded {EMBED_MODEL} in {load_s:.1f}s  rss={rss_mb()} MB", flush=True)

    def embed_fn(texts):
        return [np.asarray(v, dtype=np.float32) for v in model.passage_embed(texts)]

    checks, skipped, cost, doc_embed_ms = run_experiment(linked, embed_fn)
    print(f"checks={len(checks)} skipped={len(skipped)}  rss={rss_mb()} MB", flush=True)
    sweep: list[dict] = []
    for th in thresholds:
        row: dict = {"threshold": th}
        for var in MUTATIONS:
            fired = sum(1 for c in checks if c["variant"] == var and c["d3_similarity"] < th)
            total = sum(1 for c in checks if c["variant"] == var)
            row[f"d3_fired_{var}"] = fired
            row[f"total_{var}"] = total
        row["tp_M1"] = row.get("d3_fired_M1_identity", 0)
        row["tp_M2"] = row.get("d3_fired_M2_behavior", 0)
        row["tp_M3"] = row.get("d3_fired_M3_structure", 0)
        row["tp_total"] = row["tp_M1"] + row["tp_M2"] + row["tp_M3"]
        row["fp_unmutated"] = row.get("d3_fired_unmutated", 0)
        row["fp_N1"] = row.get("d3_fired_N1_comment_only", 0)
        row["fp_N2"] = row.get("d3_fired_N2_whitespace_only", 0)
        row["fp_total_negatives"] = row["fp_unmutated"] + row["fp_N1"] + row["fp_N2"]
        sweep.append(row)
    chosen_threshold = None
    for row in sweep:
        if row["fp_unmutated"] == 0:
            chosen_threshold = row["threshold"]
            break
    if chosen_threshold is None and sweep:
        chosen_threshold = sweep[-1]["threshold"]

    def _mean(a):
        return round(float(sum(a) / len(a)), 4) if a else 0.0

    def _median(a):
        import statistics
        return round(float(statistics.median(a)), 4) if a else 0.0
    cost_summary = {
        "hash_ms": _mean(cost["hash_ms"]),
        "hash_ms_median": _median(cost["hash_ms"]),
        "hash_ast_ms": _mean(cost["hash_ast_ms"]),
        "hash_ast_ms_median": _median(cost["hash_ast_ms"]),
        "similarity_ms": _mean(cost["hash_similarity_ms"]),
        "similarity_ms_median": _median(cost["hash_similarity_ms"]),
        "doc_embed_ms": round(float(doc_embed_ms), 4),
        "hash_ms_raw": [round(x, 4) for x in cost["hash_ms"]],
        "hash_ast_ms_raw": [round(x, 4) for x in cost["hash_ast_ms"]],
        "similarity_ms_raw": [round(x, 4) for x in cost["hash_similarity_ms"]],
    }
    detection_rates = {}
    for var in list(MUTATIONS):
        tot = sum(1 for c in checks if c["variant"] == var)
        d1 = sum(1 for c in checks if c["variant"] == var and c["d1_hash_fired"])
        d2 = sum(1 for c in checks if c["variant"] == var and c["d2_ast_fired"])
        d3 = sum(1 for c in checks if c["variant"] == var and chosen_threshold is not None and c["d3_similarity"] < chosen_threshold)
        detection_rates[var] = {"total": tot, "d1_hash_rate": round(d1 / tot, 4) if tot else 0, "d2_ast_rate": round(d2 / tot, 4) if tot else 0, "d3_sim_rate_at_chosen": round(d3 / tot, 4) if tot else 0, "d1_fired": d1, "d2_fired": d2, "d3_fired": d3}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "spike": "S6",
        "subject": "Documentation drift detection",
        "research_row": "Sentra_research.md \u00a79, row S6 (D11 doc-time reference vector, D13 drift methodology)",
        "toolchain": {"embed_model": EMBED_MODEL, "cache_dir": str(CACHE_DIR.relative_to(REPO_ROOT)) if CACHE_DIR.is_relative_to(REPO_ROOT) else str(CACHE_DIR), "chunker": "spikes/s1_tree_sitter/chunker.py"},
        "linkage": {"docs_linked": linkage.get("docs_linked"), "docs_in_sample": linkage.get("docs_in_sample"), "match_methods": linkage.get("match_methods"), "reproduced_sample_ids": linkage.get("reproduced_sample_ids"), "reproduced_match": linkage.get("reproduced_sample_matches_sample_file"), "reproduced_sample_matches_sample_file": linkage.get("reproduced_sample_matches_sample_file"), "s5_corpus_chunks_at_same_commit": linkage.get("s5_corpus_chunks_at_same_commit")},
        "corpus": {"repo": REPO.name, "path": str(REPO.relative_to(REPO_ROOT)), "commit": _repo_commit()},
        "checks": checks,
        "threshold_sweep": sweep,
        "chosen_threshold": chosen_threshold,
        "detection_rates_at_chosen": detection_rates,
        "cost": cost_summary,
        "skipped": skipped,
        "summary": f"S6 drift: {len(checks)} checks over {len(linked)} linked chunks; chosen_threshold={chosen_threshold} (lowest with 0 FP on unmutated); sweep={len(sweep)} thresholds",
    }
    OUT.write_text(json.dumps(evidence, indent=2, sort_keys=False))
    print("=" * 74)
    print("S6 — DOCUMENTATION DRIFT DETECTION")
    print("=" * 74)
    print(f"  linked           : {linkage.get('docs_linked')}/{linkage.get('docs_in_sample')} docs (methods: {linkage.get('match_methods')})")
    print(f"  reproduced_match : {linkage.get('reproduced_sample_matches_sample_file')}")
    print(f"  checks           : {len(checks)}  skipped: {len(skipped)}")
    for var in list(MUTATIONS):
        dr = detection_rates[var]
        print(f"    {var:20s} total={dr['total']}  d1={dr['d1_fired']}/{dr['total']} ({dr['d1_hash_rate']:.0%})  d2={dr['d2_fired']}/{dr['total']} ({dr['d2_ast_rate']:.0%})  d3@{chosen_threshold}={dr['d3_fired']}/{dr['total']} ({dr['d3_sim_rate_at_chosen']:.0%})")
    print(f"  threshold_sweep  : {len(sweep)} thresholds {list(thresholds)}")
    for row in sweep:
        print(f"    th={row['threshold']:.2f}  tp(M1/M2/M3)={row['tp_M1']}/{row['tp_M2']}/{row['tp_M3']}  fp(unmut/N1/N2)={row['fp_unmutated']}/{row['fp_N1']}/{row['fp_N2']}")
    print(f"  chosen_threshold : {chosen_threshold}  (lowest with 0 FP on unmutated)")
    print(f"  cost ms/check    : hash={cost_summary['hash_ms']:.3f}  ast={cost_summary['hash_ast_ms']:.3f}  similarity={cost_summary['similarity_ms']:.3f}  doc_embed={cost_summary['doc_embed_ms']:.3f}")
    print(f"  rss              : {rss_mb()} MB")
    print(f"\n  wrote {OUT.relative_to(REPO_ROOT)}")
    del model
    gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
