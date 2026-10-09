"""Facade for G3.3 audit orchestration planning, execution, and adaptive continuation."""

from __future__ import annotations

from .adaptive import run_adaptive_orchestration
from .execution import execute_orchestration_plan
from .planner import build_orchestration_plan
from .replanning import build_adaptive_replan


class AuditOrchestrationService:
    def plan(self, **kwargs):
        return build_orchestration_plan(**kwargs)

    def execute(self, **kwargs):
        return execute_orchestration_plan(**kwargs)

    def replan(self, **kwargs):
        return build_adaptive_replan(**kwargs)

    def execute_adaptively(self, **kwargs):
        return run_adaptive_orchestration(**kwargs)
