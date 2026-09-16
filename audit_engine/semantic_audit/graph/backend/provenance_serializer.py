"""
Serialization utilities for semantic graph provenance objects.
"""

import json


class ProvenanceSerializer:

    @staticmethod
    def to_dict(result):

        return {
            "backend": result.backend,
            "metadata": result.metadata,
            "provenance": [
                item.to_dict()
                for item in result.provenance_records
            ],
            "transformations": [
                item.to_dict()
                for item in result.transformation_records
            ],
            "loss_assessment": (
                result.loss_assessment.to_dict()
                if result.loss_assessment
                else None
            ),
        }


    @staticmethod
    def to_json(result):

        return json.dumps(
            ProvenanceSerializer.to_dict(result),
            indent=2,
        )
