#!/usr/bin/env python3
"""Deterministic production-code integrity audit.

Checks Python syntax/compilation and imports without invoking network services,
Cloudflare, Semantic Scholar, arXiv, Wikipedia, or LLMs.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import py_compile
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "tests"}
SMOKE_MODULES = [
    "main",
    "core.pipeline",
    "core.convergence",
    "core.writer_orchestration",
    "providers.cloudflare",
    "processing.llm_parser",
    "analysis.gap_detector",
    "analysis.citation_validator",
    "writing.dynamic_writer",
    "writing.policy_dynamic_writer",
]


def iter_python_files():
    for path in ROOT.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def audit_python_files():
    failures = []
    checked = 0
    for path in sorted(iter_python_files()):
        checked += 1
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
            py_compile.compile(
                str(path),
                doraise=True,
                quiet=1,
            )
        except Exception as exc:
            failures.append({
                "file": str(path.relative_to(ROOT)),
                "error": f"{type(exc).__name__}: {exc}",
            })
    return checked, failures


def audit_imports():
    failures = []
    imported = []
    for module_name in SMOKE_MODULES:
        try:
            importlib.import_module(module_name)
            imported.append(module_name)
        except Exception as exc:
            failures.append({
                "module": module_name,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=5),
            })
    return imported, failures


def main() -> int:
    sys.path.insert(0, str(ROOT))

    checked_files, syntax_failures = audit_python_files()
    imported, import_failures = audit_imports()

    print(f"Python files checked: {checked_files}")
    print(f"Import smoke modules passed: {len(imported)}/{len(SMOKE_MODULES)}")

    if syntax_failures:
        print("Syntax/compile failures:")
        for item in syntax_failures:
            print(f"  - {item['file']}: {item['error']}")

    if import_failures:
        print("Import failures:")
        for item in import_failures:
            print(f"  - {item['module']}: {item['error']}")

    if syntax_failures or import_failures:
        print("Code integrity audit: FAIL")
        return 1

    print("Code integrity audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
