"""
Backend execution result contract.

Provides a common wrapper around backend-specific outputs.
"""


class BackendExecutionResult:

    def __init__(
        self,
        backend,
        output,
        metadata=None,
        provenance=None,
        transformations=None,
        loss_report=None,
    ):

        self.backend = backend
        self.output = output
        self.metadata = metadata or {}
        self.provenance = provenance or {}
        self.transformations = transformations or []
        self.loss_report = loss_report or {}


    def summary(self):

        return {
            "backend": self.backend,
            "metadata": self.metadata,
            "transformations": self.transformations,
            "loss_report": self.loss_report,
        }
