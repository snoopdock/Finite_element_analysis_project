#!/usr/bin/env python3
"""Deterministic G3.1.1 domain verification acceptance artifact generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.promotion import CandidatePromotionPolicy, CandidatePromotionService
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.verification import (
    CandidateKnowledge,
    GraphAttributeConstraintVerifier,
    ObservationContractVerifier,
    ProvenanceCompletenessVerifier,
    RequiredRelationshipVerifier,
    VerifierRegistry,
    VerificationObligation,
    VerificationService,
)


def registry_service():
    registry = VerifierRegistry()
    for verifier in (
        GraphAttributeConstraintVerifier(),
        ProvenanceCompletenessVerifier(),
        RequiredRelationshipVerifier(),
        ObservationContractVerifier(),
    ):
        registry.register(verifier)
    return VerificationService(registry)


def run_validation(output_path: Path) -> tuple[dict, int]:
    graph = SemanticGraph()
    graph.add_node(SemanticNode("prod", "Module", {"lifecycle": "production"}))
    graph.add_node(SemanticNode("exp", "Module", {"lifecycle": "experimental"}))
    graph.add_node(SemanticNode("claim", "ScientificClaim"))
    graph.add_node(SemanticNode("source", "EvidenceArtifact"))
    graph.add_edge(SemanticEdge("prod", "exp", "DEPENDS_ON", metadata={"source_id": "code:1"}))
    graph.add_edge(SemanticEdge("claim", "source", "SUPPORTED_BY", metadata={"source_id": "paper:1"}))

    service = registry_service()
    dependency = SemanticGraphAnalysisService(graph).analyze(
        GraphQuery("validation-dependency", QueryType.DEPENDENCY, ["prod"], {"max_depth": 1})
    )
    architecture_rule = DomainRuleLoader.from_yaml(
        "specs/rules/architecture/no_production_to_experimental_dependency.yaml"
    )
    architecture = DomainRuleExecutor(service).execute(architecture_rule, dependency, graph)

    claim = SemanticGraphAnalysisService(graph).analyze(
        GraphQuery("validation-claim", QueryType.STRUCTURAL, ["claim"], {"direction": "outgoing"})
    )
    scientific_rule = DomainRuleLoader.from_yaml(
        "specs/rules/scientific/claim_requires_support_relationship.yaml"
    )
    scientific = DomainRuleExecutor(service).execute(scientific_rule, claim, graph)

    obs = dependency.observations[0]
    candidate = CandidateKnowledge.create(
        subject_id=obs.subject_id,
        predicate=obs.predicate,
        object_id=obs.object_id,
        evidence_ids=obs.evidence_ids,
    )
    obligation = VerificationObligation.from_analysis_result(
        dependency,
        obligation_type="observation_contract",
        observation_ids=[obs.observation_id],
        evidence_ids=list(obs.evidence_ids),
        requested_verifier_ids=["observation-contract"],
        parameters={
            "candidate_id": candidate.candidate_id,
            "subject_id": candidate.subject_id,
            "predicate": candidate.predicate,
            "object_id": candidate.object_id,
        },
    )
    receipt = service.verify(obligation, dependency, verifier_id="observation-contract")
    target = SemanticGraph()
    target.add_node(SemanticNode("prod", "Module"))
    target.add_node(SemanticNode("exp", "Module"))
    promotion = CandidatePromotionService().promote(
        candidate=candidate,
        obligation=obligation,
        receipt=receipt,
        target_graph=target,
        policy=CandidatePromotionPolicy("validation-promotion", "1"),
    )

    checks = {
        "architecture_rule_produces_verified_finding": len(architecture.findings) == 1,
        "architecture_finding_has_receipt": bool(architecture.findings and architecture.findings[0].receipt_id),
        "scientific_supported_claim_not_flagged": len(scientific.findings) == 0,
        "domain_rules_route_named_verifiers": all(o.requested_verifier_ids for o in architecture.obligations),
        "candidate_promotion_requires_receipt": promotion.promoted and bool(receipt.receipt_id),
        "promotion_changes_target_graph": promotion.graph_fingerprint_before != promotion.graph_fingerprint_after,
        "promotion_records_provenance": bool(target.edges[0].metadata.get("promotion", {}).get("receipt_id")),
        "domain_rule_contract_present": Path("specs/contracts/semantic_domain_rule_contract.yaml").is_file(),
        "promotion_contract_present": Path("specs/contracts/candidate_promotion_contract.yaml").is_file(),
        "domain_rule_examples_present": all(
            Path(path).is_file()
            for path in (
                "specs/rules/architecture/no_production_to_experimental_dependency.yaml",
                "specs/rules/provenance/evidence_requires_source_identity.yaml",
                "specs/rules/scientific/claim_requires_support_relationship.yaml",
            )
        ),
    }
    payload = {
        "schema_version": "semantic_domain_verification_validation/v1",
        "checks": checks,
        "passed": all(checks.values()),
        "architecture_execution": architecture.to_dict(),
        "scientific_execution": scientific.to_dict(),
        "promotion": promotion.to_dict(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not payload["passed"]:
        return payload, 1
    print("G3.1.1 semantic domain verification validation passed.")
    return payload, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="artifacts/semantic_domain_verification_validation.json",
        help="Path for the deterministic validation artifact.",
    )
    args = parser.parse_args()
    _, status = run_validation(Path(args.output))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
