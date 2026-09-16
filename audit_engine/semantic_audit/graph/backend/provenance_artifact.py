"""
Versioned provenance artifact generation.
"""

from pathlib import Path
import json

from audit_engine.semantic_audit.graph.backend.provenance_serializer import (
    ProvenanceSerializer,
)

from audit_engine.semantic_audit.graph.backend.artifact_metadata import (
    ArtifactMetadata,
)


class ProvenanceArtifactWriter:

    def write_json(self, result, output_path, metadata=None):

        artifact = {
            "metadata": (
                metadata.to_dict()
                if metadata
                else ArtifactMetadata().to_dict()
            ),
            "execution": ProvenanceSerializer.to_dict(result),
        }

        path = Path(output_path)

        path.write_text(
            json.dumps(artifact, indent=2),
            encoding="utf-8",
        )

        return path
