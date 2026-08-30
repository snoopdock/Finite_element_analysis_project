#!/usr/bin/env python3
"""Formal Layer Router - Routes questions to the correct solver."""

class FormalRouter:
    def detect_question_type(self, question: str) -> str:
        """Determine if question is existence, optimization, universal, etc."""
        raise NotImplementedError("Formal layer is not yet active.")
        
    def route(self, question_type: str, eta: float, tau: float) -> str:
        """Route to SAT, SMT, CP-SAT, Lean, or skip."""
        raise NotImplementedError("Formal layer is not yet active.")
