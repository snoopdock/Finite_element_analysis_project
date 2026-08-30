#!/usr/bin/env python3
"""Writing Indicator - Computes eta for each section."""

import sys
from typing import Any

from core.section_identity import get_section_id


class WritingIndicator:
    def __init__(self, w_L=0.4, w_U=0.4, w_A=0.2, leverage_map=None):
        self.w_L = float(w_L)
        self.w_U = float(w_U)
        self.w_A = float(w_A)
        self.leverage_map = dict(leverage_map) if leverage_map is not None else {
            "Introduction and Scope of the Finite Element Method": 1.0,
            "Mathematical Foundation: Strong Form, Weak Form, and Galerkin Method": 0.8,
            "The Finite Element Procedure": 0.6,
            "Rules for Modeling Physical Phenomena with FEM": 0.4,
            "Verification, Validation, and Best Practices": 0.2,
        }

    @staticmethod
    def _title(section: Any) -> str:
        return str(section.get("title", "")) if isinstance(section, dict) else str(section or "")

    def _history_key(self, section: Any, history) -> str:
        if isinstance(section, dict):
            return get_section_id(section) or self._title(section)
        title = str(section or "")
        resolver = getattr(history, "resolve_section_key", None)
        if callable(resolver):
            return resolver(title)
        return title

    def _leverage(self, title: str) -> float:
        value = self.leverage_map.get(title)
        if value is not None:
            return float(value)
        if ": " in title:
            parent = title.split(": ", 1)[0]
            value = self.leverage_map.get(parent)
            if value is not None:
                return float(value)
        print(f"  [Indicator] Warning: '{title}' not in leverage_map, using default L=0.5", file=sys.stderr)
        return 0.5

    def compute(self, section: Any, history) -> float:
        title = self._title(section)
        history_key = self._history_key(section, history)
        L = self._leverage(title)

        audits = history.audits.get(history_key, [])
        window = audits[-3:]
        U = 1.0 - (sum(bool(value) for value in window) / len(window)) if window else 1.0

        identities = [history_key, title]
        A = 0.0
        for key, count in history.anomalies.items():
            if count <= 0:
                continue
            if any(identity and identity in key for identity in identities):
                A = 1.0
                break

        eta = self.w_L * L + self.w_U * U + self.w_A * A
        return max(0.0, min(1.0, eta))
