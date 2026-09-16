"""
Backend pipeline producing provenance-aware results.
"""

from audit_engine.semantic_audit.graph.backend.execution_result import (
    BackendExecutionResult,
)

from audit_engine.semantic_audit.graph.backend.provenance import (
    ProvenanceRecord,
    TransformationRecord,
    LossAssessment,
)


class BackendPipeline:

    def __init__(self, selector, factory):
        self.selector = selector
        self.factory = factory

    def execute(self, requirements, context):

        backend_name = self.selector.select(requirements)

        adapter = self.factory.create(
            backend_name,
            context,
        )

        return BackendExecutionResult(
            backend=backend_name,
            output=adapter,
            metadata={
                "task_type": context.task_type,
            },
            provenance_records=[
                ProvenanceRecord(
                    source="SemanticGraph",
                    backend=backend_name,
                )
            ],
            transformation_records=[
                TransformationRecord(
                    operation="backend_projection",
                    input_type="SemanticGraph",
                    output_type=adapter.__class__.__name__,
                )
            ],
            loss_assessment=LossAssessment(
                lossless=True
            ),
        )
