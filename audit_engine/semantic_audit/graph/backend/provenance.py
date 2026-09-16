"""
Backend provenance and transformation tracking models.
"""


class ProvenanceRecord:

    def __init__(
        self,
        source,
        backend,
        description=None,
    ):
        self.source = source
        self.backend = backend
        self.description = description or ""


    def to_dict(self):

        return {
            "source": self.source,
            "backend": self.backend,
            "description": self.description,
        }



class TransformationRecord:

    def __init__(
        self,
        operation,
        input_type,
        output_type,
    ):
        self.operation = operation
        self.input_type = input_type
        self.output_type = output_type


    def to_dict(self):

        return {
            "operation": self.operation,
            "input_type": self.input_type,
            "output_type": self.output_type,
        }



class LossAssessment:

    def __init__(
        self,
        lossless=True,
        details=None,
    ):
        self.lossless = lossless
        self.details = details or {}


    def to_dict(self):

        return {
            "lossless": self.lossless,
            "details": self.details,
        }
