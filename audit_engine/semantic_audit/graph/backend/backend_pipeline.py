"""
Semantic Graph Backend Pipeline.

Coordinates backend selection,
adapter creation,
execution,
and result generation.
"""

from audit_engine.semantic_audit.graph.backend.execution_result import (
    BackendExecutionResult,
)


class BackendPipeline:

    def __init__(self, selector, factory):
        self.selector = selector
        self.factory = factory

    def execute(self, requirements, context):

        backend_name = self.selector.select(
            requirements
        )

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
            provenance={
                "source": "BackendPipeline",
            },
            transformations=[
                "backend_selection",
                "adapter_creation",
            ],
            loss_report={
                "lossless": True,
            },
        )
