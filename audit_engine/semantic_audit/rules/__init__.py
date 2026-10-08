"""Declarative semantic audit rules."""

from .domain_loader import DomainRuleLoader
from .domain_models import DomainAuditRule, DomainRuleScope, DomainRuleSelector
from .evaluator import RuleEvaluator
from .loader import RuleLoader
from .models import (
    RuleDisposition,
    RuleEvaluationResult,
    RuleSeverity,
    SemanticAuditRule,
)

__all__ = [
    "DomainAuditRule",
    "DomainRuleExecutionResult",
    "DomainRuleExecutor",
    "DomainRuleLoader",
    "DomainRuleScope",
    "DomainRuleSelector",
    "RuleDisposition",
    "RuleEvaluationResult",
    "RuleEvaluator",
    "RuleLoader",
    "RuleSeverity",
    "SemanticAuditRule",
]


def __getattr__(name):
    """Load finding-dependent execution types lazily to avoid package cycles."""
    if name in {"DomainRuleExecutionResult", "DomainRuleExecutor"}:
        from .execution import DomainRuleExecutionResult, DomainRuleExecutor

        return {
            "DomainRuleExecutionResult": DomainRuleExecutionResult,
            "DomainRuleExecutor": DomainRuleExecutor,
        }[name]
    raise AttributeError(name)
