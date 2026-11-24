"""AE-32B: bounded, read-only repository evidence tools for future LLM callers.

The module builds a source-grounded graph from the inspected repository without
importing or executing target code. It exposes JSON-schema tool definitions and a
single validated dispatcher, but intentionally does not contact an LLM provider
or run a tool-use loop; that is reserved for AE-32C.
"""
from __future__ import annotations

import ast
import configparser
import fnmatch
import hashlib
import json
import math
import os
import re
import stat
import tomllib
from datetime import date, datetime
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

import yaml

from audit_engine.semantic_audit.ae32a.audit import (
    SOURCE_SUFFIXES,
    audit_repository,
)
from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService

SCHEMA_VERSION = "ae32b/repository-evidence-tools/v1"
GRAPH_PROJECTION_VERSION = "ae32b/source-evidence-projection/v3"
MAX_QUERY_CHARS = 240
MAX_SEARCH_RESULTS = 30
MAX_GRAPH_RESULTS = 50
MAX_GRAPH_VISITED_NODES = 2000
MAX_GRAPH_TRAVERSAL_STEPS = 10000
MAX_WORKFLOW_PATH_VISITS = 5000
MAX_WORKFLOW_CANDIDATES = 500
MAX_NEIGHBOR_DEPTH = 4
MAX_PATH_DEPTH = 8
MAX_READ_LINES = 200
MAX_READ_CHARS = 12000
MAX_SNIPPET_CHARS = 420
MAX_OUTPUT_STRING_CHARS = 16000
MAX_TOOL_RESPONSE_BYTES = 250000
MAX_STRUCTURED_RECORD_DEPTH = 24
MAX_STRUCTURED_RECORD_ITEMS = 10000
MAX_STRUCTURED_STRING_CHARS = 16000

_EXCLUDED_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox", "node_modules", "dist", "build",
})
_EXCLUDED_PREFIXES = (
    "state/", "output/", "artifacts/", ".graph-state/", ".cache/",
)
_SENSITIVE_BASENAMES = frozenset({
    "credentials.json", "credentials.yaml", "credentials.yml", "secrets.json",
    "secrets.yaml", "secrets.yml", "service-account.json", "id_rsa", "id_ed25519",
})
_SENSITIVE_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".keystore"})
_SECRET_KEY = r"(?:[A-Za-z0-9_-]*(?:API[_-]?(?:KEY|TOKEN)|ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|AUTH[_-]?TOKEN|PASSWORD|CLIENT[_-]?SECRET|SECRET|TOKEN|AUTHORIZATION))"
_SECRET_ASSIGNMENT = re.compile(
    rf"(?im)(\b{_SECRET_KEY}\b\s*=\s*)(['\"])([^'\"\r\n]{{4,}})\2"
)
_SECRET_COLON_QUOTED = re.compile(
    rf"(?im)(['\"]?{_SECRET_KEY}['\"]?\s*:\s*)(['\"])([^'\"\r\n]{{4,}})\2"
)
_SECRET_YAML = re.compile(
    rf"(?im)^(\s*{_SECRET_KEY}\s*:\s*)(?!['\"])([^\s#][^\r\n#]*)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_TOKEN_SHAPES = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
)
_REVISION_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_SENSITIVE_FIELD_NAME = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth(?:orization)?|password|client[_-]?secret|secret|credential)")


