"""AE-31 report-only live LLM diagnosis for repository reliability issues."""
from .diagnosis import (
    DiagnosticError,
    ae29_compatible_snapshot,
    canonical_json_bytes,
    extract_retrieval_summary,
    probe_semantic_scholar,
    run_diagnostic,
    safe_read_file,
    sha256_bytes,
    sha256_json,
)

__all__ = [
    "DiagnosticError",
    "ae29_compatible_snapshot",
    "canonical_json_bytes",
    "extract_retrieval_summary",
    "probe_semantic_scholar",
    "run_diagnostic",
    "safe_read_file",
    "sha256_bytes",
    "sha256_json",
]
