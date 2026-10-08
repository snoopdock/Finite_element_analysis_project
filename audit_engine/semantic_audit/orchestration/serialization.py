"""JSON serialization helpers for G3.3 orchestration artifacts."""

from __future__ import annotations

import json
from pathlib import Path


class OrchestrationArtifactSerializer:
    @staticmethod
    def dumps(artifact) -> str:
        return json.dumps(artifact.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def write(cls, artifact, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cls.dumps(artifact) + "\n", encoding="utf-8")
        return path
