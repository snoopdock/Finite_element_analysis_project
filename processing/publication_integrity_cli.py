"""Validate generated LaTeX, compile to bounded convergence, and emit a publication manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from processing.publication_integrity import (
    PublicationIntegrityError,
    assert_latex_integrity,
    build_publication_manifest,
    compile_latex_pdf,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tex", required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--semantic-document", default="")
    parser.add_argument("--state", default="")
    parser.add_argument("--ir-contract", default="")
    parser.add_argument("--passes", type=int, default=2, help="minimum LaTeX passes")
    parser.add_argument("--max-passes", type=int, default=5, help="hard upper bound for LaTeX convergence")
    parser.add_argument("--engine", default="pdflatex")
    args = parser.parse_args(argv)

    tex_path = Path(args.tex)
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        tex = tex_path.read_text(encoding="utf-8")
        source_report = assert_latex_integrity(tex)
        compilation = compile_latex_pdf(
            tex_path,
            args.pdf,
            passes=args.passes,
            max_passes=args.max_passes,
            engine=args.engine,
        )
        manifest = build_publication_manifest(
            tex_path=tex_path,
            pdf_path=args.pdf,
            source_issues=source_report.issues,
            compilation=compilation,
            semantic_document_path=args.semantic_document or None,
            state_path=args.state or None,
            ir_contract_path=args.ir_contract or None,
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            "Publication integrity passed: static audit OK; "
            f"{args.engine} converged in {compilation.passes} pass(es) "
            f"(minimum={compilation.minimum_passes}, maximum={compilation.maximum_passes}); "
            f"PDF={args.pdf}"
        )
        return 0
    except (OSError, PublicationIntegrityError, ValueError) as exc:
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "failed",
                    "tex": str(tex_path),
                    "pdf": str(args.pdf),
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Publication integrity failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
