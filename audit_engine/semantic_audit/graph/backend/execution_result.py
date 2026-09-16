"""
Backend execution result contract with provenance support.
"""


class BackendExecutionResult:

    def __init__(
        self,
        backend,
        output,
        provenance_records=None,
        transformation_records=None,
        loss_assessment=None,
        metadata=None,
    ):
        self.backend = backend
        self.output = output
        self.provenance_records = provenance_records or []
        self.transformation_records = transformation_records or []
        self.loss_assessment = loss_assessment
        self.metadata = metadata or {}

    def summary(self):
        return {
            "backend": self.backend,
            "metadata": self.metadata,
            "provenance_count": len(self.provenance_records),
            "transformation_count": len(self.transformation_records),
            "lossless": (
                self.loss_assessment.lossless
                if self.loss_assessment
                else None
            ),
        }
