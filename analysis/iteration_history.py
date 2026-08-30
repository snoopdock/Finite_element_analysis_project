#!/usr/bin/env python3
"""Iteration history keyed by stable section identity."""

from typing import Dict, List

from core.section_identity import get_section_id


class IterationHistory:
    def __init__(self):
        self.audits: Dict[str, List[bool]] = {}
        self.anomalies: Dict[str, int] = {}
        self.anomaly_counts: Dict[str, int] = {}
        self.section_titles: Dict[str, str] = {}

    @staticmethod
    def _section_key(section) -> str:
        if isinstance(section, dict):
            section_id = get_section_id(section)
            if section_id:
                return section_id
            return str(section.get("title", ""))
        return str(section or "")

    def register_section(self, section) -> str:
        key = self._section_key(section)
        if isinstance(section, dict):
            title = str(section.get("title", "")).strip()
            section_id = get_section_id(section)
            if title and section_id:
                self.section_titles[title] = section_id
        return key

    def resolve_section_key(self, section_or_title) -> str:
        if isinstance(section_or_title, dict):
            return self._section_key(section_or_title)
        title = str(section_or_title or "")
        return self.section_titles.get(title, title)

    def record_clean_audit(self, section) -> None:
        key = self.register_section(section)
        if not key:
            return
        self.audits.setdefault(key, []).append(True)

    def record_failed_audit(self, section) -> None:
        key = self.register_section(section)
        if not key:
            return
        self.audits.setdefault(key, []).append(False)

    def record_anomaly(self, key: str) -> None:
        if not key:
            return
        self.anomalies[key] = self.anomalies.get(key, 0) + 1

    def reset_anomaly(self, key: str) -> None:
        if key in self.anomalies:
            self.anomalies[key] = 0

    def clear_all_anomalies(self) -> None:
        for key in list(self.anomalies.keys()):
            self.anomalies[key] = 0

    def get_anomaly_counts(self) -> Dict[str, int]:
        return dict(self.anomaly_counts)

    def set_anomaly_counts(self, counts: Dict[str, int]) -> None:
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
            cleaned[key] = max(0, numeric)
        self.anomaly_counts = cleaned

    def to_dict(self) -> Dict:
        return {
            "audits": self.audits,
            "anomalies": self.anomalies,
            "anomaly_counts": self.anomaly_counts,
            "section_titles": self.section_titles,
        }

    def load_from_dict(self, data: Dict) -> None:
        if not isinstance(data, dict):
            return
        audits = data.get("audits", {})
        anomalies = data.get("anomalies", {})
        titles = data.get("section_titles", {})
        self.audits = audits if isinstance(audits, dict) else {}
        self.anomalies = anomalies if isinstance(anomalies, dict) else {}
        self.set_anomaly_counts(data.get("anomaly_counts", {}))
        self.section_titles = titles if isinstance(titles, dict) else {}
