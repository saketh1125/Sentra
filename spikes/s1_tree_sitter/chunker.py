"""
Sentra P0 / Spike S1 — Syntax-aware chunker (Tree-sitter).

This module is deliberately written as *production-shaped* code, not throwaway
spike scratch: if S1 validates, this logic carries forward into P2 (Repository
Knowledge Core). Anything that fails the spike is measured and reported, not
papered over.

Design decisions are exposed as parameters rather than hard-coded, because the
Sentra research document lists "Parser / chunker strategy" as open decision D8.
The spike measures these options so D8 can be decided from evidence.

Scope (Sentra documented language scope): Python, JavaScript, TypeScript.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from tree_sitter import Language, Node, Parser

# --------------------------------------------------------------------------
# Language registry
# --------------------------------------------------------------------------

# Extension -> (language key, human name). Kept explicit so an unsupported file
# is never silently mis-parsed with a fallback grammar.
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

LANGUAGE_NAMES = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "tsx": "TSX",
}

_LANGUAGE_CACHE: dict[str, Language] = {}


def get_language(key: str) -> Language:
    """Load a Tree-sitter Language object, cached per process."""
    if key in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[key]
    if key == "python":
        import tree_sitter_python
        lang = Language(tree_sitter_python.language())
    elif key == "javascript":
        import tree_sitter_javascript
        lang = Language(tree_sitter_javascript.language())
    elif key in ("typescript", "tsx"):
        import tree_sitter_typescript
        mod = (
            tree_sitter_typescript.language_tsx()
            if key == "tsx"
            else tree_sitter_typescript.language_typescript()
        )
        lang = Language(mod)
    else:
        raise ValueError(f"unsupported language key: {key}")
    _LANGUAGE_CACHE[key] = lang
    return lang


def language_for_path(path: Path) -> str | None:
    return EXTENSION_MAP.get(path.suffix.lower())


# --------------------------------------------------------------------------
# Chunk model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit. `content_hash` drives incremental re-processing
    (FR11) and documentation regeneration (FR4)."""

    file_path: str
    language: str
    kind: str  # module | function | class | method
    name: str
    qualified_name: str  # e.g. "Session.send" — improves citation readability
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    content: str
    content_hash: str
    byte_start: int
    byte_end: int
    parent_kind: str | None = None

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "kind": self.kind,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content_hash": self.content_hash,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "parent_kind": self.parent_kind,
            "line_count": self.line_count,
        }


@dataclass
class ChunkerConfig:
    """Open decision D8, expressed as configuration.

    Defaults chosen for the spike; the spike exists to challenge them.
    """

    # Whether to keep @decorator / export lines inside the function chunk.
    # Default True: a decorator materially changes what a function *is*, and
    # dropping it would make generated documentation misleading.
    include_decorators: bool = True

    # Emit a whole-file chunk in addition to the per-function chunks. Module
    # chunks give M1 a high-level view and give M6 a fallback "documented unit".
    emit_module_chunks: bool = True

    # Functions longer than this are emitted whole (correctness first) but also
    # flagged, because very large chunks retrieve poorly. Splitting is D8's
    # open sub-question; the spike measures how common the problem is.
    oversized_line_threshold: int = 200

    # Minimum lines for a chunk to be emitted. Filters trivial one-liners that
    # add retrieval noise without adding retrieval value.
    min_line_count: int = 1


# --------------------------------------------------------------------------
# Node-type tables (deliberately explicit; no heuristics on node text)
# --------------------------------------------------------------------------

_PY_FUNCTION = {"function_definition"}
_PY_CLASS = {"class_definition"}
_JS_FUNCTION = {
    "function_declaration",
    "generator_function_declaration",
    "arrow_function",
    "function_expression",
    "method_definition",
}
_JS_CLASS = {"class_declaration", "class"}

_DECORATED = {"decorated_definition"}
_EXPORT = {"export_statement"}


