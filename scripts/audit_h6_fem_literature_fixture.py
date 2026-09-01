#!/usr/bin/env python3
"""Audit the small FEM literature trial manifest without downloading PDFs."""

from pathlib import Path

import yaml


MANIFEST = Path(__file__).resolve().parents[1] / "audits" / "fixtures" / "h6_fem_literature_manifest.yaml"


def main() -> int:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert data["name"] == "h6_fem_literature_trial"
    sources = data["sources"]
    assert len(sources) == 4
    assert len({item["source_id"] for item in sources}) == 4
    assert len({item["source_type"] for item in sources}) >= 3
    assert len({item["scientific_role"] for item in sources}) == 4

    # The fixture is metadata-only: no PDF byte payload or embedded base64 is stored.
    assert data["trial_requirements"]["do_not_store_pdf_bytes"] is True
    for source in sources:
        serialized_source = str(source).lower()
        assert "pdf_bytes" not in source
        assert "base64" not in serialized_source
        assert "pdf_bytes:" not in serialized_source

    # Bibliographic metadata must not be interpreted as evidence.
    for source in sources:
        assert "claims" not in source
        assert "evidence_relation_ids" not in source
        assert "proposition_ids" not in source

    print("H6 FEM literature fixture audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
