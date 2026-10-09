from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.high_assurance import (
    HighAssuranceExecutionStatus,
    builtin_high_assurance_adapter_registry,
    ControlledHighAssuranceExecutor,
)
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationDecision

from .conftest import static_import_obligation


def test_static_import_adapter_confirms_absence(analysis_result, semantic_graph):
    obligation = static_import_obligation(analysis_result, "import os\nfrom pathlib import Path\n")
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    record = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import")
    assert record.status is HighAssuranceExecutionStatus.EXECUTED
    assert record.result.decision is VerificationDecision.CONFIRMED
    assert record.result.evidence_state is VerificationStatus.VALIDATED
    assert record.result.validation_envelope.completeness.value == "exhaustive_within_scope"


def test_static_import_adapter_refutes_forbidden_import(analysis_result, semantic_graph):
    obligation = static_import_obligation(analysis_result, "import networkx as nx\n")
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    result = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import").result
    assert result.decision is VerificationDecision.REFUTED
    assert any(w.kind.value == "counterexample" for w in result.witnesses)
    assert "networkx" in str(result.witnesses[-1].details)


def test_static_import_adapter_matches_submodules(analysis_result, semantic_graph):
    obligation = static_import_obligation(analysis_result, "from networkx.algorithms import shortest_path\n")
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    result = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import").result
    assert result.decision is VerificationDecision.REFUTED


def test_static_import_adapter_records_dynamic_import_exclusion(analysis_result, semantic_graph):
    obligation = static_import_obligation(analysis_result, "import importlib\nimportlib.import_module('networkx')\n")
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    result = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import").result
    assert result.decision is VerificationDecision.CONFIRMED
    assert any("dynamic imports" in value for value in result.validation_envelope.excluded_scope)


def test_static_import_adapter_is_inconclusive_on_syntax_error(analysis_result, semantic_graph):
    obligation = static_import_obligation(analysis_result, "def broken(:\n")
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    result = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import").result
    assert result.decision is VerificationDecision.INCONCLUSIVE
    assert result.evidence_state is VerificationStatus.OBSERVED
    assert result.validation_envelope.completeness.value == "partial"


def test_static_import_execution_serialization_does_not_leak_source(analysis_result, semantic_graph):
    secret = "import os\n# highly-sensitive-source-marker"
    obligation = static_import_obligation(analysis_result, secret)
    executor = ControlledHighAssuranceExecutor(builtin_high_assurance_adapter_registry())
    payload = executor.execute(obligation, VerificationContext(analysis_result, semantic_graph), adapter_id="python-static-import").to_dict()
    assert "highly-sensitive-source-marker" not in str(payload)
