#!/usr/bin/env python3
"""Writing Indicator - Computes eta for each section."""

import sys


class WritingIndicator:
    def __init__(self, w_L=0.4, w_U=0.4, w_A=0.2, leverage_map=None):
        self.w_L = w_L
        self.w_U = w_U
        self.w_A = w_A

        # FIX Eff-3: Accept leverage map from config instead of hardcoding
        if leverage_map is not None:
            self.leverage_map = leverage_map
        else:
            self.leverage_map = {
                "Introduction and Scope of the Finite Element Method": 1.0,
                "Mathematical Foundation: Strong Form, Weak Form, and Galerkin Method": 0.8,
                "The Finite Element Procedure": 0.6,
                "Rules for Modeling Physical Phenomena with FEM": 0.4,
                "Verification, Validation, and Best Practices": 0.2,
            }

    def compute(self, topic: str, history) -> float:
        L = self.leverage_map.get(topic)

        # Handle unknown/dynamic titles
        if L is None:
            if ": " in topic:
                parent = topic.split(": ")[0]
                L = self.leverage_map.get(parent, 0.5)
            elif "(merged with" in topic:
                L = 0.5
            else:
                L = 0.5
                print(f"  [Indicator] Warning: '{topic}' not in leverage_map, "
                      f"using default L=0.5", file=sys.stderr)

        audits = history.audits.get(topic, [])
        w = 3
        window = audits[-w:]
        U = 1.0 - (sum(window) / len(window)) if window else 1.0

        A = 0.0
        for key, count in history.anomalies.items():
            if topic in key and count > 0:
                A = 1.0
                break

        eta = self.w_L * L + self.w_U * U + self.w_A * A
        return eta
