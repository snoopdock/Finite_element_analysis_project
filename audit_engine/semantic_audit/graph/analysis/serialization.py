"""Serialization of reusable semantic graph analysis artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .results import ANALYSIS_SCHEMA_VERSION, GraphAnalysisResult


class AnalysisArtifactSerializer:
    @staticmethod
    def result_to_dict(result: GraphAnalysisResult) -> dict:
        return result.to_dict()

    @staticmethod
    def bundle_to_dict(results: Iterable[GraphAnalysisResult]) -> dict:
        materialized = list(results)
        return {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "result_count": len(materialized),
            "results": [result.to_dict() for result in materialized],
        }

    @classmethod
    def write_bundle(
        cls,
        results: Iterable[GraphAnalysisResult],
        output_path: str | Path,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cls.bundle_to_dict(results), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path
