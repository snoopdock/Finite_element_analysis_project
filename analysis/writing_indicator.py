#!/usr/bin/env python3
"""Writing Indicator - Computes eta for each section."""

import sys

from core.section_identity import get_section_id


class WritingIndicator:
    def __init__(self, w_L=0.4, w_U=0.4, w_A=0.2, leverage_map=None):
        self.w_L = w_L
        self.w_U = w_U
        self.w_A = w_A
        self.leverage_map = leverage_map if leverage_map is not None else {
            "Introduction and Scope of the Finite Element Method": 1.0,
            "Mathematical Foundation: Strong Form, Weak Form, and Galerkin Method": 0.8,
            "The Finite Element Procedure": 0.6,
            "Rules for Modeling Physical Phenomena with FEM": 0.4,
            "Verification, Validation, and Best Practices": 0.2,
        }

    def compute(self, topic, history) -> float:
        """Compute eta while separating display title from history identity."""
        if isinstance(topic, dict):
            title = str(topic.get("title", ""))
            section_id = get_section_id(topic)
            history_key = section_id or title
        else:
            title = str(topic or "")
            history_key = title

        L = self.leverage_map.get(title)
        if L is None:
            if ": " in title:
                parent = title.split(": ", 1)[0]
                L = self.leverage_map.get(parent, 0.5)
            else:
                L = 0.5
                print(
                    f"  [Indicator] Warning: '{title}' not in leverage_map, using default L=0.5",
                    file=sys.stderr,
                )

        audits = history.audits.get(history_key, [])
        window = audits[-3:]
        U = 1.0 - (sum(window) / len(window)) if window else 1.0

        A = 0.0
        section_tokens = {history_key, title}
        for key, count in history.anomalies.items():
            if count <= 0:
                continue
            # New anomaly keys use UUIDs; legacy keys may still contain titles.
            if any(token and token in key for token in section_tokens):
                A = 1.0
                break

        return self.w_L * L + self.w_U * U + self.w_A * A
