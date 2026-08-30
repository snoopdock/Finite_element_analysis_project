#!/usr/bin/env python3
"""
Iteration History.

Tracks:
- section audit history
- anomaly history
- persistent OAA hysteresis counters
"""

from typing import Dict, List


class IterationHistory:

    def __init__(self):
        self.audits: Dict[str, List[bool]] = {}
        self.anomalies: Dict[str, int] = {}
        self.anomaly_counts: Dict[str, int] = {}

    # ------------------------------------------------------------
    # Audit history
    # ------------------------------------------------------------

    def record_clean_audit(
        self,
        section: str,
    ) -> None:
        if not section:
            return

        self.audits.setdefault(
            section,
            [],
        ).append(True)

    def record_failed_audit(
        self,
        section: str,
    ) -> None:
        if not section:
            return

        self.audits.setdefault(
            section,
            [],
        ).append(False)

    # ------------------------------------------------------------
    # General anomaly history
    # ------------------------------------------------------------

    def record_anomaly(
        self,
        key: str,
    ) -> None:
        if not key:
            return

        self.anomalies[key] = (
            self.anomalies.get(key, 0)
            + 1
        )

    def reset_anomaly(
        self,
        key: str,
    ) -> None:
        if key in self.anomalies:
            self.anomalies[key] = 0

    def clear_all_anomalies(self) -> None:
        for key in list(
            self.anomalies.keys()
        ):
            self.anomalies[key] = 0

    # ------------------------------------------------------------
    # Persistent OAA hysteresis
    # ------------------------------------------------------------

    def get_anomaly_counts(
        self,
    ) -> Dict[str, int]:
        return dict(
            self.anomaly_counts
        )

    def set_anomaly_counts(
        self,
        counts: Dict[str, int],
    ) -> None:
        if not isinstance(counts, dict):
            self.anomaly_counts = {}
            return

        cleaned = {}

        for key, value in counts.items():
            if not isinstance(key, str):
                continue

            try:
                numeric = int(value)
            except (TypeError, ValueError):
                continue

            cleaned[key] = max(
                0,
                numeric,
            )

        self.anomaly_counts = cleaned

    # ------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------

    def to_dict(self) -> Dict:
        return {
            "audits": self.audits,
            "anomalies": self.anomalies,
            "anomaly_counts": self.anomaly_counts,
        }

    def load_from_dict(
        self,
        data: Dict,
    ) -> None:
        if not isinstance(data, dict):
            return

        audits = data.get(
            "audits",
            {},
        )

        anomalies = data.get(
            "anomalies",
            {},
        )

        anomaly_counts = data.get(
            "anomaly_counts",
            {},
        )

        self.audits = (
            audits
            if isinstance(audits, dict)
            else {}
        )

        self.anomalies = (
            anomalies
            if isinstance(anomalies, dict)
            else {}
        )

        self.set_anomaly_counts(
            anomaly_counts
        )