class Chunker:
    """Turns a source file into syntax-aware chunks."""

    def __init__(self, config: ChunkerConfig | None = None):
        self.config = config or ChunkerConfig()

    # -- public -----------------------------------------------------------

    def chunk_source(
        self,
        source: bytes,
        file_path: str,
        language: str,
    ) -> tuple[list[Chunk], dict]:
        """Return (chunks, diagnostics) for one file.

        diagnostics reports has_error / parse_ok so the caller can measure the
        parse rate rather than assuming it.
        """
        parser = Parser(get_language(language))
        tree = parser.parse(source)
        root = tree.root_node

        diagnostics = {
            "has_error": root.has_error,
            "root_type": root.type,
            "parse_time_ms": 0.0,
            "oversized_chunk_count": 0,
        }

        chunks: list[Chunk] = []
        if self.config.emit_module_chunks:
            module_chunk = self._make_chunk(
                root, source, file_path, language, kind="module", name="<module>"
            )
            if module_chunk and module_chunk.line_count >= self.config.min_line_count:
                chunks.append(module_chunk)

        for node, parent in self._iter_definitions(root, language):
            # A decorated_definition / export_statement wrapper and its inner
            # definition node span the SAME byte range. Emitting both produced
            # duplicate chunks (measured: 4 duplicate ranges in requests/auth.py
            # alone, e.g. HTTPBasicAuth.__init__ twice), which would corrupt
            # retrieval results and double-count findings. Since the wrapper is
            # emitted (and it carries the decorators), skip the inner node.
            if parent is not None and parent.type in _DECORATED | _EXPORT:
                continue
            kind, name = self._classify(node, language)
            if kind is None:
                continue
            qualified = self._qualified_name(node, name, language, parent)
            target = node
            # A decorator wrapper sits outside the function node's own extent.
            if self.config.include_decorators and parent is not None:
                if parent.type in _DECORATED:
                    target = parent
                elif parent.type in _EXPORT:
                    target = parent
            chunk = self._make_chunk(
                target,
                source,
                file_path,
                language,
                kind=kind,
                name=name,
                qualified_name=qualified,
                parent_kind=self._classify(parent, language)[0] if parent else None,
            )
            if chunk is None:
                continue
            if chunk.line_count < self.config.min_line_count:
                continue
            if chunk.line_count > self.config.oversized_line_threshold:
                diagnostics["oversized_chunk_count"] += 1
            chunks.append(chunk)

        return chunks, diagnostics

    def chunk_file(self, path: Path, root: Path | None = None) -> tuple[list[Chunk], dict]:
        language = language_for_path(path)
        rel = str(path.relative_to(root)) if root else str(path)
        if language is None:
            return [], {"skipped": "unsupported_extension"}
        try:
            source = path.read_bytes()
        except OSError as exc:  # unreadable file: record, do not crash the run
            return [], {"skipped": f"read_error:{exc.__class__.__name__}"}
        return self.chunk_source(source, rel, language)

    # -- traversal --------------------------------------------------------

    def _iter_definitions(
        self, root: Node, language: str
    ) -> Iterator[tuple[Node, Node | None]]:
        """Yield (definition_node, parent_definition_node) depth-first."""
        stack: list[tuple[Node, Node | None]] = [(root, None)]
        while stack:
            node, parent = stack.pop()
            yield node, parent
            for child in reversed(node.children):
                stack.append((child, node))

    def _classify(self, node: Node | None, language: str) -> tuple[str | None, str]:
        if node is None:
            return None, ""
        t = node.type
        if t in _DECORATED:
            inner = node.child_by_field_name("definition")
            return self._classify(inner, language)
        if t in _EXPORT:
            inner = node.child_by_field_name("declaration")
            return self._classify(inner, language)
        if language == "python":
            if t in _PY_FUNCTION:
                return "function", (node.child_by_field_name("name") or _NULL).text.decode(
                    "utf8", "replace"
                ) if node.child_by_field_name("name") else "<anonymous>"
            if t in _PY_CLASS:
                name_node = node.child_by_field_name("name")
                return "class", name_node.text.decode("utf8", "replace") if name_node else "<anonymous>"
            return None, ""
        if t in _JS_FUNCTION:
            name_node = node.child_by_field_name("name")
            if name_node:
                return ("method" if _in_class(node) else "function"), name_node.text.decode(
                    "utf8", "replace"
                )
            # Anonymous arrow / function expression: use the assigned binding.
            var = _assigned_name(node)
            return ("function" if var else "function"), var or "<anonymous>"
        if t in _JS_CLASS:
            name_node = node.child_by_field_name("name")
            return "class", name_node.text.decode("utf8", "replace") if name_node else "<anonymous>"
        return None, ""

    def _qualified_name(
        self, node: Node, name: str, language: str, parent: Node | None
    ) -> str:
        """Build `Outer.inner` / `Class.method`.

        Ancestors are walked upward, but a node is only appended if it actually
        *encloses* this node with a strictly larger span. Without that guard,
        wrappers that share a byte range produce self-nested names such as
        `to_key_val_list.to_key_val_list`, which are worse than no name at all
        because they corrupt qualified-name-based lookups downstream.
        """
        parts = [name]
        cur = node.parent
        while cur is not None:
            pkind, pname = self._classify(cur, language)
            if (
                pkind in ("class", "function")
                and pname
                and pname != "<anonymous>"
                and (cur.start_byte, cur.end_byte) != (node.start_byte, node.end_byte)
                and pname != parts[-1]
            ):
                parts.append(pname)
            cur = cur.parent
        return ".".join(reversed(parts))

    # -- chunk construction ------------------------------------------------

    def _make_chunk(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        language: str,
        kind: str,
        name: str,
        qualified_name: str | None = None,
        parent_kind: str | None = None,
    ) -> Chunk | None:
        start_byte, end_byte = node.start_byte, node.end_byte
        if end_byte <= start_byte:
            return None
        content = source[start_byte:end_byte].decode("utf8", "replace")
        if not content.strip():
            return None
        return Chunk(
            file_path=file_path,
            language=language,
            kind=kind,
            name=name,
            qualified_name=qualified_name or name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            content=content,
            content_hash=hashlib.sha256(content.encode("utf8")).hexdigest(),
            byte_start=start_byte,
            byte_end=end_byte,
            parent_kind=parent_kind,
        )


class _Null:
    """Sentinel so `child_by_field_name(...) or _NULL` is safe."""


def _in_class(node: Node) -> bool:
    cur = node.parent
    while cur is not None:
        if cur.type in _PY_CLASS or cur.type in _JS_CLASS:
            return True
        cur = cur.parent
    return False


def _assigned_name(node: Node) -> str | None:
    """Recover a name for `const f = () => {}` / `f = function(){}`."""
    cur = node.parent
    if cur is None:
        return None
    for field_name in ("name", "declarator", "left", "key"):
        n = cur.child_by_field_name(field_name)
        if n is not None:
            for sub in _descendants(n, depth=2):
                if sub.type == "identifier":
                    return sub.text.decode("utf8", "replace")
    return None


def _descendants(node: Node, depth: int = 1):
    if depth < 0:
        return
    yield node
    for child in node.children:
        yield from _descendants(child, depth - 1)