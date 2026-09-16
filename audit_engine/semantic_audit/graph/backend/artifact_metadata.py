"""
Artifact metadata model.
"""

from datetime import datetime, timezone


class ArtifactMetadata:

    def __init__(
        self,
        schema_version="1.0",
        generated_by="SemanticGraphBackend",
        graph_version="1.0",
        execution_context=None,
    ):
        self.schema_version = schema_version
        self.generated_by = generated_by
        self.graph_version = graph_version
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.execution_context = execution_context or {}

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "generated_by": self.generated_by,
            "graph_version": self.graph_version,
            "created_at": self.created_at,
            "execution_context": self.execution_context,
        }