class EvidenceToolError(ValueError):
    """Expected, safe-to-return evidence-tool failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> str:
    """Serialize canonical JSON strictly; non-finite numbers are not JSON."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class _StructuredRecordError(ValueError):
    """A structured history record cannot be represented safely."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _normalize_record_value(
    value: Any,
    *,
    active: set[int] | None = None,
    depth: int = 0,
    budget: list[int] | None = None,
    issue_codes: list[str] | None = None,
) -> Any:
    """Convert safe YAML/JSON values to bounded, acyclic JSON-compatible data.

    YAML dates are normalized to ISO-8601 strings. Non-finite floats are
    represented explicitly and reported. Recursive aliases, excessive nesting,
    oversized structures, non-string mapping keys, and unsupported Python values
    reject the record rather than entering the evidence graph.
    """
    if active is None:
        active = set()
    if budget is None:
        budget = [0]
    if issue_codes is None:
        issue_codes = []
    if depth > MAX_STRUCTURED_RECORD_DEPTH:
        raise _StructuredRecordError("maximum_nesting_depth")
    budget[0] += 1
    if budget[0] > MAX_STRUCTURED_RECORD_ITEMS:
        raise _StructuredRecordError("maximum_structured_items")

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        if len(value) > MAX_STRUCTURED_STRING_CHARS:
            issue_codes.append("string_value_truncated")
            return value[:MAX_STRUCTURED_STRING_CHARS] + "…<truncated>"
        return value
    if isinstance(value, int):
        if value.bit_length() > 4096:
            raise _StructuredRecordError("integer_too_large")
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        label = "nan" if math.isnan(value) else ("positive_infinity" if value > 0 else "negative_infinity")
        issue_codes.append("non_finite_number_normalized")
        return f"<non-finite-number:{label}>"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise _StructuredRecordError("recursive_value")
        active.add(identity)
        try:
            normalized: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise _StructuredRecordError("non_string_mapping_key")
                normalized[key] = _normalize_record_value(
                    item, active=active, depth=depth + 1, budget=budget, issue_codes=issue_codes
                )
            return normalized
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise _StructuredRecordError("recursive_value")
        active.add(identity)
        try:
            return [
                _normalize_record_value(
                    item, active=active, depth=depth + 1, budget=budget, issue_codes=issue_codes
                )
                for item in value
            ]
        finally:
            active.remove(identity)

    raise _StructuredRecordError("unsupported_value_type")


def _validate_revision(value: str | None, name: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip()
    if not _REVISION_RE.fullmatch(normalized):
        raise ValueError(f"{name} must be a 7–64 character hexadecimal revision or empty")
    return normalized.lower()


def _validate_root(root: str | Path) -> Path:
    supplied = Path(root).expanduser()
    if supplied.is_symlink():
        raise EvidenceToolError("unsafe_repository_root", "Repository root must not be a symlink")
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise EvidenceToolError("repository_root_unavailable", "Repository root cannot be resolved") from exc
    if not resolved.is_dir():
        raise EvidenceToolError("repository_root_not_directory", "Repository root must be a directory")
    return resolved


def _is_sensitive_path(rel: str) -> bool:
    path = PurePosixPath(rel)
    name = path.name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    if name in _SENSITIVE_BASENAMES or path.suffix.lower() in _SENSITIVE_SUFFIXES:
        return True
    # Avoid indexing likely credential material, but do not exclude test source
    # merely because its filename contains the word "secret".
    if "credentials" in name and path.suffix.lower() in {".json", ".yaml", ".yml", ".toml"}:
        return True
    return False


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceToolError("invalid_path", "path must be a non-empty repository-relative string")
    raw = value.strip()
    if "\\" in raw or raw.startswith("/"):
        raise EvidenceToolError("invalid_path", "Absolute paths and backslash-separated paths are not accepted")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceToolError("invalid_path", "Path traversal and non-canonical paths are not accepted")
    normalized = path.as_posix()
    if normalized.startswith(_EXCLUDED_PREFIXES) or any(part in _EXCLUDED_DIRS for part in path.parts):
        raise EvidenceToolError("path_out_of_scope", "Runtime, generated, or dependency-cache paths are outside the evidence scope")
    if _is_sensitive_path(normalized):
        raise EvidenceToolError("sensitive_path_blocked", "Credential-like files are not available to evidence tools")
    if path.suffix.lower() not in SOURCE_SUFFIXES:
        raise EvidenceToolError("unsupported_file_type", "The requested file type is outside the indexed text-source policy")
    return normalized


def _source_lines(text: str) -> list[str]:
    """Split physical source lines without treating Unicode separators as newlines."""
    lines = re.split(r"\r\n|\r|\n", text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _module_name(path: str, source_roots: tuple[str, ...] | list[str] = ()) -> str:
    normalized = PurePosixPath(path).as_posix()
    parts = list(PurePosixPath(normalized).parts)
    if not parts or PurePosixPath(normalized).suffix.lower() != ".py":
        return ""
    for root in sorted((str(item).strip("/") for item in source_roots if str(item).strip("/")),
                       key=lambda item: (-len(item.split("/")), -len(item))):
        if normalized.startswith(root + "/"):
            parts = list(PurePosixPath(normalized[len(root) + 1:]).parts)
            break
    if not parts:
        return ""
    if parts[-1].lower() == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = PurePosixPath(parts[-1]).stem
    return ".".join(parts)


def _contains_identifier_reference(text: str, identifier: str) -> bool:
    """Match an identifier-like module reference without accepting prefixes."""
    candidate = identifier.strip()
    if candidate.startswith("module:"):
        candidate = candidate[len("module:"):]
    if not candidate:
        return False
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(candidate) + r"(?![A-Za-z0-9_])", text, re.IGNORECASE) is not None


def _file_kind(path: str) -> str:
    pure = PurePosixPath(path)
    name = pure.name.lower()
    if path.startswith(".github/workflows/") and pure.suffix.lower() in {".yml", ".yaml"}:
        return "WorkflowDefinition"
    if path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py"):
        return "TestFile"
    if path.startswith(("docs/", "specs/")) or pure.suffix.lower() == ".md":
        return "DocumentationFile"
    if pure.suffix.lower() == ".py":
        return "PythonSourceFile"
    return "ConfigurationOrDataFile"


def _redact_text(text: str) -> str:
    """Redact the complete value before any presentation truncation."""
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>{m.group(2)}", text)
    text = _SECRET_COLON_QUOTED.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>{m.group(2)}", text)
    text = _SECRET_YAML.sub(lambda m: f"{m.group(1)}<redacted>", text)
    text = _BEARER.sub("Bearer <redacted>", text)
    text = _TOKEN_SHAPES.sub("<redacted-token>", text)
    return text


def _redact_then_truncate(text: str, limit: int) -> str:
    """Apply redaction to the full input before limiting its visible prefix."""
    redacted = _redact_text(text)
    if len(redacted) <= limit:
        return redacted
    return redacted[:limit] + "…<truncated-after-redaction>"


def _sanitize_output_value(
    value: Any,
    *,
    field_name: str | None = None,
    active: set[int] | None = None,
    depth: int = 0,
) -> Any:
    """Return a detached, redacted, strict-JSON-compatible output structure."""
    if active is None:
        active = set()
    if depth > 32:
        return "<omitted:maximum-nesting-depth>"
    if field_name and _SENSITIVE_FIELD_NAME.search(field_name) and value is not None:
        return "<redacted>"
    if value is None or isinstance(value, (bool, str)):
        if isinstance(value, str):
            return _redact_then_truncate(value, MAX_OUTPUT_STRING_CHARS)
        return value
    if isinstance(value, int):
        return value if value.bit_length() <= 4096 else "<omitted:integer-too-large>"
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return "<omitted:non-finite-number>"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            return "<omitted:cyclic-reference>"
        active.add(identity)
        try:
            result: dict[str, Any] = {}
            for raw_key, item in value.items():
                key = raw_key if isinstance(raw_key, str) else "<non-string-key>"
                safe_key = _redact_then_truncate(key, 240)
                if safe_key in result:
                    suffix = 2
                    while f"{safe_key}#{suffix}" in result:
                        suffix += 1
                    safe_key = f"{safe_key}#{suffix}"
                result[safe_key] = _sanitize_output_value(
                    item, field_name=key, active=active, depth=depth + 1
                )
            return result
        finally:
            active.remove(identity)
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            return "<omitted:cyclic-reference>"
        active.add(identity)
        try:
            return [
                _sanitize_output_value(item, active=active, depth=depth + 1)
                for item in value
            ]
        finally:
            active.remove(identity)
    return f"<omitted:unsupported-{type(value).__name__}>"


def _read_snapshot_file(root: Path, relative_path: str, expected_size: int) -> bytes:
    """Read a manifest file without following symlinked path components where supported."""
    parts = PurePosixPath(relative_path).parts
    if not parts or expected_size < 0:
        raise OSError("invalid manifest file entry")

    supports_dir_fd = getattr(os, "supports_dir_fd", set())
    if (os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")
            and os.open in supports_dir_fd):
        directory_fds: list[int] = []
        file_fd: int | None = None
        try:
            root_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            directory_fds.append(root_fd)
            current_fd = root_fd
            for part in parts[:-1]:
                next_fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current_fd
                )
                directory_fds.append(next_fd)
                current_fd = next_fd
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
                raise OSError("manifest file type or size changed")
            with os.fdopen(file_fd, "rb", closefd=False) as stream:
                data = stream.read(expected_size + 1)
            if len(data) != expected_size:
                raise OSError("manifest file size changed while reading")
            return data
        finally:
            if file_fd is not None:
                os.close(file_fd)
            for descriptor in reversed(directory_fds):
                os.close(descriptor)

    # Portable fallback: verify each component before opening, refuse a symlink
    # at the final component where O_NOFOLLOW exists, and recheck containment.
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise OSError("symlinked manifest path is not permitted")
    resolved = cursor.resolve(strict=True)
    resolved.relative_to(root)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    file_fd = os.open(str(resolved), flags)
    try:
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
            raise OSError("manifest file type or size changed")
        with os.fdopen(file_fd, "rb", closefd=False) as stream:
            data = stream.read(expected_size + 1)
        if len(data) != expected_size:
            raise OSError("manifest file size changed while reading")
        return data
    finally:
        os.close(file_fd)


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, module: str, path: str, source_sha256: str):
        self.module = module
        self.path = path
        self.source_sha256 = source_sha256
        self.stack: list[str] = []
        self.symbols: list[dict[str, Any]] = []

    def _visit_named(self, node: ast.AST, kind: str, name: str) -> None:
        qualified = ".".join([*self.stack, name])
        line = int(getattr(node, "lineno", 1))
        legacy_id = f"symbol:{self.module}::{qualified}"
        occurrence_payload = {
            "path": self.path, "source_sha256": self.source_sha256,
            "module": self.module, "qualified_name": qualified,
            "line": line, "kind": kind,
        }
        occurrence_digest = hashlib.sha256(_canonical_json(occurrence_payload).encode("utf-8")).hexdigest()[:24]
        self.symbols.append({
            "name": name,
            "qualified_name": qualified,
            "module": self.module,
            "path": self.path,
            "line": line,
            "kind": kind,
            "symbol_id": legacy_id,
            "node_id": f"symbol-occurrence:{occurrence_digest}",
            "occurrence_id": f"symbol-occurrence:{occurrence_digest}",
        })
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_named(node, "class", node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_named(node, "function", node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_named(node, "async_function", node.name)



def _dotted_ast_name(node: ast.AST) -> tuple[str, ...]:
    """Return a dotted expression as identifier parts, or an empty tuple."""
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        parent = _dotted_ast_name(node.value)
        return (*parent, node.attr) if parent else ()
    return ()


class _CallGraphVisitor(ast.NodeVisitor):
    """Resolve a deliberately conservative subset of Python call relationships.

    Only statically unambiguous calls are promoted to graph edges. Dynamic
    dispatch, arbitrary instance attributes, reflection, and alias assignments
    are intentionally left unresolved rather than guessed.
    """

    def __init__(
        self,
        *,
        module: str,
        path: str,
        source_sha256: str,
        symbol_nodes: Mapping[tuple[str, str], list[str]],
        module_nodes: Mapping[str, str],
        import_bindings: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.module = module
        self.path = path
        self.source_sha256 = source_sha256
        self.symbol_nodes = symbol_nodes
        self.module_nodes = module_nodes
        self.import_bindings = import_bindings
        self.scope: list[str] = []
        self.class_stack: list[str] = []
        self.current_symbol: str | None = None
        self.current_qualified: str | None = None
        self.edges: list[dict[str, Any]] = []
        self.call_sites = 0
        self.unresolved_calls = 0
        self.ambiguous_calls = 0

    def _unique_symbol(self, module: str, qualified: str) -> str | None:
        candidates = self.symbol_nodes.get((module, qualified), [])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            self.ambiguous_calls += 1
        return None

    def _resolve_name(self, name: str) -> str | None:
        # Prefer a nested/local definition, then the module-level definition.
        if self.current_qualified:
            nested = self._unique_symbol(
                self.module, f"{self.current_qualified}.{name}"
            )
            if nested:
                return nested
        if self.class_stack:
            method = self._unique_symbol(
                self.module, f"{self.class_stack[-1]}.{name}"
            )
            if method:
                return method
        local = self._unique_symbol(self.module, name)
        if local:
            return local

        binding = self.import_bindings.get(name)
        if not binding:
            return None
        if binding.get("kind") == "symbol":
            return self._unique_symbol(
                str(binding.get("module", "")),
                str(binding.get("name", "")),
            )
        # A module object is not itself a confirmed callable.
        return None

    def _resolve_dotted(self, parts: tuple[str, ...]) -> str | None:
        if not parts:
            return None
        if parts[0] == "self" and self.class_stack and len(parts) == 2:
            return self._unique_symbol(
                self.module, f"{self.class_stack[-1]}.{parts[1]}"
            )

        binding = self.import_bindings.get(parts[0])
        if not binding:
            return None

        if binding.get("kind") == "symbol":
            # Calling a method on an imported class/function is not promoted:
            # the receiver's runtime type may be different from the imported
            # definition.
            return None

        base_module = str(binding.get("module", ""))
        remainder = list(parts[1:])
        if not base_module:
            return None

        # Find the longest repository module prefix represented by this import
        # binding, then treat the remaining identifiers as a symbol path.
        module_candidates = [base_module]
        candidate = base_module
        for item in remainder:
            candidate = f"{candidate}.{item}"
            if candidate in self.module_nodes:
                module_candidates.append(candidate)

        selected_module = module_candidates[-1]
        consumed = len(selected_module.split(".")) - len(base_module.split("."))
        symbol_parts = remainder[consumed:]
        if not symbol_parts:
            return None
        return self._unique_symbol(selected_module, ".".join(symbol_parts))

    def _record_call(self, node: ast.Call, target: str | None, resolution: str) -> None:
        if not self.current_symbol:
            return
        if target is None or target == self.current_symbol:
            self.unresolved_calls += 1 if target is None else 0
            return
        self.edges.append({
            "source": self.current_symbol,
            "target": target,
            "line": getattr(node, "lineno", None),
            "resolution_kind": resolution,
        })

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.scope.append(node.name)
        # Class-body calls are deliberately not attributed to a callable
        # symbol. Constructor/method relationships are captured at call sites.
        previous_symbol = self.current_symbol
        previous_qualified = self.current_qualified
        self.current_symbol = None
        self.current_qualified = None
        self.generic_visit(node)
        self.current_symbol = previous_symbol
        self.current_qualified = previous_qualified
        self.scope.pop()
        self.class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join([*self.scope, node.name])
        target_symbol = self._unique_symbol(self.module, qualified)
        previous_symbol = self.current_symbol
        previous_qualified = self.current_qualified
        self.current_symbol = target_symbol
        self.current_qualified = qualified
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()
        self.current_symbol = previous_symbol
        self.current_qualified = previous_qualified

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.call_sites += 1
        parts = _dotted_ast_name(node.func)
        target = None
        resolution = ""
        if len(parts) == 1:
            target = self._resolve_name(parts[0])
            resolution = "name"
        elif parts:
            target = self._resolve_dotted(parts)
            resolution = "dotted"
        if target is None and self.current_symbol:
            self.unresolved_calls += 1
        self._record_call(node, target, resolution)
        self.generic_visit(node)


def _tool(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def build_tool_definitions() -> list[dict[str, Any]]:
    """Return provider-neutral OpenAI-compatible function tool declarations."""
    return [
        _tool("repository_summary", "Return the indexed source snapshot, graph size, relation counts, and provenance. Does not execute repository code."),
        _tool("search_repository", "Search indexed, non-sensitive text sources. Returns bounded snippets with exact path, line, and file hash.", {
            "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
            "mode": {"type": "string", "enum": ["both", "content", "path"]},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
        }, ["query"]),
        _tool("read_source_file", "Read a bounded line range from one indexed repository-relative text file. Sensitive paths are blocked and secret-like literals are redacted.", {
            "path": {"type": "string", "minLength": 1, "maxLength": 400},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
        }, ["path"]),
        _tool("search_symbols", "Search Python class/function definitions discovered with AST parsing; returns exact source path, line, kind, and source hash.", {
            "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
            "kind": {"type": "string", "enum": ["any", "class", "function", "async_function"]},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
        }, ["query"]),
        _tool("graph_neighbors", "Query graph relationships; impact accepts up to 24 additional changed_nodes.", {
            "node": {"type": "string", "minLength": 1, "maxLength": 500},
            "changed_nodes": {"type": "array", "items": {"type": "string"}, "maxItems": 24},
            "direction": {"type": "string", "enum": ["outgoing", "incoming", "both", "dependencies", "dependents", "impact"]},
            "relation_types": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 80}, "maxItems": 12},
            "max_depth": {"type": "integer", "minimum": 0, "maximum": MAX_NEIGHBOR_DEPTH},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_GRAPH_RESULTS},
        }, ["node"]),
        _tool("graph_path", "Test whether a bounded path exists between repository graph entities using the SemanticGraphAnalysisService. CALLS edges are conservative AST-resolved invocation observations.", {
            "source": {"type": "string", "minLength": 1, "maxLength": 500},
            "target": {"type": "string", "minLength": 1, "maxLength": 500},
            "direction": {"type": "string", "enum": ["outgoing", "incoming", "both"]},
            "relation_types": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 80}, "maxItems": 12},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": MAX_PATH_DEPTH},
        }, ["source", "target"]),
        _tool("find_related_tests", "Find test files with observed imports or explicit text references to a source file/module. Results distinguish imports from textual references.", {
            "target": {"type": "string", "minLength": 1, "maxLength": 500},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
        }, ["target"]),
        _tool("trace_execution_context", "Trace bounded static import callers, dependencies, Python entrypoint context, and active CI workflow candidates. target must be a resolvable repository-relative Python file path or module ID; function-level symbol IDs are not valid module targets. This is static analysis only and does not prove runtime execution.", {
            "target": {"type": "string", "minLength": 1, "maxLength": 500},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": MAX_NEIGHBOR_DEPTH},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_GRAPH_RESULTS},
        }, ["target"]),
        _tool("discover_case_context", "Discover bounded README, fixture-description, incident, case, and scenario metadata candidates. Returns line-numbered previews when a complete safe preview fits; candidates are not executed.", {
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
        }),
        _tool("find_workflow_context", "Find active workflow files with a statically observed invocation edge to a script or Python module.", {
            "target": {"type": "string", "minLength": 1, "maxLength": 500},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
        }, ["target"]),
        _tool("search_decision_history", "Search indexed decision, outcome, action, rule, link, and audit decision documentation without executing its code.", {
            "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
        }, ["query"]),
    ]


class RepositoryEvidenceTools:
    """Build a deterministic source graph and expose safe, bounded query tools."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        source_revision: str | None = None,
        runner_revision: str | None = None,
        graph_backend: str = "networkx",
    ) -> None:
        self.root = _validate_root(repo_root)
        if graph_backend not in {"networkx", "scipy", "igraph", "graph-tool", "snap", "reference"}:
            raise EvidenceToolError(
                "unsupported_graph_backend",
                "graph_backend must be selected by trusted configuration as a registered "
                "backend (networkx, scipy, igraph, graph-tool, snap) or reference",
            )
        self.graph_backend = graph_backend
        self.source_revision = _validate_revision(source_revision, "source_revision")
        self.runner_revision = _validate_revision(runner_revision, "runner_revision")
        self.report = audit_repository(
            self.root,
            source_revision=self.source_revision,
            runner_revision=self.runner_revision,
        )
        self.manifest_sha256 = self.report["audit"]["manifest_sha256"]
        self.python_source_roots = tuple(self.report.get("audit", {}).get("python_source_roots", []))
        self.manifest_rows = {
            row["path"]: row for row in self.report.get("source_manifest", [])
            if row.get("status") == "included"
        }
        self.structured_record_issues: list[dict[str, str]] = []
        self.structured_record_issue_count = 0
        self._structured_record_issue_keys: set[tuple[str, str]] = set()
        self.evidence_index_status = (
            "complete" if self.report.get("audit", {}).get("status") == "complete" else "incomplete"
        )
        self.contents: dict[str, str] = {}
        self.file_hashes: dict[str, str] = {}
        self.file_sizes: dict[str, int] = {}
        self.skipped_sensitive_files = 0
        self.skipped_non_utf8_files = 0
        self._load_indexed_content()
        self.graph = SemanticGraph()
        self.node_metadata: dict[str, dict[str, Any]] = {}
        self.file_nodes: dict[str, str] = {}
        self.module_nodes: dict[str, str] = {}
        self.module_paths: dict[str, list[str]] = defaultdict(list)
        self.module_identity_issues: list[dict[str, Any]] = []
        self.symbols: list[dict[str, Any]] = []
        self.symbols_by_id: dict[str, dict[str, Any]] = {}
        self.symbols_by_legacy_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._edge_keys: set[str] = set()
        self.call_graph_stats: dict[str, Any] = {}
        self._build_graph()
        if self.skipped_non_utf8_files or self.structured_record_issues or self.module_identity_issues:
            self.evidence_index_status = "incomplete"
        self.graph_fingerprint = self._graph_fingerprint()
        self._context_backend_bypasses: Counter[str] = Counter()
        self._context_operation_telemetry: dict[str, dict[str, int]] = {}
        self.graph_service = SemanticGraphAnalysisService(
            self.graph,
            semantic_context=SemanticContext(
                graph_schema_version="semantic_graph/v1",
                relationship_vocabulary_version="ae32b/source-relations/v1",
                projection_contract_version=GRAPH_PROJECTION_VERSION,
                analysis_contract_version="semantic_graph_analysis_contract/v2",
            ),
            traversal_backend=self.graph_backend,
            verify_backend_parity=True,
        )
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "repository_summary": self._repository_summary,
            "search_repository": self._search_repository,
            "read_source_file": self._read_source_file,
            "search_symbols": self._search_symbols,
            "graph_neighbors": self._graph_neighbors,
            "graph_path": self._graph_path,
            "find_related_tests": self._find_related_tests,
            "trace_execution_context": self._trace_execution_context,
            "discover_case_context": self._discover_case_context,
            "find_workflow_context": self._find_workflow_context,
            "search_decision_history": self._search_decision_history,
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return build_tool_definitions()

    def _record_structured_issue(self, path: str, code: str) -> None:
        self.evidence_index_status = "incomplete"
        key = (path, code)
        if key in self._structured_record_issue_keys:
            return
        self._structured_record_issue_keys.add(key)
        self.structured_record_issue_count += 1
        if len(self.structured_record_issues) < 500:
            self.structured_record_issues.append({"path": path, "code": code})

    def _load_indexed_content(self) -> None:
        for rel, row in sorted(self.manifest_rows.items()):
            if _is_sensitive_path(rel):
                self.skipped_sensitive_files += 1
                continue
            expected_hash = row.get("sha256")
            expected_size = row.get("size")
            if not isinstance(expected_hash, str) or not isinstance(expected_size, int) or expected_size < 0:
                raise EvidenceToolError("invalid_source_manifest", "Included source has an invalid size or digest")
            try:
                data = _read_snapshot_file(self.root, rel, expected_size)
            except (OSError, ValueError) as exc:
                raise EvidenceToolError(
                    "source_changed_during_index",
                    f"Indexed source changed, became unavailable, or crossed a path boundary: {rel}",
                ) from exc
            if _sha256(data) != expected_hash:
                raise EvidenceToolError(
                    "source_changed_during_index",
                    f"Indexed source changed during snapshot construction: {rel}",
                )
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                self.skipped_non_utf8_files += 1
                self.evidence_index_status = "incomplete"
                continue
            self.contents[rel] = text
            self.file_hashes[rel] = expected_hash
            self.file_sizes[rel] = len(data)

    def _add_node(self, node_id: str, entity_type: str, attributes: dict[str, Any]) -> None:
        if self.graph.has_node(node_id):
            existing = self.graph.get_node(node_id)
            if existing is not None and existing.entity_type != entity_type:
                raise EvidenceToolError("graph_identity_collision", f"Conflicting graph node identity: {node_id}")
            return
        node = SemanticNode(node_id=node_id, entity_type=entity_type, attributes=dict(attributes))
        self.graph.add_node(node)
        self.node_metadata[node_id] = {"node_id": node_id, "entity_type": entity_type, **dict(attributes)}

    def _add_edge(self, source: str, target: str, relation: str, metadata: dict[str, Any] | None = None) -> None:
        if not self.graph.has_node(source) or not self.graph.has_node(target):
            return
        payload = {"source": source, "target": target, "relation": relation, "metadata": dict(metadata or {})}
        key = _canonical_json(payload)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.graph.add_edge(SemanticEdge(
            source_id=source,
            target_id=target,
            relation_type=relation,
            metadata=dict(metadata or {}),
        ))

    def _ensure_module_node(self, module: str) -> str:
        node_id = f"module:{module}"
        if not self.graph.has_node(node_id):
            paths = sorted(self.module_paths.get(module, []))
            self._add_node(node_id, "PythonModule", {"module": module, "paths": paths})
            self.module_nodes[module] = node_id
        return node_id


    def _collect_import_bindings(
        self,
        path: str,
        tree: ast.AST,
    ) -> dict[str, dict[str, Any]]:
        """Collect conservative import bindings used by static call resolution."""
        line_targets: dict[int, list[str]] = defaultdict(list)
        for edge in self.report.get("python_import_edges", []):
            if edge.get("path") != path:
                continue
            target = str(edge.get("target", "")).strip()
            line = edge.get("line")
            if target and isinstance(line, int) and target not in line_targets[line]:
                line_targets[line].append(target)

        bindings: dict[str, dict[str, Any]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".", 1)[0]
                    bindings[local] = {
                        "kind": "module",
                        "module": alias.name,
                        "import_line": node.lineno,
                    }
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.module is None:
                    # ``from . import x`` is resolved conservatively only when
                    # AE-32A supplied an unambiguous target for the line.
                    targets = line_targets.get(node.lineno, [])
                else:
                    targets = line_targets.get(node.lineno, [])
                if len(targets) != 1:
                    continue
                target_module = targets[0]
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    symbol_qualified = f"symbol:{target_module}::{alias.name}"
                    if len(self.symbols_by_legacy_id.get(symbol_qualified, [])) == 1:
                        bindings[local] = {
                            "kind": "symbol",
                            "module": target_module,
                            "name": alias.name,
                            "import_line": node.lineno,
                        }
                    elif f"{target_module}.{alias.name}" in self.module_nodes:
                        bindings[local] = {
                            "kind": "module",
                            "module": f"{target_module}.{alias.name}",
                            "import_line": node.lineno,
                        }
                    else:
                        # Keep unresolved internal imports out of the call
                        # graph rather than turning a textual import into a
                        # confirmed callable relationship.
                        continue
        return bindings

    def _build_static_call_graph(self) -> None:
        """Add source-grounded CALLS edges for unambiguous AST call sites."""
        symbol_nodes: dict[tuple[str, str], list[str]] = defaultdict(list)
        for symbol in self.symbols:
            symbol_nodes[(symbol["module"], symbol["qualified_name"])].append(symbol["node_id"])

        total_candidates = 0
        resolved = 0
        unresolved = 0
        ambiguous = 0
        for rel in sorted(self.contents):
            if PurePosixPath(rel).suffix.lower() != ".py":
                continue
            module = _module_name(rel, self.python_source_roots)
            if not module:
                continue
            try:
                tree = ast.parse(self.contents[rel], filename=rel)
            except (SyntaxError, ValueError):
                continue
            bindings = self._collect_import_bindings(rel, tree)
            visitor = _CallGraphVisitor(
                module=module,
                path=rel,
                source_sha256=self.file_hashes[rel],
                symbol_nodes=symbol_nodes,
                module_nodes=self.module_nodes,
                import_bindings=bindings,
            )
            visitor.visit(tree)
            total_candidates += visitor.call_sites
            resolved += len(visitor.edges)
            unresolved += max(0, visitor.call_sites - len(visitor.edges))
            ambiguous += visitor.ambiguous_calls
            for edge in visitor.edges:
                self._add_edge(
                    edge["source"],
                    edge["target"],
                    "CALLS",
                    {
                        "path": rel,
                        "line": edge.get("line"),
                        "source_sha256": self.file_hashes[rel],
                        "observed_by": "python_ast_call_resolution",
                        "resolution_kind": edge.get("resolution_kind"),
                        "resolution_status": "statically_resolved",
                    },
                )
        self.call_graph_stats = {
            "candidate_call_sites": total_candidates,
            "resolved_call_edges": resolved,
            "unresolved_call_sites": unresolved,
            "ambiguous_call_sites": ambiguous,
            "resolution_policy": "conservative_ast_v1",
            "runtime_execution": False,
        }

    def _build_graph(self) -> None:
        # File nodes are derived only from the hashed, included, UTF-8 source set.
        for rel in sorted(self.contents):
            lines = _source_lines(self.contents[rel])
            node_id = f"file:{rel}"
            kind = _file_kind(rel)
            self.file_nodes[rel] = node_id
            self._add_node(node_id, kind, {
                "path": rel,
                "sha256": self.file_hashes[rel],
                "size_bytes": self.file_sizes[rel],
                "line_count": len(lines),
                "suffix": PurePosixPath(rel).suffix.lower(),
            })

        for rel in sorted(self.contents):
            if PurePosixPath(rel).suffix.lower() != ".py":
                continue
            module = _module_name(rel, self.python_source_roots)
            if not module:
                continue
            existing_paths = self.module_paths[module]
            if existing_paths and rel not in existing_paths:
                collision_paths = sorted({*existing_paths, rel})
                issue = {"module": module, "paths": collision_paths, "kind": "ambiguous_physical_module_sources"}
                if issue not in self.module_identity_issues:
                    self.module_identity_issues.append(issue)
            self.module_paths[module].append(rel)
            module_id = self._ensure_module_node(module)
            self._add_edge(self.file_nodes[rel], module_id, "IMPLEMENTS", {
                "path": rel, "source_sha256": self.file_hashes[rel],
            })
            self._add_edge(module_id, self.file_nodes[rel], "IMPLEMENTED_BY", {
                "path": rel, "source_sha256": self.file_hashes[rel],
            })
            try:
                tree = ast.parse(self.contents[rel], filename=rel)
            except (SyntaxError, ValueError):
                continue
            visitor = _SymbolVisitor(module, rel, self.file_hashes[rel])
            visitor.visit(tree)
            for symbol in visitor.symbols:
                symbol_node = symbol["node_id"]
                self._add_node(symbol_node, "PythonSymbol", {
                    "name": symbol["name"],
                    "qualified_name": symbol["qualified_name"],
                    "module": module,
                    "path": rel,
                    "line": symbol["line"],
                    "kind": symbol["kind"],
                    "source_sha256": self.file_hashes[rel],
                    "symbol_id": symbol.get("symbol_id"),
                    "occurrence_id": symbol.get("occurrence_id", symbol_node),
                })
                self._add_edge(self.file_nodes[rel], symbol_node, "DEFINES", {
                    "path": rel, "line": symbol["line"], "kind": symbol["kind"],
                    "source_sha256": self.file_hashes[rel],
                })
                self._add_edge(symbol_node, module_id, "MEMBER_OF", {
                    "path": rel, "line": symbol["line"], "source_sha256": self.file_hashes[rel],
                })
                self.symbols.append(symbol)
                self.symbols_by_id[symbol_node] = symbol
                self.symbols_by_legacy_id[symbol["symbol_id"]].append(symbol)

        # Model the conventional ``python -m package`` entrypoint explicitly.
        # This is a static package-layout observation, not proof of runtime execution.
        for module in sorted(self.module_paths):
            if not module.endswith(".__main__"):
                continue
            package = module[: -len(".__main__")]
            package_id = self.module_nodes.get(package)
            entrypoint_id = self.module_nodes.get(module)
            if package_id and entrypoint_id:
                self._add_edge(package_id, entrypoint_id, "PACKAGE_ENTRYPOINT", {
                    "observed_by": "python_package_entrypoint_convention",
                    "package_module": package,
                    "entrypoint_module": module,
                })

        # Use AE-32A's AST-derived internal import edges as source-grounded graph facts.
        for edge in self.report.get("python_import_edges", []):
            path = edge.get("path", "")
            if path not in self.contents:
                continue
            source_module = str(edge.get("source", ""))
            target_module = str(edge.get("target", ""))
            if not source_module or not target_module:
                continue
            source_id = self._ensure_module_node(source_module)
            target_id = self._ensure_module_node(target_module)
            metadata = {
                "path": path,
                "line": edge.get("line"),
                "binding": edge.get("binding"),
                "import_kind": edge.get("import_kind"),
                "execution_context": edge.get("execution_context", "unknown"),
                "observed_by": "python_ast_import",
                "source_sha256": self.file_hashes.get(path),
            }
            self._add_edge(source_id, target_id, "IMPORTS", metadata)
            if self._is_test_path(path) and edge.get("execution_context") != "type_checking_only":
                self._add_edge(self.file_nodes[path], target_id, "TESTS", metadata)

        # Workflow invocation edges are static command observations, never execution proof.
        for edge in self.report.get("workflow_edges", []):
            source_path = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if source_path not in self.file_nodes:
                continue
            target_id: str | None = None
            if target in self.file_nodes:
                target_id = self.file_nodes[target]
            elif target in self.module_paths or target in self.module_nodes:
                target_id = self._ensure_module_node(target)
            elif target.endswith(".py") and target in self.contents:
                target_id = self.file_nodes[target]
            if target_id:
                invocation_metadata = {
                    "path": source_path,
                    "line": edge.get("line"),
                    "workflow_edge_kind": edge.get("kind"),
                    "observed_by": "workflow_command_static_scan",
                    "source_sha256": self.file_hashes.get(source_path),
                    "evidence_status": edge.get("evidence_status", "static_command_candidate"),
                    "working_directory": edge.get("working_directory", "."),
                }
                self._add_edge(self.file_nodes[source_path], target_id, "INVOKES", invocation_metadata)
                # Keep the direct file invocation and add a normalized module
                # entrypoint edge when the script maps unambiguously to a module.
                if edge.get("kind") == "workflow_invokes_script" and target in self.file_nodes:
                    target_module = _module_name(target, self.python_source_roots)
                    if target_module and target_module in self.module_nodes:
                        normalized_metadata = dict(invocation_metadata)
                        normalized_metadata.update({
                            "observed_by": "workflow_script_module_normalization",
                            "normalized_script_path": target,
                            "normalization_status": "static_path_to_module",
                        })
                        self._add_edge(
                            self.file_nodes[source_path], self.module_nodes[target_module],
                            "INVOKES", normalized_metadata,
                        )

        # Carry structured decision/action/outcome/rule/link records into the graph.
        # YAML is parsed with safe_load; records remain retrieval context, not authority.
        self._build_decision_memory_graph()

        # Carry AE-32A's static findings into the graph so later investigations can
        # query a finding and traverse to its exact source evidence.
        for finding in self.report.get("findings", []):
            finding_id = str(finding.get("id", "")).strip()
            if not finding_id:
                continue
            node_id = f"finding:{finding_id}"
            self._add_node(node_id, "StaticAuditFinding", {
                "finding_id": finding_id,
                "title": str(finding.get("title", ""))[:240],
                "severity": str(finding.get("severity", "unknown")),
                "statement": str(finding.get("statement", ""))[:1000],
                "limitation": str(finding.get("limitation", ""))[:600],
            })
            for evidence in finding.get("evidence", []):
                path = evidence.get("path")
                if path not in self.file_nodes:
                    continue
                self._add_edge(node_id, self.file_nodes[path], "SUPPORTED_BY", {
                    "path": path,
                    "line": evidence.get("line"),
                    "kind": evidence.get("kind"),
                    "detail": str(evidence.get("detail", ""))[:400],
                    "source_sha256": self.file_hashes.get(path),
                    "observed_by": "ae32a_static_finding",
                })

        # Add conservative function/class invocation relationships only after all symbols exist.
        self._build_static_call_graph()

        # Refresh package/module path metadata after every implementation path is known.
        for module, paths in self.module_paths.items():
            node_id = self.module_nodes.get(module)
            if node_id and self.graph.get_node(node_id) is not None:
                normalized_paths = sorted(paths)
                identity_status = "ambiguous_physical_sources" if len(normalized_paths) > 1 else "unique_physical_source"
                self.graph.get_node(node_id).attributes["paths"] = normalized_paths
                self.graph.get_node(node_id).attributes["identity_status"] = identity_status
                self.node_metadata[node_id]["paths"] = normalized_paths
                self.node_metadata[node_id]["identity_status"] = identity_status
        self.symbols.sort(key=lambda item: (item["path"], item["line"], item["qualified_name"]))

    def _build_decision_memory_graph(self) -> None:
        record_dirs = {
            "decisions": "decision",
            "outcomes": "outcome",
            "actions": "action",
            "rules": "rule",
            "links": "link",
        }
        records: list[dict[str, Any]] = []
        record_nodes: dict[tuple[str, str], str] = {}
        for path in sorted(self.contents):
            if not path.startswith("decision_memory/"):
                continue
            parts = PurePosixPath(path).parts
            if len(parts) < 3 or parts[1] not in record_dirs or PurePosixPath(path).suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            record_type = record_dirs[parts[1]]
            text = self.contents[path]
            try:
                raw_payload = json.loads(text) if path.lower().endswith(".json") else yaml.safe_load(text)
            except (json.JSONDecodeError, yaml.YAMLError, RecursionError):
                self._record_structured_issue(path, "invalid_structured_record")
                continue
            if not isinstance(raw_payload, Mapping):
                self._record_structured_issue(path, "record_not_mapping")
                continue
            normalization_issues: list[str] = []
            try:
                payload = _normalize_record_value(raw_payload, issue_codes=normalization_issues)
            except _StructuredRecordError as exc:
                self._record_structured_issue(path, exc.code)
                continue
            for issue_code in sorted(set(normalization_issues)):
                self._record_structured_issue(path, issue_code)
            if not isinstance(payload, dict):
                self._record_structured_issue(path, "record_not_mapping")
                continue
            record_id = payload.get("id")
            if not isinstance(record_id, str) or not record_id.strip():
                self._record_structured_issue(path, "missing_record_id")
                continue
            record_id = record_id.strip()
            if len(record_id) > 240:
                self._record_structured_issue(path, "record_id_too_long")
                continue
            record_key = (record_type, record_id)
            if record_key in record_nodes:
                # Do not silently merge two physical records into one graph node.
                self._record_structured_issue(path, "duplicate_record_identity")
                continue
            node_id = f"decision_record:{record_type}:{record_id}"
            title = ""
            summary = ""
            if record_type == "decision":
                nested = payload.get("decision") if isinstance(payload.get("decision"), Mapping) else {}
                context = payload.get("context") if isinstance(payload.get("context"), Mapping) else {}
                title = str(nested.get("title", ""))
                summary = str(nested.get("statement", context.get("problem", "")))
            elif record_type == "action":
                nested = payload.get("action") if isinstance(payload.get("action"), Mapping) else {}
                title = str(nested.get("type", "action"))
                summary = str(nested.get("description", ""))
            elif record_type == "outcome":
                nested = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
                title = str(nested.get("status", "outcome"))
                summary = str(nested.get("summary", ""))
            elif record_type == "rule":
                title = str(payload.get("status", "rule"))
                summary = str(payload.get("statement", ""))
            else:
                nested = payload.get("relationship") if isinstance(payload.get("relationship"), Mapping) else {}
                title = str(nested.get("type", "link"))
                summary = str(nested.get("explanation", ""))

            status_value = payload.get("status")
            if status_value is None and isinstance(payload.get("result"), Mapping):
                status_value = payload["result"].get("status")
            review = payload.get("review") if isinstance(payload.get("review"), Mapping) else {}

            def safe_review_field(field: str) -> Any:
                value = review.get(field)
                if value is None or isinstance(value, (str, bool, int, float)):
                    return _sanitize_output_value(value, field_name=field)
                self._record_structured_issue(path, f"non_scalar_review_{field}")
                return "<invalid-structured-field>"

            if status_value is None or isinstance(status_value, (str, bool, int, float)):
                safe_status = _sanitize_output_value(status_value, field_name="status")
            else:
                self._record_structured_issue(path, "non_scalar_status")
                safe_status = "<invalid-structured-field>"

            attributes = {
                "record_id": record_id,
                "record_type": record_type,
                "path": path,
                "title": _redact_then_truncate(title, 240),
                "summary": _redact_then_truncate(summary, 800),
                "status": safe_status,
                "human_review_required": safe_review_field("human_review_required"),
                "approved": safe_review_field("approved"),
                "source_sha256": self.file_hashes[path],
            }
            self._add_node(node_id, "DecisionMemoryRecord", attributes)
            self._add_edge(self.file_nodes[path], node_id, "CONTAINS_RECORD", {
                "path": path, "line": 1, "source_sha256": self.file_hashes[path],
                "observed_by": "safe_structured_record_parse",
            })
            record_nodes[record_key] = node_id
            records.append({"record_type": record_type, "record_id": record_id, "node_id": node_id,
                            "path": path, "payload": payload, "text": text})

        def as_ids(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return [item for item in value if isinstance(item, str)]
            return []

        for record in records:
            record_type = record["record_type"]
            payload = record["payload"]
            source_id = record["node_id"]
            path = record["path"]
            text = record["text"]
            refs: list[tuple[str, str, str]] = []
            if record_type == "action":
                triggered_by = payload.get("triggered_by") if isinstance(payload.get("triggered_by"), Mapping) else {}
                refs.extend(("decision", value, "REFERENCES_DECISION") for value in as_ids(triggered_by.get("decision")))
                refs.extend(("decision", value, "REFERENCES_DECISION") for value in as_ids(payload.get("decision_refs")))
            elif record_type == "outcome":
                refs.extend(("action", value, "OUTCOME_FOR_ACTION") for value in as_ids(payload.get("action_id")))
            elif record_type == "rule":
                sources = payload.get("sources") if isinstance(payload.get("sources"), Mapping) else {}
                refs.extend(("decision", value, "DERIVED_FROM_DECISION") for value in as_ids(sources.get("decision_ids")))
                refs.extend(("action", value, "DERIVED_FROM_ACTION") for value in as_ids(sources.get("action_ids")))
                refs.extend(("outcome", value, "DERIVED_FROM_OUTCOME") for value in as_ids(sources.get("outcome_ids")))
            elif record_type == "link":
                refs.extend(("decision", value, "LINKS_DECISION") for value in as_ids(payload.get("decision_id")))
            for target_type, reference_id, relation in refs:
                target_id = record_nodes.get((target_type, reference_id))
                if not target_id:
                    continue
                line_number = next((index for index, line in enumerate(_source_lines(text), start=1)
                                    if reference_id in line), None)
                self._add_edge(source_id, target_id, relation, {
                    "path": path, "line": line_number, "reference_id": reference_id,
                    "source_sha256": self.file_hashes[path],
                    "observed_by": "safe_structured_record_reference",
                })

    @staticmethod
    def _is_test_path(path: str) -> bool:
        name = PurePosixPath(path).name.lower()
        return path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py")

    def _graph_fingerprint(self) -> str:
        # Use the existing canonical graph fingerprint implementation.
        from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
        return graph_fingerprint(self.graph)

    def _provenance(self) -> dict[str, Any]:
        return {
            "source_revision": self.source_revision,
            "source_revision_status": "caller_asserted_not_git_verified" if self.source_revision else "not_provided",
            "runner_revision": self.runner_revision,
            "runner_revision_status": "caller_asserted_not_git_verified" if self.runner_revision else "not_provided",
            "source_manifest_sha256": self.manifest_sha256,
            "graph_fingerprint": self.graph_fingerprint,
            "graph_projection_version": GRAPH_PROJECTION_VERSION,
            "source_snapshot_status": self.report.get("audit", {}).get("status", "unknown"),
            "evidence_index_status": self.evidence_index_status,
            "skipped_non_utf8_file_count": self.skipped_non_utf8_files,
            "structured_record_issue_count": self.structured_record_issue_count,
            "module_identity_issue_count": len(self.module_identity_issues),
        }

    def _envelope(self, tool: str, status: str, result: dict[str, Any] | None = None,
                  error: dict[str, str] | None = None) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "tool": tool,
            "status": status,
            "provenance": self._provenance(),
        }
        if result is not None:
            value["result"] = result
        if error is not None:
            value["error"] = error
        return value

    def _finalize_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Detach and sanitize all output before it crosses the evidence boundary."""
        safe = _sanitize_output_value(response)
        try:
            encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            safe = {
                "schema_version": SCHEMA_VERSION,
                "tool": str(response.get("tool", "unknown"))[:100],
                "status": "error",
                "provenance": _sanitize_output_value(self._provenance()),
                "error": {"code": "response_not_json_compatible", "message": "Tool output failed strict JSON validation"},
            }
            encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_TOOL_RESPONSE_BYTES:
            safe = {
                "schema_version": SCHEMA_VERSION,
                "tool": str(response.get("tool", "unknown"))[:100],
                "status": "error",
                "provenance": _sanitize_output_value(self._provenance()),
                "error": {
                    "code": "tool_response_too_large",
                    "message": "Tool output exceeded the safe response-size limit; no partial result was returned",
                },
            }
        return safe

    def invoke(self, tool_name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Invoke an approved tool and return detached, redacted strict JSON data."""
        if not isinstance(tool_name, str) or tool_name not in self._handlers:
            response = self._envelope(str(tool_name)[:100], "error", error={
                "code": "unknown_tool", "message": "Tool name is not in the approved AE-32B registry",
            })
            return self._finalize_response(response)
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            response = self._envelope(tool_name, "error", error={
                "code": "invalid_arguments", "message": "Tool arguments must be a JSON object",
            })
            return self._finalize_response(response)
        try:
            result = self._handlers[tool_name](dict(arguments))
            response = self._envelope(tool_name, "ok", result=result)
        except EvidenceToolError as exc:
            response = self._envelope(tool_name, "error", error={"code": exc.code, "message": str(exc)})
        except (TypeError, ValueError, KeyError) as exc:
            # Argument failures are concise; the finalizer redacts their text.
            response = self._envelope(tool_name, "error", error={
                "code": "invalid_arguments", "message": str(exc)[:240] or "Invalid tool arguments",
            })
        except Exception:
            # Never expose stack traces or arbitrary exception payloads to a model.
            response = self._envelope(tool_name, "error", error={
                "code": "tool_internal_error", "message": "Evidence tool failed safely; inspect runner logs",
            })
        return self._finalize_response(response)

    @staticmethod
    def _check_keys(args: dict[str, Any], allowed: set[str], required: set[str] = frozenset()) -> None:
        unknown = set(args) - allowed
        missing = required - set(args)
        if unknown:
            raise EvidenceToolError("unknown_argument", "Unsupported argument(s): " + ", ".join(sorted(unknown)))
        if missing:
            raise EvidenceToolError("missing_argument", "Required argument(s) missing: " + ", ".join(sorted(missing)))

    @staticmethod
    def _string(args: dict[str, Any], key: str, *, required: bool = True, maximum: int = MAX_QUERY_CHARS) -> str:
        value = args.get(key)
        if value is None and not required:
            return ""
        if not isinstance(value, str) or not value.strip():
            raise EvidenceToolError("invalid_argument", f"{key} must be a non-empty string")
        value = value.strip()
        if len(value) > maximum:
            raise EvidenceToolError("argument_too_long", f"{key} exceeds the maximum length of {maximum}")
        return value

    @staticmethod
    def _bounded_int(args: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
        value = args.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise EvidenceToolError("invalid_argument", f"{key} must be an integer")
        if value < minimum or value > maximum:
            raise EvidenceToolError("argument_out_of_range", f"{key} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _relation_types(args: dict[str, Any]) -> list[str] | None:
        if "relation_types" not in args:
            return None
        value = args["relation_types"]
        if not isinstance(value, list) or len(value) > 12 or any(not isinstance(item, str) or not item.strip() for item in value):
            raise EvidenceToolError("invalid_argument", "relation_types must be a list of at most 12 non-empty strings")
        return sorted(set(item.strip() for item in value))

    def graph_runtime_report(self) -> dict[str, Any]:
        """Return the actual query backend and its observed execution counters."""
        engine = self.graph_service.engine.traversal_engine
        runtime = engine.runtime_report()
        active_backend = runtime.get("active_computation_backend")
        backend_is_external = active_backend not in (None, "reference", "python_reference_traversal")
        runtime.update({
            "context_backend_bypasses": dict(sorted(self._context_backend_bypasses.items())),
            "context_backend_bypass_count": sum(self._context_backend_bypasses.values()),
            "context_operation_telemetry": {
                key: dict(value)
                for key, value in sorted(self._context_operation_telemetry.items())
            },
            "canonical_model": "SemanticGraph",
            "query_service": "SemanticGraphAnalysisService",
            "backend_pipeline_wired_into_ae32b_query_path": backend_is_external,
            "external_backend_adapters_active": [active_backend] if backend_is_external else [],
            "repository_code_executed": False,
            "network_calls_performed": False,
            "source_files_modified": False,
        })
        return runtime

    def close(self) -> None:
        """Release resources owned by the selected graph backend.

        Most in-process backends require no explicit teardown. Isolated worker
        adapters (such as SNAP) own subprocess/container resources and must be
        closed explicitly by long-lived repository tools and conformance
        runners rather than relying on interpreter-shutdown finalizers.
        """
        engine = self.graph_service.engine.traversal_engine
        adapter = getattr(engine, "adapter", None)
        close = getattr(adapter, "close", None)
        if callable(close):
            close()

    def _context_edges(
        self,
        node_id: str,
        *,
        direction: str,
        relation_types: set[str],
        operation: str,
    ) -> list[SemanticEdge]:
        """Read one node's context adjacency through the backend-neutral query service.

        Context tools retain their domain-specific BFS, filtering and evidence
        formatting. This method delegates each local adjacency request to a
        one-hop GraphQuery, so the selected traversal backend—not a private
        backend hook or a canonical-edge fallback—serves the request.
        """
        if direction not in {"outgoing", "incoming"}:
            raise EvidenceToolError("unsupported_context_direction", "Unsupported context adjacency direction")
        if not isinstance(operation, str) or not operation.strip():
            raise EvidenceToolError("invalid_context_operation", "Context operation name must be non-empty")

        counters = self._context_operation_telemetry.setdefault(
            operation,
            {
                "adjacency_queries_attempted": 0,
                "adjacency_queries_succeeded": 0,
                "adjacency_queries_failed": 0,
                "native_adjacency_lookups": 0,
                "native_edge_occurrences_read": 0,
                "parity_verified": 0,
                "parity_failures": 0,
            },
        )
        counters["adjacency_queries_attempted"] += 1
        query_payload = {
            "node": node_id,
            "direction": direction,
            "relation_types": sorted(relation_types),
            "max_depth": 1,
            "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
            "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS,
            "operation": operation,
            "graph_fingerprint": self.graph_fingerprint,
        }
        query = GraphQuery(
            query_id=self._query_id("context-adjacency", query_payload),
            query_type=QueryType.DEPENDENCY,
            source_entities=[node_id],
            constraints={
                "direction": direction,
                "relation_types": sorted(relation_types),
                "max_depth": 1,
                "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
                "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS,
            },
        )
        try:
            result = self.graph_service.analyze(query)
            if bool(result.metadata.get("truncated", False)):
                raise EvidenceToolError(
                    "context_adjacency_incomplete",
                    "The selected graph backend could not return complete local context adjacency within its bounds",
                )
            backend_metrics = result.metadata.get("backend_native_query_metrics", {})
            if isinstance(backend_metrics, Mapping):
                for key in ("native_adjacency_lookups", "native_edge_occurrences_read"):
                    value = backend_metrics.get(key, 0)
                    if isinstance(value, int) and not isinstance(value, bool):
                        counters[key] += value
            if result.metadata.get("backend_parity_status") == "verified_against_reference_per_query":
                counters["parity_verified"] += 1

            edges: list[SemanticEdge] = []
            for evidence in result.evidence:
                provenance = evidence.provenance if isinstance(evidence.provenance, Mapping) else {}
                attributes = provenance.get("edge_attributes", {})
                metadata = provenance.get("edge_metadata", {})
                edges.append(SemanticEdge(
                    source_id=evidence.subject_id,
                    target_id=evidence.object_id,
                    relation_type=evidence.predicate,
                    attributes=dict(attributes) if isinstance(attributes, Mapping) else {},
                    metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
                ))
            counters["adjacency_queries_succeeded"] += 1
            return edges
        except Exception as exc:
            counters["adjacency_queries_failed"] += 1
            if "parity" in str(exc).lower():
                counters["parity_failures"] += 1
            raise

    def _repository_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(args, set())
        relations = Counter(edge.relation_type for edge in self.graph.edges)
        summary = {
            "audit_status": self.report.get("audit", {}).get("status", "unknown"),
            "indexed_file_count": len(self.contents),
            "manifest_included_file_count": len(self.manifest_rows),
            "skipped_sensitive_file_count": self.skipped_sensitive_files,
            "skipped_non_utf8_file_count": self.skipped_non_utf8_files,
            "evidence_index_status": self.evidence_index_status,
            "structured_record_issue_count": self.structured_record_issue_count,
            "structured_record_issues": list(self.structured_record_issues[:50]),
            "module_identity_issue_count": len(self.module_identity_issues),
            "module_identity_issues": list(self.module_identity_issues[:50]),
            "python_source_roots": list(self.python_source_roots),
            "python_parse_issue_count": len(self.report.get("python_parse_issues", [])),
            "scope_issue_count": len(self.report.get("scope_issues", [])),
            "graph_node_count": len(self.graph.nodes),
            "graph_edge_count": len(self.graph.edges),
            "graph_relation_counts": dict(sorted(relations.items())),
            "graph_fingerprint": self.graph_fingerprint,
            "graph_projection_version": GRAPH_PROJECTION_VERSION,
            "graph_runtime": self.graph_runtime_report(),
            "symbol_count": len(self.symbols),
            "call_graph": dict(self.call_graph_stats),
            "workflow_count": self.report.get("audit", {}).get("workflow_count", 0),
            "static_finding_count": len(self.report.get("findings", [])),
            "read_only": True,
            "repository_code_executed": False,
            "network_calls_performed": False,
            "source_files_modified": False,
        }
        return summary

    def _search_repository(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(args, {"query", "mode", "max_results"}, {"query"})
        query = self._string(args, "query")
        mode = args.get("mode", "both")
        if mode not in {"both", "content", "path"}:
            raise EvidenceToolError("invalid_argument", "mode must be both, content, or path")
        max_results = self._bounded_int(args, "max_results", 10, 1, MAX_SEARCH_RESULTS)
        needle = query.casefold()
        matches: list[dict[str, Any]] = []
        for path in sorted(self.contents):
            if mode in {"both", "path"} and needle in path.casefold():
                matches.append({
                    "path": path, "line": None, "match_kind": "path",
                    "snippet": path, "source_sha256": self.file_hashes[path],
                })
                if len(matches) > max_results:
                    break
            if mode == "path":
                continue
            for line_number, line in enumerate(_source_lines(self.contents[path]), start=1):
                if needle not in line.casefold():
                    continue
                matches.append({
                    "path": path,
                    "line": line_number,
                    "match_kind": "content",
                    "snippet": _redact_then_truncate(line, MAX_SNIPPET_CHARS),
                    "source_sha256": self.file_hashes[path],
                })
                if len(matches) > max_results:
                    break
            if len(matches) > max_results:
                break
        truncated = len(matches) > max_results
        return {"query": _redact_text(query), "mode": mode, "matches": matches[:max_results], "truncated": truncated}

    def _read_source_file(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(args, {"path", "start_line", "end_line"}, {"path"})
        path = _safe_relative_path(self._string(args, "path", maximum=400))
        if path not in self.contents:
            raise EvidenceToolError("file_not_indexed", "File is not in the current safe source snapshot")
        lines = _source_lines(self.contents[path])
        if not lines:
            if "start_line" in args and (
                isinstance(args["start_line"], bool)
                or not isinstance(args["start_line"], int)
                or args["start_line"] != 1
            ):
                raise EvidenceToolError("argument_out_of_range", "An empty file only supports start_line=1")
            requested_end = args.get("end_line", 1)
            if isinstance(requested_end, bool) or not isinstance(requested_end, int):
                raise EvidenceToolError("invalid_argument", "end_line must be an integer")
            if requested_end < 1:
                raise EvidenceToolError("argument_out_of_range", "end_line must be at least 1")
            return {
                "path": path, "source_sha256": self.file_hashes[path], "total_lines": 0,
                "requested_start_line": 1, "requested_end_line": requested_end,
                "start_line": 1, "end_line": 0, "content": "",
                "truncated": requested_end > 1, "redaction_applied": True,
                "end_clamped_to_eof": requested_end > 0,
                "content_omitted": False, "source_range_complete": True,
                "omitted_line_count": 0, "read_coverage": "empty_file",
            }
        # Starting positions must identify a real line. An end position may
        # legitimately overshoot EOF: clamp it to the indexed source length,
        # while retaining both the requested and effective range in evidence.
        start = self._bounded_int(args, "start_line", 1, 1, len(lines))
        default_end = min(len(lines), start + MAX_READ_LINES - 1)
        requested_end = args.get("end_line", default_end)
        if isinstance(requested_end, bool) or not isinstance(requested_end, int):
            raise EvidenceToolError("invalid_argument", "end_line must be an integer")
        if requested_end < start:
            raise EvidenceToolError("argument_out_of_range", "end_line must be greater than or equal to start_line")
        effective_requested_end = min(requested_end, len(lines))
        end = min(effective_requested_end, start + MAX_READ_LINES - 1)
        rendered = []
        char_count = 0
        truncated = requested_end > len(lines) or end < effective_requested_end
        for line_no in range(start, end + 1):
            rendered_line = f"{line_no}: {_redact_text(lines[line_no - 1])}"
            if char_count + len(rendered_line) + 1 > MAX_READ_CHARS:
                truncated = True
                break
            rendered.append(rendered_line)
            char_count += len(rendered_line) + 1
        last_returned = start + len(rendered) - 1
        # Legacy `truncated` also describes an overshooting *request*, not only
        # omitted source. New fields disambiguate this without breaking callers.
        omitted_lines = (start - 1) + max(0, len(lines) - last_returned)
        range_complete = start == 1 and last_returned == len(lines)
        return {
            "path": path,
            "source_sha256": self.file_hashes[path],
            "total_lines": len(lines),
            "requested_start_line": start,
            "requested_end_line": requested_end,
            "start_line": start,
            "end_line": last_returned,
            "content": "\n".join(rendered),
            "truncated": bool(truncated or last_returned < end),
            "end_clamped_to_eof": requested_end > len(lines),
            "content_omitted": not range_complete,
            "source_range_complete": range_complete,
            "omitted_line_count": omitted_lines,
            "read_coverage": "complete_file" if range_complete else "partial_file",
            "redaction_applied": True,
        }

    def _search_symbols(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(args, {"query", "kind", "max_results"}, {"query"})
        query = self._string(args, "query").casefold()
        kind = args.get("kind", "any")
        if kind not in {"any", "class", "function", "async_function"}:
            raise EvidenceToolError("invalid_argument", "kind must be any, class, function, or async_function")
        max_results = self._bounded_int(args, "max_results", 10, 1, MAX_SEARCH_RESULTS)
        results = []
        for symbol in self.symbols:
            if kind != "any" and symbol["kind"] != kind:
                continue
            if query not in symbol["name"].casefold() and query not in symbol["qualified_name"].casefold():
                continue
            results.append({
                "node_id": symbol["node_id"], "occurrence_id": symbol.get("occurrence_id", symbol["node_id"]),
                "symbol_id": symbol.get("symbol_id"), "name": symbol["name"],
                "qualified_name": symbol["qualified_name"], "kind": symbol["kind"],
                "module": symbol["module"], "path": symbol["path"], "line": symbol["line"],
                "source_sha256": self.file_hashes[symbol["path"]],
            })
            if len(results) > max_results:
                break
        truncated = len(results) > max_results
        return {"query": _redact_text(query), "kind": kind, "symbols": results[:max_results], "truncated": truncated}

    def _resolve_node(self, selector: str) -> str:
        selector = selector.strip()
        if selector in self.node_metadata:
            return selector
        if selector.startswith("symbol:") and selector in self.symbols_by_legacy_id:
            occurrences = self.symbols_by_legacy_id[selector]
            if len(occurrences) == 1:
                return occurrences[0]["node_id"]
            raise EvidenceToolError("ambiguous_symbol_identity", "Symbol name has multiple source occurrences; use a symbol occurrence ID from search_symbols")
        if selector.startswith(("file:", "module:", "symbol:", "finding:")):
            raise EvidenceToolError("graph_node_not_found", "Graph node identifier is not present in this snapshot")
        try:
            path = _safe_relative_path(selector)
        except EvidenceToolError:
            path = ""
        if path and path in self.file_nodes:
            return self.file_nodes[path]
        if selector.startswith("module:") and selector[7:] in self.module_nodes:
            return self.module_nodes[selector[7:]]
        if selector in self.module_nodes:
            return self.module_nodes[selector]
        # Accept a bare Python file stem only when it resolves uniquely.
        candidates = [module for module, paths in self.module_paths.items()
                      if module.rsplit(".", 1)[-1] == selector and paths]
        if len(candidates) == 1:
            return self.module_nodes[candidates[0]]
        raise EvidenceToolError("graph_node_not_found", "Selector did not resolve to a unique indexed file, module, symbol, or finding")

    def _describe_node(self, node_id: str) -> dict[str, Any]:
        data = dict(self.node_metadata.get(node_id, {"node_id": node_id}))
        path = data.get("path")
        if path in self.file_hashes:
            data["source_sha256"] = self.file_hashes[path]
        return data

    @staticmethod
    def _query_id(prefix: str, payload: dict[str, Any]) -> str:
        digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:20]
        return f"ae32b-{prefix}-{digest}"

    def _query_graph(self, query: GraphQuery) -> dict[str, Any]:
        result = self.graph_service.analyze(query).to_dict()
        result["source_nodes"] = [self._describe_node(item) for item in result.get("source_entities", [])]
        result["discovered_nodes"] = [self._describe_node(item) for item in result.get("discovered_entities", [])]
        # Evidence records contain the observed edge and its source-line metadata.
        return result

    @staticmethod
    def _graph_source_paths(result: Mapping[str, Any]) -> list[str]:
        paths: set[str] = set()
        for item in list(result.get("source_nodes", [])) + list(result.get("discovered_nodes", [])):
            if isinstance(item, Mapping) and isinstance(item.get("path"), str) and item.get("path"):
                paths.add(item["path"])
        for evidence in result.get("evidence", []):
            if not isinstance(evidence, Mapping):
                continue
            provenance = evidence.get("provenance", {})
            if not isinstance(provenance, Mapping):
                continue
            metadata = provenance.get("edge_metadata", {})
            if not isinstance(metadata, Mapping):
                continue
            path = metadata.get("path")
            if isinstance(path, str) and path:
                paths.add(path)
        return sorted(paths)

    def _graph_neighbors(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(
            args,
            {"node", "changed_nodes", "direction", "relation_types", "max_depth", "max_results"},
            {"node"},
        )
        direction = args.get("direction", "both")
        if direction in {"dependencies", "dependents"}:
            if "changed_nodes" in args:
                raise EvidenceToolError("invalid_argument", "changed_nodes is supported only when direction=impact")
            forwarded = {
                key: value for key, value in args.items()
                if key in {"node", "relation_types", "max_depth", "max_results"}
            }
            forwarded["direction"] = "outgoing" if direction == "dependencies" else "incoming"
            return self._graph_dependencies(forwarded)
        if direction == "impact":
            forwarded = {
                key: value for key, value in args.items()
                if key in {"node", "changed_nodes", "relation_types", "max_depth", "max_results"}
            }
            return self._graph_impact(forwarded)
        if "changed_nodes" in args:
            raise EvidenceToolError("invalid_argument", "changed_nodes is supported only when direction=impact")
        node = self._resolve_node(self._string(args, "node", maximum=500))
        if direction not in {"outgoing", "incoming", "both"}:
            raise EvidenceToolError("invalid_argument", "direction must be outgoing, incoming, or both")
        depth = self._bounded_int(args, "max_depth", 1, 0, MAX_NEIGHBOR_DEPTH)
        max_results = self._bounded_int(args, "max_results", 20, 1, MAX_GRAPH_RESULTS)
        relations = self._relation_types(args)
        if relations is None:
            relations = sorted({edge.relation_type for edge in self.graph.edges})
        query_payload = {"node": node, "direction": direction, "max_depth": depth,
                         "relation_types": relations, "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
                         "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS}
        query = GraphQuery(
            query_id=self._query_id("neighbors", query_payload),
            query_type=QueryType.DEPENDENCY,
            source_entities=[node],
            constraints={"direction": direction, "max_depth": depth, "relation_types": relations,
                         "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
                         "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS},
        )
        result = self._query_graph(query)
        discovered = result.get("discovered_nodes", [])
        visible_nodes = discovered[:max_results]
        visible_ids = {item["node_id"] for item in visible_nodes}
        result["discovered_nodes"] = visible_nodes
        result_limit_truncated = len(discovered) > max_results
        traversal_truncated = bool(result.get("metadata", {}).get("truncated", False))
        result["result_limit_truncated"] = result_limit_truncated
        result["truncated"] = result_limit_truncated or traversal_truncated
        result["coverage_status"] = "partial" if result["truncated"] else "complete_for_query"
        result["discovered_entities"] = [item["node_id"] for item in visible_nodes]
        visible_observations = [
            item for item in result.get("observations", [])
            if item.get("subject_id") in visible_ids or item.get("object_id") in visible_ids
        ]
        visible_evidence_ids = {evidence_id for item in visible_observations for evidence_id in item.get("evidence_ids", [])}
        result["observations"] = visible_observations
        result["evidence"] = [item for item in result.get("evidence", []) if item.get("evidence_id") in visible_evidence_ids]
        result["observed_relation_types"] = sorted({
            str(item.get("predicate"))
            for item in visible_observations
            if isinstance(item, Mapping) and item.get("predicate")
        })
        result["source_paths"] = self._graph_source_paths(result)
        return result

    def _graph_dependencies(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(
            args,
            {"node", "direction", "relation_types", "max_depth", "max_results"},
            {"node"},
        )
        node = self._resolve_node(self._string(args, "node", maximum=500))
        direction = args.get("direction", "outgoing")
        if direction not in {"outgoing", "incoming", "both"}:
            raise EvidenceToolError("invalid_argument", "direction must be outgoing, incoming, or both")
        depth = self._bounded_int(args, "max_depth", 3, 1, MAX_NEIGHBOR_DEPTH)
        max_results = self._bounded_int(args, "max_results", 30, 1, MAX_GRAPH_RESULTS)
        relations = self._relation_types(args)
        if relations is None:
            relations = ["IMPORTS", "DEPENDS_ON"]
        query_payload = {
            "node": node, "direction": direction, "max_depth": depth,
            "relation_types": relations, "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
            "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS,
        }
        query = GraphQuery(
            query_id=self._query_id("dependencies", query_payload),
            query_type=QueryType.DEPENDENCY,
            source_entities=[node],
            constraints={
                "direction": direction, "max_depth": depth, "relation_types": relations,
                "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
                "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS,
            },
        )
        result = self._query_graph(query)
        discovered = result.get("discovered_nodes", [])
        depth_by_node: dict[str, int] = {}
        for observation in result.get("observations", []):
            metadata = observation.get("metadata", {})
            target = metadata.get("traversed_to") if isinstance(metadata, Mapping) else None
            observed_depth = observation.get("depth")
            if isinstance(target, str) and isinstance(observed_depth, int):
                depth_by_node[target] = min(depth_by_node.get(target, observed_depth), observed_depth)
        visible = discovered[:max_results]
        direct = [item for item in visible if depth_by_node.get(item.get("node_id"), 0) == 1]
        transitive = [item for item in visible if depth_by_node.get(item.get("node_id"), 0) > 1]
        if direction == "outgoing":
            result["direct_dependencies"] = direct
            result["transitive_dependencies"] = transitive
        elif direction == "incoming":
            result["direct_dependents"] = direct
            result["transitive_dependents"] = transitive
        else:
            result["direct_neighbors"] = direct
            result["transitive_neighbors"] = transitive
        visible_ids = {item.get("node_id") for item in visible}
        result["discovered_nodes"] = visible
        result["discovered_entities"] = [item["node_id"] for item in visible if item.get("node_id")]
        result["result_limit_truncated"] = len(discovered) > max_results
        result["truncated"] = bool(result.get("metadata", {}).get("truncated", False)) or result["result_limit_truncated"]
        result["coverage_status"] = "partial" if result["truncated"] else "complete_for_query"
        result["dependency_semantics"] = {
            "outgoing": "dependencies",
            "incoming": "dependents",
            "both": "neighbors",
        }[direction]
        result["dependency_relation_types"] = relations
        result["source_paths"] = self._graph_source_paths(result)
        return result

    def _graph_impact(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(
            args,
            {"node", "changed_nodes", "relation_types", "max_depth", "max_results"},
            {"node"},
        )
        first = self._resolve_node(self._string(args, "node", maximum=500))
        raw_changed = args.get("changed_nodes", [])
        if not isinstance(raw_changed, list) or len(raw_changed) > 24:
            raise EvidenceToolError("invalid_argument", "changed_nodes must be an array of at most 24 additional node selectors")
        resolved_changed = [
            self._resolve_node(self._string({"node": value}, "node", maximum=500))
            for value in raw_changed
        ]
        sources = [first, *resolved_changed]
        if len(set(sources)) != len(sources):
            raise EvidenceToolError("duplicate_change_source", "Change-set node selectors must resolve to unique graph entities")
        sources = sorted(sources)

        depth = self._bounded_int(args, "max_depth", 3, 1, MAX_NEIGHBOR_DEPTH)
        max_results = self._bounded_int(args, "max_results", 30, 1, MAX_GRAPH_RESULTS)
        relations = self._relation_types(args)
        if relations is None:
            relations = ["IMPORTS", "DEPENDS_ON", "CALLS", "INVOKES", "TESTS"]
        query_payload = {
            "changed_sources": sources,
            "max_depth": depth,
            "relation_types": relations,
            "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
            "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS,
        }
        query = GraphQuery(
            query_id=self._query_id("impact-change-set", query_payload),
            query_type=QueryType.IMPACT,
            source_entities=sources,
            constraints={
                "max_depth": depth,
                "relation_types": relations,
                "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
                "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS,
            },
        )
        result = self._query_graph(query)
        metadata = result.get("metadata", {})
        candidates = metadata.get("impact_candidates", []) if isinstance(metadata, Mapping) else []
        if not isinstance(candidates, list):
            raise EvidenceToolError("invalid_graph_result", "Impact candidate payload is invalid")
        node_descriptions = {
            item.get("node_id"): item
            for item in result.get("discovered_nodes", [])
            if isinstance(item, Mapping) and isinstance(item.get("node_id"), str)
        }
        visible_candidates = []
        for candidate in candidates[:max_results]:
            if not isinstance(candidate, Mapping) or not isinstance(candidate.get("node_id"), str):
                continue
            enriched = dict(candidate)
            enriched["node"] = node_descriptions.get(
                candidate["node_id"], self._describe_node(candidate["node_id"])
            )
            visible_candidates.append(enriched)
        visible_ids = {item["node_id"] for item in visible_candidates}
        cycle_reports = metadata.get("dependency_cycles", []) if isinstance(metadata, Mapping) else []
        if not isinstance(cycle_reports, list):
            raise EvidenceToolError("invalid_graph_result", "Dependency-cycle payload is invalid")
        visible_cycles = [
            item for item in cycle_reports[:50]
            if isinstance(item, Mapping)
            and (set(item.get("node_ids", [])) & (visible_ids | set(sources)))
        ]
        candidate_evidence_ids = {
            evidence_id
            for item in visible_candidates
            for evidence_id in item.get("evidence_ids", [])
            if isinstance(evidence_id, str)
        }
        cycle_evidence_ids = {
            evidence_id
            for item in visible_cycles
            for evidence_id in item.get("evidence_ids", [])
            if isinstance(evidence_id, str)
        }
        ownership_evidence_ids = (
            set(metadata.get("ownership_evidence_ids", []))
            if isinstance(metadata, Mapping) else set()
        )
        allowed_evidence_ids = candidate_evidence_ids | cycle_evidence_ids | ownership_evidence_ids
        result["evidence"] = [
            item for item in result.get("evidence", [])
            if item.get("evidence_id") in allowed_evidence_ids
        ]
        result["observations"] = [
            item for item in result.get("observations", [])
            if set(item.get("evidence_ids", [])) & allowed_evidence_ids
        ]
        result["discovered_nodes"] = [
            item for item in result.get("discovered_nodes", [])
            if item.get("node_id") in visible_ids
        ]
        result["discovered_entities"] = [
            item["node_id"] for item in result["discovered_nodes"] if item.get("node_id")
        ]
        result["impact_candidates"] = visible_candidates
        result["dependency_cycles"] = visible_cycles
        visible_risk_indicators = []
        if isinstance(metadata, Mapping):
            for raw_indicator in metadata.get("risk_indicators", []):
                if not isinstance(raw_indicator, Mapping):
                    continue
                indicator = dict(raw_indicator)
                raw_node_ids = indicator.get("node_ids")
                if isinstance(raw_node_ids, list):
                    indicator["node_ids"] = [
                        node_id for node_id in raw_node_ids
                        if node_id in visible_ids or node_id in sources
                    ]
                    if raw_node_ids and not indicator["node_ids"]:
                        continue
                raw_evidence_ids = indicator.get("evidence_ids")
                if isinstance(raw_evidence_ids, list):
                    indicator["evidence_ids"] = [
                        evidence_id for evidence_id in raw_evidence_ids
                        if evidence_id in allowed_evidence_ids
                    ]
                visible_risk_indicators.append(indicator)
        result["risk_indicators"] = visible_risk_indicators
        if isinstance(result.get("metadata"), dict):
            result["metadata"]["impact_candidates"] = visible_candidates
            result["metadata"]["dependency_cycles"] = visible_cycles
            result["metadata"]["risk_indicators"] = result["risk_indicators"]
        result["direct_impact_candidates"] = [
            item for item in visible_candidates
            if min(item.get("impact_depth_by_source", {}).values(), default=item.get("impact_depth", 0)) == 1
        ]
        result["transitive_impact_candidates"] = [
            item for item in visible_candidates
            if min(item.get("impact_depth_by_source", {}).values(), default=item.get("impact_depth", 0)) > 1
        ]
        result["shared_impact_candidates"] = [
            item for item in visible_candidates if item.get("shared_change_impact")
        ]
        result["impacted_tests"] = [
            item for item in visible_candidates if item.get("candidate_kind") == "test"
        ]
        result["impacted_workflows"] = [
            item for item in visible_candidates if item.get("candidate_kind") == "workflow"
        ]
        result["impacted_symbols"] = [
            item for item in visible_candidates if item.get("candidate_kind") == "symbol"
        ]
        result["result_limit_truncated"] = len(candidates) > max_results
        cycle_status = metadata.get("cycle_analysis_status", "unknown") if isinstance(metadata, Mapping) else "unknown"
        result["truncated"] = (
            bool(metadata.get("truncated", False)) if isinstance(metadata, Mapping) else True
        ) or result["result_limit_truncated"] or cycle_status != "complete"
        result["coverage_status"] = "partial" if result["truncated"] else (
            "complete_for_query" if result.get("status") != "incomplete" else "partial"
        )
        result["change_set_summary"] = {
            "changed_sources": sources,
            "changed_source_count": len(sources),
            "unique_impact_count": metadata.get("unique_impact_count", len(candidates)),
            "shared_impact_count": metadata.get("shared_impact_count", 0),
            "source_impact_counts": metadata.get("source_impact_counts", {}),
        }
        result["cycle_analysis_status"] = cycle_status
        result["impact_semantics"] = (
            "Static change-set impact candidates aggregated across the supplied source entities. "
            "Shared candidates identify observed overlap; dependency cycles are strongly connected "
            "components over IMPORTS/DEPENDS_ON in the bounded impacted subgraph. These observations "
            "do not prove runtime execution, failure, severity, missing test coverage, or correctness."
        )
        result["impact_relation_types"] = relations
        result["source_paths"] = self._graph_source_paths(result)
        return result

    def _graph_path(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(args, {"source", "target", "direction", "relation_types", "max_depth"}, {"source", "target"})
        source = self._resolve_node(self._string(args, "source", maximum=500))
        target = self._resolve_node(self._string(args, "target", maximum=500))
        direction = args.get("direction", "both")
        if direction not in {"outgoing", "incoming", "both"}:
            raise EvidenceToolError("invalid_argument", "direction must be outgoing, incoming, or both")
        depth = self._bounded_int(args, "max_depth", 5, 1, MAX_PATH_DEPTH)
        relations = self._relation_types(args)
        if relations is None:
            relations = sorted({edge.relation_type for edge in self.graph.edges})
        query_payload = {"source": source, "target": target, "direction": direction,
                         "max_depth": depth, "relation_types": relations,
                         "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
                         "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS}
        query = GraphQuery(
            query_id=self._query_id("path", query_payload),
            query_type=QueryType.PATH,
            source_entities=[source],
            constraints={"target_entity": target, "direction": direction, "max_depth": depth,
                         "relation_types": relations, "max_visited_nodes": MAX_GRAPH_VISITED_NODES,
                         "max_traversal_steps": MAX_GRAPH_TRAVERSAL_STEPS},
        )
        result = self._query_graph(query)
        path = []
        for observation in result.get("observations", []):
            meta = observation.get("metadata", {})
            path.append({
                "from": meta.get("traversed_from"),
                "to": meta.get("traversed_to"),
                "relation": observation.get("predicate"),
                "subject": observation.get("subject_id"),
                "object": observation.get("object_id"),
                "evidence_ids": observation.get("evidence_ids", []),
                "depth": observation.get("depth"),
            })
        result["path"] = path
        result["path_found"] = result.get("status") == "completed"
        result["search_complete"] = not bool(result.get("metadata", {}).get("truncated", False))
        result["truncated"] = not result["search_complete"]
        result["coverage_status"] = "complete_for_query" if result["search_complete"] else "partial"
        result["observed_relation_types"] = sorted({
            str(item.get("predicate"))
            for item in result.get("observations", [])
            if isinstance(item, Mapping) and item.get("predicate")
        })
        result["source_paths"] = self._graph_source_paths(result)
        return result

    def _pytest_python_file_patterns(self) -> tuple[list[str] | None, str | None, str | None]:
        """Return visible pytest ``python_files`` patterns without importing pytest.

        Multiple active configuration files or malformed configuration are
        treated as unknown. This deliberately prefers a conservative result
        over guessing which config pytest would select for a particular CLI.
        """
        active: list[tuple[str, list[str]]] = []
        for path in ("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg"):
            text = self.contents.get(path)
            if text is None:
                continue
            try:
                if path == "pyproject.toml":
                    document = tomllib.loads(text)
                    section = document.get("tool", {}).get("pytest", {}).get("ini_options", {})
                    if not isinstance(section, Mapping):
                        return None, path, "malformed_pytest_configuration"
                    if "python_files" in section:
                        raw = section.get("python_files")
                        if isinstance(raw, str):
                            patterns = raw.split()
                        elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
                            patterns = [part for item in raw for part in item.split()]
                        else:
                            return None, path, "unsupported_python_files_configuration"
                        if not patterns:
                            return None, path, "empty_python_files_configuration"
                        active.append((path, patterns))
                else:
                    parser = configparser.ConfigParser(interpolation=None, strict=True)
                    parser.read_string(text)
                    section_name = "pytest" if path in {"pytest.ini", "tox.ini"} else "tool:pytest"
                    if parser.has_section(section_name) and parser.has_option(section_name, "python_files"):
                        raw = parser.get(section_name, "python_files", raw=True)
                        patterns = raw.split()
                        if not patterns:
                            return None, path, "empty_python_files_configuration"
                        active.append((path, patterns))
            except (tomllib.TOMLDecodeError, configparser.Error, TypeError, ValueError):
                return None, path, "malformed_pytest_configuration"
        if len(active) > 1:
            return None, ";".join(item[0] for item in active), "multiple_pytest_configurations"
        if active:
            return active[0][1], active[0][0], None
        return ["test_*.py", "*_test.py"], None, None

    def _pytest_static_assessment(self, path: str) -> dict[str, Any]:
        """Classify a Python candidate against visible pytest filename rules only."""
        if PurePosixPath(path).suffix.lower() != ".py":
            return {
                "classification": "not_a_python_test_module",
                "collection_status": "not_applicable",
                "execution_status": "not_executed_static_analysis_only",
                "config_source": None,
                "matched_python_files_pattern": None,
                "test_item_candidate_count": 0,
                "parse_status": "not_applicable",
            }
        patterns, config_source, config_issue = self._pytest_python_file_patterns()
        if patterns is None:
            classification = "unknown"
            collection_status = "unknown"
            matched_pattern = None
        else:
            basename = PurePosixPath(path).name
            matched_pattern = next(
                (pattern for pattern in patterns if fnmatch.fnmatchcase(basename, pattern)),
                None,
            )
            if matched_pattern:
                classification = "pytest_collection_candidate"
                collection_status = "matches_visible_python_files_pattern"
            elif self._is_test_path(path):
                classification = "helper_only_not_default_collected"
                collection_status = "not_collected_by_visible_python_files_pattern"
            else:
                classification = "nonmatching_python_source_candidate"
                collection_status = "not_collected_by_visible_python_files_pattern"
        source = self.contents.get(path, "")
        try:
            tree = ast.parse(source, filename=path)
            item_count = sum(
                1 for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            )
            parse_status = "parsed"
        except (SyntaxError, ValueError):
            item_count = 0
            parse_status = "syntax_error"
        result = {
            "classification": classification,
            "collection_status": collection_status,
            "execution_status": "not_executed_static_analysis_only",
            "config_source": config_source,
            "matched_python_files_pattern": matched_pattern,
            "test_item_candidate_count": item_count,
            "parse_status": parse_status,
        }
        if config_issue:
            result["configuration_issue"] = config_issue
        return result

    def _find_related_tests(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(args, {"target", "max_results"}, {"target"})
        selector = self._string(args, "target", maximum=500)
        max_results = self._bounded_int(args, "max_results", 15, 1, MAX_SEARCH_RESULTS)
        target_id = self._resolve_node(selector)
        candidate_targets = [target_id]
        node = self.graph.get_node(target_id)
        if node is not None and node.entity_type in {"PythonSourceFile", "TestFile"}:
            module = _module_name(str(node.attributes.get("path", "")), self.python_source_roots)
            if module and f"module:{module}" in self.node_metadata:
                candidate_targets.append(f"module:{module}")
        results: dict[str, dict[str, Any]] = {}
        graph_truncated = False
        for candidate in candidate_targets:
            query = GraphQuery(
                query_id=self._query_id("related-tests", {"target": candidate}),
                query_type=QueryType.DEPENDENCY,
                source_entities=[candidate],
                constraints={"direction": "incoming", "max_depth": 1, "relation_types": ["TESTS"]},
            )
            graph_result = self._query_graph(query)
            graph_truncated = graph_truncated or bool(graph_result.get("metadata", {}).get("truncated", False))
            for item in graph_result.get("discovered_nodes", []):
                if item.get("entity_type") == "TestFile":
                    path = item.get("path")
                    test_node_id = self.file_nodes.get(str(path))
                    edge_evidence = [
                        evidence for evidence in graph_result.get("evidence", [])
                        if evidence.get("subject_id") == test_node_id and evidence.get("predicate") == "TESTS"
                    ][:3]
                    results[str(path)] = {
                        "path": path,
                        "relationship": "static_import",
                        "source_sha256": self.file_hashes.get(str(path)),
                        "graph_evidence": edge_evidence,
                    }
        module_candidates: list[str] = []
        if selector.startswith("module:"):
            module_candidates.append(selector[len("module:"):])
        if node is not None and node.attributes.get("module"):
            module_candidates.append(str(node.attributes.get("module")))
        if node is not None and node.attributes.get("path"):
            module_from_path = _module_name(str(node.attributes.get("path")), self.python_source_roots)
            if module_from_path:
                module_candidates.append(module_from_path)
        if not module_candidates and not selector.startswith(("file:", "symbol:", "finding:")):
            module_candidates.append(selector)
        module_candidates = sorted(set(candidate for candidate in module_candidates if candidate))
        path_candidate = selector[len("file:"):] if selector.startswith("file:") else selector
        for path, text in sorted(self.contents.items()):
            if not self._is_test_path(path) or path in results:
                continue
            lines = _source_lines(text)
            for line_number, line in enumerate(lines, start=1):
                exact_module_match = any(_contains_identifier_reference(line, candidate) for candidate in module_candidates)
                exact_path_match = path_candidate.endswith(".py") and _contains_identifier_reference(line, path_candidate)
                if exact_module_match or exact_path_match:
                    results[path] = {
                        "path": path,
                        "relationship": "text_reference",
                        "line": line_number,
                        "snippet": _redact_then_truncate(line, MAX_SNIPPET_CHARS),
                        "source_sha256": self.file_hashes[path],
                    }
                    break
        ordered = [results[path] for path in sorted(results)]
        visible = ordered[:max_results]
        for item in visible:
            item["pytest_static_assessment"] = self._pytest_static_assessment(str(item["path"]))
        truncated = len(ordered) > max_results or graph_truncated
        index_incomplete = self.evidence_index_status != "complete"
        return {
            "target": selector,
            "tests": visible,
            "candidate_count": len(ordered),
            "returned_count": len(visible),
            "truncated": bool(truncated),
            "coverage_status": "partial" if truncated or index_incomplete else "complete_for_query",
            "evidence_index_status": self.evidence_index_status,
            "note": "Pytest classification uses visible filename configuration and static AST parsing only. It does not import or execute test modules; import edges and text references do not prove a test executes in a workflow.",
        }

    def _trace_execution_context(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return bounded static caller/dependency/entrypoint/workflow context."""
        self._check_keys(args, {"target", "max_depth", "max_results"}, {"target"})
        selector = self._string(args, "target", maximum=500)
        max_depth = self._bounded_int(args, "max_depth", 3, 1, MAX_NEIGHBOR_DEPTH)
        max_results = self._bounded_int(args, "max_results", 20, 1, MAX_GRAPH_RESULTS)
        target_id = self._resolve_node(selector)
        target_node = self.graph.get_node(target_id)
        target_path = str((target_node.attributes if target_node else {}).get("path", ""))
        if target_id.startswith("module:"):
            target_module_id = target_id
        elif target_path:
            module = _module_name(target_path, self.python_source_roots)
            target_module_id = self.module_nodes.get(module, "") if module else ""
        else:
            target_module_id = ""
        if not target_module_id:
            raise EvidenceToolError("target_not_python_module", "Static execution context requires a resolvable Python module target")

        incoming: dict[str, list[SemanticEdge]] = defaultdict(list)
        outgoing: dict[str, list[SemanticEdge]] = defaultdict(list)
        # Query each module's outgoing native adjacency once; this observes each
        # IMPORTS edge occurrence once while retaining both directed indexes.
        for module_node_id in sorted(set(self.module_nodes.values())):
            for edge in self._context_edges(
                module_node_id, direction="outgoing", relation_types={"IMPORTS"},
                operation="trace_execution_context",
            ):
                if edge.metadata.get("execution_context") == "type_checking_only":
                    continue
                incoming[edge.target_id].append(edge)
                outgoing[edge.source_id].append(edge)
        for adjacency in (incoming, outgoing):
            for values in adjacency.values():
                values.sort(key=lambda edge: (
                    str(edge.metadata.get("path", "")),
                    int(edge.metadata.get("line") or 0), edge.source_id, edge.target_id,
                ))

        def walk(start: str, adjacency: Mapping[str, list[SemanticEdge]]) -> tuple[list[dict[str, Any]], bool, set[str]]:
            queue: list[tuple[str, int]] = [(start, 0)]
            visited = {start}
            records: list[dict[str, Any]] = []
            related_nodes: set[str] = set()
            truncated = False
            cursor = 0
            while cursor < len(queue):
                current, depth = queue[cursor]
                cursor += 1
                if depth >= max_depth:
                    if adjacency.get(current):
                        truncated = True
                    continue
                for edge in adjacency.get(current, []):
                    next_node = edge.source_id if adjacency is incoming else edge.target_id
                    path = str(edge.metadata.get("path", ""))
                    record = {
                        "path": path,
                        "source_module": edge.source_id,
                        "target_module": edge.target_id,
                        "line": edge.metadata.get("line"),
                        "depth": depth + 1,
                        "relation": "IMPORTS",
                        "source_sha256": self.file_hashes.get(path),
                    }
                    records.append(record)
                    if next_node != start:
                        related_nodes.add(next_node)
                    if next_node not in visited:
                        visited.add(next_node)
                        queue.append((next_node, depth + 1))
                    if len(records) > max_results:
                        truncated = True
                        break
                if len(records) > max_results:
                    break
            return records[:max_results], truncated, related_nodes

        caller_relationships, caller_truncated, caller_nodes = walk(target_module_id, incoming)
        dependency_relationships, dependency_truncated, dependency_nodes = walk(target_module_id, outgoing)
        caller_paths = sorted({item["path"] for item in caller_relationships if item.get("path") in self.contents})
        dependency_paths = sorted({
            path for node_id in dependency_nodes
            for path in self.module_paths.get(str(self.node_metadata.get(node_id, {}).get("module", "")), [])
            if path in self.contents
        })

        def has_main_guard(source: str) -> bool:
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError):
                return False
            for node in ast.walk(tree):
                if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
                    continue
                test = node.test
                if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
                    continue
                left, right = test.left, test.comparators[0]
                if isinstance(left, ast.Name) and left.id == "__name__" and isinstance(right, ast.Constant) and right.value == "__main__":
                    return True
                if isinstance(right, ast.Name) and right.id == "__name__" and isinstance(left, ast.Constant) and left.value == "__main__":
                    return True
            return False

        entrypoints: list[tuple[str, str]] = []
        for path, source in sorted(self.contents.items()):
            if PurePosixPath(path).suffix.lower() != ".py":
                continue
            module = _module_name(path, self.python_source_roots)
            if not module:
                continue
            if module.endswith(".__main__") or has_main_guard(source):
                entrypoints.append((path, module))

        def reaches_target(start_module: str) -> bool:
            start_id = self.module_nodes.get(start_module)
            if not start_id:
                return False
            queue = [(start_id, 0)]
            visited = {start_id}
            cursor = 0
            while cursor < len(queue):
                current, depth = queue[cursor]
                cursor += 1
                if current == target_module_id:
                    return True
                if depth >= max_depth:
                    continue
                for edge in outgoing.get(current, []):
                    if edge.target_id not in visited:
                        visited.add(edge.target_id)
                        queue.append((edge.target_id, depth + 1))
            return False

        relevant_entrypoints = [(path, module) for path, module in entrypoints if reaches_target(module)]
        entrypoint_paths = sorted({path for path, _ in relevant_entrypoints})
        entrypoint_context_relationships: list[dict[str, Any]] = []
        for entrypoint_path, entrypoint_module in relevant_entrypoints:
            entrypoint_id = self.module_nodes.get(entrypoint_module)
            if not entrypoint_id:
                continue
            for edge in outgoing.get(entrypoint_id, []):
                if edge.target_id == target_module_id:
                    continue
                target_module = str(self.node_metadata.get(edge.target_id, {}).get("module", ""))
                for context_path in self.module_paths.get(target_module, []):
                    if context_path in self.contents:
                        entrypoint_context_relationships.append({
                            "entrypoint_path": entrypoint_path,
                            "path": context_path,
                            "target_module": target_module,
                            "line": edge.metadata.get("line"),
                            "relationship": "direct_import_from_python_entrypoint",
                            "source_sha256": self.file_hashes.get(context_path),
                        })
        entrypoint_context_relationships.sort(key=lambda item: (item["entrypoint_path"], item["path"]))
        entrypoint_context_paths = sorted({item["path"] for item in entrypoint_context_relationships})
        entrypoint_truncated = len(entrypoint_context_paths) > max_results or len(entrypoint_paths) > max_results
        entrypoint_paths = entrypoint_paths[:max_results]
        entrypoint_context_paths = entrypoint_context_paths[:max_results]

        workflow_result = self._find_workflow_context(
            {"target": selector, "max_results": max_results},
            _operation="trace_execution_context.workflow_context",
        )
        active_workflow_paths = workflow_result.get("workflows", []) if isinstance(workflow_result, Mapping) else []
        workflow_truncated = bool(workflow_result.get("truncated", False)) if isinstance(workflow_result, Mapping) else True
        truncated = caller_truncated or dependency_truncated or entrypoint_truncated or workflow_truncated
        index_incomplete = self.evidence_index_status != "complete"
        return {
            "target": selector,
            "resolved_target": target_id,
            "target_path": target_path or None,
            "target_module": target_module_id,
            "coverage_status": "partial" if truncated or index_incomplete else "complete_for_query",
            "truncated": bool(truncated),
            "evidence_index_status": self.evidence_index_status,
            "static_caller_relationships": caller_relationships,
            "static_caller_paths": caller_paths[:max_results],
            "static_dependency_relationships": dependency_relationships,
            "static_dependency_paths": dependency_paths[:max_results],
            "python_entrypoint_paths": entrypoint_paths,
            "entrypoint_context_relationships": entrypoint_context_relationships[:max_results],
            "entrypoint_context_paths": entrypoint_context_paths,
            "active_workflow_paths": active_workflow_paths[:max_results],
            "workflow_coverage_status": workflow_result.get("coverage_status", "partial") if isinstance(workflow_result, Mapping) else "partial",
            "limitations": [
                "Static import and workflow relationships do not prove runtime execution.",
                "Python entrypoint identification is based on source syntax and package layout only.",
                "No repository code or tests were executed.",
            ],
        }

    def _discover_case_context(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find bounded case/fixture descriptions and return safe line-numbered previews."""
        self._check_keys(args, {"max_results"})
        max_results = self._bounded_int(args, "max_results", 20, 1, MAX_SEARCH_RESULTS)
        allowed_suffixes = {".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini"}
        candidates: list[tuple[str, str, str]] = []
        for path in sorted(self.contents):
            if _is_sensitive_path(path):
                continue
            pure = PurePosixPath(path)
            basename = pure.name.casefold()
            components = {part.casefold() for part in pure.parts[:-1]}
            stem = pure.stem.casefold()
            if pure.suffix.lower() not in allowed_suffixes:
                continue
            if basename.startswith("readme"):
                category = "fixture_description" if components.intersection({"fixture", "fixtures", "scenario", "scenarios"}) else "readme_description"
                reason = "README-style repository or fixture description candidate"
            elif "incident" in stem or "incident" in components:
                category = "incident_metadata"
                reason = "Incident-named structured or descriptive metadata candidate"
            elif "case" in stem or "case" in components:
                category = "case_metadata"
                reason = "Case-named metadata candidate"
            elif "scenario" in stem or "scenario" in components:
                category = "scenario_metadata"
                reason = "Scenario-named metadata candidate"
            elif "fixture" in stem or components.intersection({"fixture", "fixtures"}):
                category = "fixture_metadata"
                reason = "Fixture-named metadata candidate"
            elif "metadata" in stem or "metadata" in components:
                category = "case_metadata"
                reason = "Metadata-named context candidate"
            else:
                continue
            candidates.append((path, category, reason))

        visible = candidates[:max_results]
        metadata_candidates: list[dict[str, Any]] = []
        preview_budget = 24_000
        for path, category, reason in visible:
            source = self.contents[path]
            lines = _source_lines(source)
            rendered_full = [f"{number}: {_redact_text(line)}" for number, line in enumerate(lines, start=1)]
            full_preview_chars = sum(len(line) + 1 for line in rendered_full)
            complete = len(lines) <= 120 and len(source) <= 6_000 and full_preview_chars <= preview_budget
            if complete:
                rendered = rendered_full
            else:
                rendered = []
                remaining = preview_budget
                for number, line in enumerate(lines[:40], start=1):
                    prefix = f"{number}: "
                    if remaining <= len(prefix):
                        break
                    safe_line = _redact_text(line)
                    safe_line = safe_line[: max(0, remaining - len(prefix) - 1)]
                    rendered_line = prefix + safe_line + ("…" if len(safe_line) < len(_redact_text(line)) else "")
                    rendered.append(rendered_line)
                    remaining -= len(rendered_line) + 1
                preview_budget -= sum(len(line) + 1 for line in rendered)
            if complete:
                preview_budget -= full_preview_chars
            metadata_candidates.append({
                "path": path,
                "category": category,
                "reason": reason,
                "source_sha256": self.file_hashes[path],
                "total_lines": len(lines),
                "line_numbered_preview": rendered,
                "preview_line_numbered": True,
                "redaction_applied": True,
                "content_complete": complete,
                "content_omitted": not complete,
                "preview_truncated": not complete,
            })
        truncated = len(candidates) > max_results
        index_incomplete = self.evidence_index_status != "complete"
        return {
            "candidate_count": len(candidates),
            "returned_count": len(metadata_candidates),
            "metadata_candidates": metadata_candidates,
            "truncated": bool(truncated),
            "coverage_status": "partial" if truncated or index_incomplete else "complete_for_query",
            "evidence_index_status": self.evidence_index_status,
            "note": "A complete line-numbered preview with a source hash may count as inspected context. Incomplete previews require read_source_file. No repository code or tests are executed.",
        }

    def _find_workflow_context(
        self, args: dict[str, Any], *, _operation: str = "find_workflow_context"
    ) -> dict[str, Any]:
        self._check_keys(args, {"target", "max_results"}, {"target"})
        selector = self._string(args, "target", maximum=500)
        max_results = self._bounded_int(args, "max_results", 15, 1, MAX_SEARCH_RESULTS)
        target_id = self._resolve_node(selector)
        target_node = self.graph.get_node(target_id)
        target_module_ids: set[str] = set()
        if target_id.startswith("module:"):
            target_module_ids.add(target_id)
        if target_node is not None and PurePosixPath(str(target_node.attributes.get("path", ""))).suffix.lower() == ".py":
            module = _module_name(str(target_node.attributes["path"]), self.python_source_roots)
            if module in self.module_nodes:
                target_module_ids.add(self.module_nodes[module])

        # Index only IMPORTS edges for transitive workflow context. This is a
        # bounded BFS over the same canonical SemanticGraph and avoids walking
        # unrelated symbol/definition edges when a workflow invokes a package.
        import_adjacency: dict[str, list[SemanticEdge]] = defaultdict(list)
        invoke_adjacency: dict[str, list[SemanticEdge]] = defaultdict(list)
        context_source_ids = sorted(set(self.module_nodes.values()) | set(self.file_nodes.values()))
        for source_id in context_source_ids:
            for edge in self._context_edges(
                source_id, direction="outgoing",
                relation_types={"IMPORTS", "PACKAGE_ENTRYPOINT", "INVOKES"},
                operation=_operation,
            ):
                if edge.relation_type == "IMPORTS":
                    if edge.metadata.get("execution_context") == "type_checking_only":
                        continue
                    import_adjacency[edge.source_id].append(edge)
                elif edge.relation_type == "PACKAGE_ENTRYPOINT":
                    import_adjacency[edge.source_id].append(edge)
                elif edge.relation_type == "INVOKES":
                    invoke_adjacency[edge.source_id].append(edge)
        for values in import_adjacency.values():
            values.sort(key=lambda edge: (edge.target_id, int(edge.metadata.get("line") or 0), edge.source_id))

        def import_path(source: str, target: str, max_depth: int = 4) -> list[SemanticEdge] | None:
            nonlocal path_visit_count, path_budget_exhausted
            if source == target:
                return []
            queue: list[tuple[str, list[SemanticEdge]]] = [(source, [])]
            visited = {source}
            cursor = 0
            while cursor < len(queue):
                if path_visit_count >= MAX_WORKFLOW_PATH_VISITS:
                    path_budget_exhausted = True
                    return None
                path_visit_count += 1
                current, path = queue[cursor]
                cursor += 1
                if len(path) >= max_depth:
                    continue
                for edge in import_adjacency.get(current, []):
                    if edge.target_id in visited:
                        continue
                    next_path = path + [edge]
                    if edge.target_id == target:
                        return next_path
                    visited.add(edge.target_id)
                    queue.append((edge.target_id, next_path))
            return None

        results: dict[str, dict[str, Any]] = {}
        active_workflow_paths = {
            item.get("path") for item in self.report.get("workflows", [])
            if item.get("active_workflow_candidate") and item.get("status") == "scanned"
        }
        all_workflow_paths = [path for path in sorted(self.file_nodes)
                              if _file_kind(path) == "WorkflowDefinition" and path in active_workflow_paths]
        workflow_candidates_truncated = len(all_workflow_paths) > MAX_WORKFLOW_CANDIDATES
        workflow_paths = all_workflow_paths[:MAX_WORKFLOW_CANDIDATES]
        path_visit_count = 0
        path_budget_exhausted = False
        for workflow_path in workflow_paths:
            if path_budget_exhausted:
                break
            workflow_id = self.file_nodes[workflow_path]
            for invoke_edge in invoke_adjacency.get(workflow_id, []):
                if path_budget_exhausted:
                    break
                invoked = invoke_edge.target_id
                path_edges: list[SemanticEdge] | None = None
                final_file_edge: SemanticEdge | None = None
                relationship = "direct_invocation"
                if invoked == target_id:
                    path_edges = []
                else:
                    for target_module_id in sorted(target_module_ids):
                        module_path = import_path(invoked, target_module_id)
                        if module_path is None:
                            continue
                        path_edges = module_path
                        if target_id.startswith("file:") and target_id != target_module_id:
                            target_file_path = str((target_node.attributes if target_node else {}).get("path", ""))
                            if target_file_path:
                                final_file_edge = next((
                                    edge for edge in self._context_edges(
                                        target_module_id, direction="outgoing",
                                        relation_types={"IMPLEMENTED_BY"}, operation=_operation,
                                    ) if edge.target_id == target_id
                                ), None)
                                if final_file_edge is None:
                                    continue
                        relationship = "transitive_static_path"
                        break
                if path_edges is None:
                    continue
                all_edges = [invoke_edge, *path_edges]
                if final_file_edge is not None:
                    all_edges.append(final_file_edge)
                path_steps = []
                graph_evidence = []
                for depth, edge in enumerate(all_edges, start=1):
                    metadata = dict(edge.metadata)
                    path_steps.append({
                        "from": edge.source_id, "to": edge.target_id,
                        "relation": edge.relation_type, "depth": depth,
                        "source_path": metadata.get("path"), "line": metadata.get("line"),
                        "execution_context": metadata.get("execution_context"),
                    })
                    graph_evidence.append({
                        "evidence_id": self._edge_evidence_id(edge),
                        "subject_id": edge.source_id,
                        "predicate": edge.relation_type,
                        "object_id": edge.target_id,
                        "verification_status": "observed",
                        "source_kind": "semantic_edge",
                        "provenance": {"edge_attributes": dict(edge.attributes), "edge_metadata": metadata},
                    })
                candidate = {
                    "path": workflow_path,
                    "source_sha256": self.file_hashes.get(workflow_path),
                    "relationship": relationship,
                    "path_length": len(all_edges),
                    "path_steps": path_steps,
                    "graph_evidence": graph_evidence,
                }
                current = results.get(workflow_path)
                if current is None or candidate["path_length"] < current["path_length"]:
                    results[workflow_path] = candidate

        ordered = [results[key] for key in sorted(results, key=lambda path: (results[path]["path_length"], path))]
        return {
            "target": selector,
            "workflows": ordered[:max_results],
            "truncated": len(ordered) > max_results or path_budget_exhausted or workflow_candidates_truncated,
            "coverage_status": "partial" if len(ordered) > max_results or path_budget_exhausted or workflow_candidates_truncated else "complete_for_query",
            "traversal_visits": path_visit_count,
            "workflow_candidates_examined": len(workflow_paths),
            "stop_reason": "max_workflow_path_visits" if path_budget_exhausted else ("max_workflow_candidates" if workflow_candidates_truncated else None),
            "note": "Direct and transitive paths are static source/workflow observations, not proof that a workflow ran or imported code at runtime.",
        }

    @staticmethod
    def _edge_evidence_id(edge: SemanticEdge) -> str:
        from audit_engine.semantic_audit.graph.analysis.identity import edge_fingerprint
        return edge_fingerprint(edge)

    def _search_decision_history(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_keys(args, {"query", "max_results"}, {"query"})
        query = self._string(args, "query").casefold()
        max_results = self._bounded_int(args, "max_results", 10, 1, MAX_SEARCH_RESULTS)
        prefixes = (
            "decision_memory/decisions/", "decision_memory/outcomes/", "decision_memory/actions/",
            "decision_memory/rules/", "decision_memory/links/", "docs/decisions/", "docs/audit-engine/",
        )
        matches: list[dict[str, Any]] = []
        for path in sorted(self.contents):
            if not path.startswith(prefixes):
                continue
            for line_number, line in enumerate(_source_lines(self.contents[path]), start=1):
                if query not in line.casefold():
                    continue
                matches.append({
                    "path": path, "line": line_number,
                    "snippet": _redact_then_truncate(line, MAX_SNIPPET_CHARS),
                    "source_sha256": self.file_hashes[path],
                })
                if len(matches) > max_results:
                    break
            if len(matches) > max_results:
                break
        truncated = len(matches) > max_results
        return {"query": _redact_text(query), "matches": matches[:max_results], "truncated": truncated,
                "search_scope": list(prefixes),
                "note": "Historical records are retrieval context, not automatically authoritative decisions."}


def create_tool_server(repo_root: str | Path, **kwargs: Any) -> RepositoryEvidenceTools:
    """Create the evidence tool registry for use by a future LLM orchestration loop."""
    return RepositoryEvidenceTools(repo_root, **kwargs)
