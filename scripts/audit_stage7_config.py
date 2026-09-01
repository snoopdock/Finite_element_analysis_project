#!/usr/bin/env python3
"""Read-only audit for Stage 7 concept-relationship configuration."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        with CONFIG.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        semantic = config.get("semantic_verification", {}) if isinstance(config, dict) else {}
        check(semantic.get("concept_relationship_enabled") is False, "Concept-relationship analysis is not disabled by default.")
        check(int(semantic.get("max_concept_relationship_pairs_per_cycle", 0)) > 0, "Concept-pair limit is not positive.")
        check(int(semantic.get("max_concept_relationship_propositions_per_pair", 0)) > 0, "Proposition-per-pair limit is not positive.")
        check(int(semantic.get("concept_relationship_max_records", 0)) > 0, "Proposal ledger limit is not positive.")
        check(int(semantic.get("concept_relationship_max_tokens", 0)) > 0, "Concept-relationship token limit is not positive.")

        print("Stage 7 concept relationship configuration audit")
        print("================================================")
        print("PASS: disabled-by-default behavior and finite analysis bounds passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 CONFIG AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
