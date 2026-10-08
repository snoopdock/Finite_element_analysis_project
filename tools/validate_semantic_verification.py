#!/usr/bin/env python3
"""Deterministic G3.1 semantic verification validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.findings import FindingFactory
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext, VerificationStatus
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.rules import RuleEvaluator, SemanticAuditRule
from audit_engine.semantic_audit.verification import (
    CandidateKnowledge,
    EvidenceCorroborationVerifier,
    ObservationContractVerifier,
    VerificationArtifactSerializer,
    VerificationDecision,
    VerificationObligation,
    VerificationService,
    VerifierRegistry,
)


def build_fixture() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id in ("api", "service", "db"):
        graph.add_node(SemanticNode(node_id=node_id, entity_type="SoftwareComponent"))
    graph.add_edge(
        SemanticEdge(
            "api",
            "service",
            "DEPENDS_ON",
            metadata={"source_id": "ast:api", "line": 10},
        )
    )
    graph.add_edge(
        SemanticEdge(
            "service",
            "db",
            "DEPENDS_ON",
            metadata={"source_id": "ast:service", "line": 20},
        )
    )
    return graph


def run_validation(output_path: Path) -> dict:
    context = SemanticContext(
        graph_schema_version="semantic_graph/v1",
        relationship_vocabulary_version="software-relations/v1",
        projection_contract_version="ast-to-semantic-graph/v1",
    )
    result = SemanticGraphAnalysisService(
        build_fixture(), semantic_context=context
    ).analyze(
        GraphQuery(
            "g31-validation",
            QueryType.DEPENDENCY,
            ["api"],
            {"max_depth": 2},
        )
    )

    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    registry.register(EvidenceCorroborationVerifier())
    service = VerificationService(registry)

    observation_obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type="observation_contract",
        requested_verifier_ids=["observation-contract"],
        parameters={
            "subject_id": "api",
            "predicate": "DEPENDS_ON",
            "object_id": "service",
        },
    )
    observation_receipt = service.verify(observation_obligation, result)

    corroboration_obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type="evidence_corroboration",
        requested_verifier_ids=["evidence-corroboration"],
        parameters={
            "independence_key": "source_id",
            "minimum_independent_sources": 2,
        },
    )
    corroboration_receipt = service.verify(corroboration_obligation, result)

    rule = SemanticAuditRule(
        rule_id="validation.verified_dependency_demo",
        version="1.0.0",
        obligation_type="observation_contract",
        title="Validated dependency demonstration",
        finding_message="A deliberately configured validation rule matched the verified observation.",
    )
    evaluation = RuleEvaluator().evaluate(
        rule, observation_obligation, observation_receipt
    )
    finding = FindingFactory.create(rule, evaluation, observation_receipt)

    candidate = CandidateKnowledge.create(
        subject_id="api",
        predicate="POSSIBLY_RELATED_TO",
        object_id="db",
        evidence_ids=observation_obligation.evidence_ids,
        provenance={"producer": "validation-fixture"},
    )

    changed_context = SemanticContext(
        graph_schema_version="semantic_graph/v1",
        relationship_vocabulary_version="software-relations/v2",
        projection_contract_version="ast-to-semantic-graph/v1",
    )

    checks = {
        "semantic_context_bound": result.semantic_context.fingerprint == observation_obligation.semantic_context_fingerprint,
        "analysis_identity_context_sensitive": result.to_dict()["semantic_context_fingerprint"] == result.semantic_context.fingerprint,
        "observation_contract_confirmed": observation_receipt.decision is VerificationDecision.CONFIRMED,
        "observation_contract_validated": observation_receipt.evidence_state is VerificationStatus.VALIDATED,
        "corroboration_confirmed": corroboration_receipt.decision is VerificationDecision.CONFIRMED,
        "corroboration_not_overpromoted": corroboration_receipt.evidence_state is VerificationStatus.CORROBORATED,
        "rule_evaluation_precedes_finding": finding.receipt_id == observation_receipt.receipt_id,
        "finding_bound_to_semantic_context": finding.semantic_context_fingerprint == result.semantic_context.fingerprint,
        "candidate_is_proposed": candidate.state is VerificationStatus.PROPOSED,
        "receipt_detects_semantic_context_staleness": observation_receipt.is_stale_for(
            graph_fingerprint=result.graph_fingerprint,
            semantic_context_fingerprint=changed_context.fingerprint,
        ),
    }

    payload = {
        "schema_version": "semantic_verification_validation/v1",
        "status": "PASSED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "architecture_guards": {
            "graph_analysis_creates_findings": False,
            "verification_creates_findings": False,
            "candidate_can_mutate_canonical_graph": False,
            "evidence_state_separate_from_verification_decision": True,
        },
        "verification_artifacts": VerificationArtifactSerializer.bundle_to_dict(
            [observation_obligation, corroboration_obligation],
            [observation_receipt, corroboration_receipt],
        ),
        "sample_finding": finding.to_dict(),
        "sample_candidate": candidate.to_dict(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if payload["status"] != "PASSED":
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit("G3.1 semantic verification validation failed: " + ", ".join(failed))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="artifacts/semantic_verification_validation.json",
    )
    args = parser.parse_args()
    payload = run_validation(Path(args.output))
    print(json.dumps(payload["checks"], indent=2))
    print("G3.1 semantic verification validation passed.")


if __name__ == "__main__":
    main()
