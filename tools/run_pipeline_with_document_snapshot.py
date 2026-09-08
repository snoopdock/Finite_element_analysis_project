#!/usr/bin/env python3
"""Run the existing pipeline and persist its semantic document snapshot.

This is a transitional integration entry point. The existing ``main.py``
remains unchanged; after a successful pipeline invocation, the resulting
``output/sections.json`` is converted to ``output/document.json`` using the
semantic document pipeline integration layer.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.document_pipeline_integration import persist_pipeline_document
from utils.text import load_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the existing FEA pipeline and persist document.json."
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Pipeline configuration passed to main.py.",
    )
    args = parser.parse_args(argv)

    command = [sys.executable, str(ROOT / "main.py"), "--config", args.config]
    completed = subprocess.run(command, cwd=ROOT)

    if completed.returncode != 0:
        return completed.returncode

    sections_path = ROOT / "output" / "sections.json"
    document_path = ROOT / "output" / "document.json"

    sections = load_json(sections_path, [])
    if not isinstance(sections, list):
        print(
            "Pipeline completed, but output/sections.json is not a list.",
            file=sys.stderr,
        )
        return 2

    try:
        persist_pipeline_document(
            sections,
            document_path,
        )
    except Exception as exc:
        print(
            f"Failed to persist semantic document: {exc}",
            file=sys.stderr,
        )
        return 3

    print(f"Semantic document persisted to {document_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
