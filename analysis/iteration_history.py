#!/usr/bin/env python3
"""Iteration History - Tracks audits, anomalies, and OAA state across cycles."""

from typing import Dict, List, Optional


class IterationHistory:
    def __init__(self):
        self.audits: Dict[str, List[bool]] = {}
        self.anomalies: Dict[str, int] = {}
        self.anomaly_counts: Dict[str, int] = {}  # FIX #8: Persistent OAA anomaly counts

    def record_clean_audit(self, section: str):
        self.audits.setdefault(section, []).append(True)

    def record_failed_audit(self, section: str):
        self.audits.setdefault(section, []).append(False)

    def record_anomaly(self, key: str):
        self.anomalies[key] = self.anomalies.get(key, 0) + 1

    def reset_anomaly(self, key: str):
        """Clear an anomaly when it is resolved by an adjustment."""
        if key in self.anomalies:
            self.anomalies[key] = 0

    def clear_all_anomalies(self):
        for key in self.anomalies:
            self.anomalies[key] = 0

    def get_anomaly_counts(self) -> Dict[str, int]:
        """FIX #8: Get persisted OAA anomaly counts."""
        return dict(self.anomaly_counts)

    def set_anomaly_counts(self, counts: Dict[str, int]):
        """FIX #8: Set OAA anomaly counts from persisted state."""
        self.anomaly_counts = dict(counts)

    def to_dict(self) -> Dict:
        return {
            "audits": self.audits,
            "anomalies": self.anomalies,
            "anomaly_counts": self.anomaly_counts,  # FIX #8: Persist OAA counts
        }

    def load_from_dict(self, data: Dict):
        self.audits = data.get("audits", {})
        self.anomalies = data.get("anomalies", {})
        self.anomaly_counts = data.get("anomaly_counts", {})  # FIX #8: Load OAA counts
