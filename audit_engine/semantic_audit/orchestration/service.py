"""Facade for G3.3 audit orchestration planning and execution."""

from __future__ import annotations

from .execution import execute_orchestration_plan
from .planner import build_orchestration_plan


class AuditOrchestrationService:
    def plan(self, **kwargs):
        return build_orchestration_plan(**kwargs)

    def execute(self, **kwargs):
        return execute_orchestration_plan(**kwargs)
