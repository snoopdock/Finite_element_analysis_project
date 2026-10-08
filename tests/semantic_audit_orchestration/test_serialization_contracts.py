import json
from pathlib import Path

from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.orchestration import (
    AuditBudget,
    OrchestrationArtifactSerializer,
    VerificationMethod,
    VerificationObjective,
    VerifierOrchestrationProfile,
    VerifierProfileCatalog,
    build_orchestration_plan,
)
from audit_engine.semantic_audit.verification import VerifierRegistry

from .conftest import CheapConfirmVerifier


def test_plan_serializes_to_json(tmp_path, observation_obligation):
    registry = VerifierRegistry(); registry.register(CheapConfirmVerifier())
    catalog = VerifierProfileCatalog(); catalog.register(
        VerifierOrchestrationProfile(
            "cheap-confirm", "1.0.0", VerificationMethod.CONTRACT, 1,
            VerificationStatus.VALIDATED,
        )
    )
    objective = VerificationObjective.create(
        obligation_id=observation_obligation.obligation_id,
        minimum_evidence_state=VerificationStatus.VALIDATED,
    )
    plan = build_orchestration_plan(
        obligations=[observation_obligation], objectives=[objective], registry=registry,
        profiles=catalog, budget=AuditBudget(1, 1),
    )
    path = OrchestrationArtifactSerializer.write(plan, tmp_path / "plan.json")
    payload = json.loads(path.read_text())
    assert payload["plan_id"] == plan.plan_id
    assert payload["reserved_cost_units"] == 1


def test_g330_contracts_and_schemas_present():
    for path in (
        "specs/contracts/semantic_audit_orchestration_contract.yaml",
        "specs/contracts/verification_resource_profile_contract.yaml",
        "specs/contracts/audit_budget_contract.yaml",
        "specs/contracts/orchestration_execution_contract.yaml",
        "specs/schemas/semantic_audit_orchestration_plan.schema.json",
        "specs/schemas/semantic_audit_orchestration_execution.schema.json",
    ):
        assert Path(path).is_file(), path
