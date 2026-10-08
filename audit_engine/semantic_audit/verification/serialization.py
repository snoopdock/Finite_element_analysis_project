
"""Serialization for verification obligations and receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import VerificationObligation
from .receipts import VerificationReceipt


VERIFICATION_BUNDLE_SCHEMA_VERSION = "semantic_verification_bundle/v1"


class VerificationArtifactSerializer:
    @staticmethod
    def bundle_to_dict(
        obligations: Iterable[VerificationObligation],
        receipts: Iterable[VerificationReceipt],
    ) -> dict:
        obligation_list = list(obligations)
        receipt_list = list(receipts)
        return {
            "schema_version": VERIFICATION_BUNDLE_SCHEMA_VERSION,
            "obligation_count": len(obligation_list),
            "receipt_count": len(receipt_list),
            "obligations": [item.to_dict() for item in obligation_list],
            "receipts": [item.to_dict() for item in receipt_list],
        }

    @classmethod
    def write_bundle(cls, obligations, receipts, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cls.bundle_to_dict(obligations, receipts), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path
