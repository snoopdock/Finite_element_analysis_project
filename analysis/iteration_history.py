#!/usr/bin/env python3
"""Iteration History - Tracks audits and anomalies across cycles."""

class IterationHistory:
    def __init__(self):
        self.audits = {}
        self.anomalies = {}

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

    def get_clean_audit_count(self, section: str) -> int:
        audits = self.audits.get(section, [])
        count = 0
        for a in reversed(audits):
            if a: count += 1
            else: break
        return count

    def to_dict(self):
        return {"audits": self.audits, "anomalies": self.anomalies}

    def load_from_dict(self, data: dict):
        self.audits = data.get("audits", {})
        self.anomalies = data.get("anomalies", {})
