"""
Provenance artifact generation utilities.
"""

import json

from pathlib import Path

from audit_engine.semantic_audit.graph.backend.provenance_serializer import (
    ProvenanceSerializer,
)


class ProvenanceArtifactWriter:


    def write_json(
        self,
        result,
        output_path,
    ):

        data = ProvenanceSerializer.to_dict(result)

        path = Path(output_path)

        path.write_text(
            json.dumps(
                data,
                indent=2,
            ),
            encoding="utf-8",
        )

        return path
