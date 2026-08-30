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
        return (
            str(section.get("title", ""))
            if isinstance(section, dict)
            else str(section or "")
        )

    def _history_key(self, section: Any, history) -> str:
        """Resolve a section to its stable identity whenever possible."""
        if isinstance(section, dict):
            section_id = get_section_id(section)
            if section_id:
                return section_id

        title = self._title(section)
        resolver = getattr(
            history,
            "resolve_section_key",
            None,
        )

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

        print(
            f"  [Indicator] Warning: '{title}' not in leverage_map, "
            "using default L=0.5",
            file=sys.stderr,
        )
        return 0.5

    def _anomaly_applies(self, key: str, history_key: str, title: str) -> bool:
        """Determine whether a history anomaly belongs to this section."""
        if not key:
            return False

        if history_key and history_key in key:
            return True

        if title and title in key:
            return True

        return False

    def compute(self, section: Any, history) -> float:
        title = self._title(section)
        history_key = self._history_key(
            section,
            history,
        )

        L = self._leverage(title)

        audits = history.audits.get(
            history_key,
            [],
        )

        window = audits[-3:]

        if window:
            U = 1.0 - (
                sum(bool(value) for value in window)
                / len(window)
            )
        else:
            U = 1.0

        A = 0.0

        # OAA anomaly records may be keyed by stable UUIDs. During
        # migration/compatibility, title-based records are also accepted.
        for key, count in history.anomalies.items():
            if count <= 0:
                continue

            if self._anomaly_applies(
                str(key),
                history_key,
                title,
            ):
                A = 1.0
                break

        eta = (
            self.w_L * L
            + self.w_U * U
            + self.w_A * A
        )

        return max(
            0.0,
            min(1.0, eta),
        )
