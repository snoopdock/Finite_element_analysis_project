"""AE-27: controlled, language-agnostic neurosymbolic proposal gateway.

AE-27 accepts model-generated candidate relationships as quarantined hypotheses.
The gateway binds proposals to the exact AE-24 contract and the AE-26 semantic
state, restricts model context to authoritative observations, supports
many-to-many evidence links, and evaluates candidate sets through bounded
counterfactual AE-25 reasoning.

No model is invoked here, no source program is executed, and no candidate is
promoted into the authoritative graph.
"""
from __future__ import annotations

from collections import defaultdict
import copy
from typing import Any, Mapping
import re

from audit_engine.semantic_audit.ae24.contracts import (
    admit,
    canonical,
    sha,
    ContractError,
)
from audit_engine.semantic_audit.ae25.reasoner import analyze as symbolic_analyze
from audit_engine.semantic_audit.ae26.semantics import snapshot as semantic_snapshot

SCHEMA = "ae27/neurosymbolic-proposal/v2"
ADJUDICATION_SCHEMA = "ae27/neurosymbolic-adjudication/v2"
DECISIONS = frozenset({"accept", "reject", "defer"})
LINK_KINDS = frozenset({"supports", "contradicts"})
MAX_CANDIDATES = 200
MAX_CONTEXT_OCCURRENCES = 2000
MAX_LINKS = 2000
MAX_REVIEWS = 1000
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ProposalError(ValueError):
    """Invalid proposal, stale context, unsupported link, or failed replay."""


def _body_without_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    body = copy.deepcopy(value)
    body.pop(field, None)
    return body


def _validate_model(model: Any) -> None:
    if not isinstance(model, dict):
        raise ProposalError("Model metadata is required")
    allowed = {"adapter_id", "model_family", "model_version", "context_sha256"}
    required = {"adapter_id", "model_family", "model_version", "context_sha256"}
    if set(model) - allowed or not required <= set(model):
        raise ProposalError("Invalid model metadata")
    for key in ("adapter_id", "model_family", "model_version"):
        if not isinstance(model[key], str) or not model[key] or len(model[key]) > 256:
            raise ProposalError("Invalid model metadata value")
    if not isinstance(model["context_sha256"], str) or not DIGEST.fullmatch(model["context_sha256"]):
        raise ProposalError("Invalid model context digest")


def _assertion_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in contract["assertions"]}


def _validate_candidate_shape(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    candidate: dict[str, Any],
    existing_ids: set[str],
) -> None:
    if not isinstance(candidate, dict):
        raise ProposalError("Candidate assertion must be an object")
    required = {"id", "subject", "predicate", "object", "origin", "source_id"}
    allowed = required | {"attributes"}
    if set(candidate) - allowed or not required <= set(candidate):
        raise ProposalError("Invalid candidate assertion keys")
    if not isinstance(candidate["id"], str) or not SAFE_ID.fullmatch(candidate["id"]):
        raise ProposalError("Invalid candidate occurrence identity")
    if candidate["id"] in existing_ids:
        raise ProposalError("Candidate occurrence collides with base assertion")
    if candidate["origin"] != "candidate":
        raise ProposalError("Neural proposal assertions must have candidate origin")

    # AE-24 remains the typed contract gate. The candidate is admitted only into
    # an isolated copy; it never mutates the caller's authoritative contract.
    probe = copy.deepcopy(contract)
    probe["assertions"] = list(probe["assertions"]) + [copy.deepcopy(candidate)]
    try:
        admit(probe, sources)
    except (ContractError, ValueError) as exc:
        raise ProposalError(f"Candidate fails AE-24 contract admission: {exc}") from exc


def _context_fingerprint(
    graph_fingerprint: str,
    semantic_fingerprint: str,
    occurrences: list[str],
) -> str:
    return sha(
        canonical(
            {
                "graph_fingerprint": graph_fingerprint,
                "semantic_fingerprint": semantic_fingerprint,
                "context_occurrences": sorted(set(occurrences)),
            }
        )
    )


def _context_semantic_ids(
    semantic: Any,
    context: list[str],
) -> tuple[str, ...]:
    by_occurrence = {edge.occurrence_id: edge.semantic_id for edge in semantic.edges}
    return tuple(sorted({by_occurrence[occurrence] for occurrence in context}))


def validate_proposal(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Validate and return normalized proposal metadata without promotion."""
    if not isinstance(proposal, dict):
        raise ProposalError("Proposal must be an object")

    allowed = {
        "schema_version",
        "proposal_id",
        "base_contract_sha256",
        "base_graph_fingerprint",
        "base_semantic_fingerprint",
        "base_hypothesis_fingerprint",
        "context_occurrences",
        "candidate_assertions",
        "evidence_links",
        "model",
        "proposal_sha256",
    }
    required = allowed - {"proposal_sha256"}
    if set(proposal) - allowed or not required <= set(proposal):
        raise ProposalError("Invalid proposal envelope")
    if proposal["schema_version"] != SCHEMA:
        raise ProposalError("Unsupported proposal schema")
    if not isinstance(proposal["proposal_id"], str) or not SAFE_ID.fullmatch(proposal["proposal_id"]):
        raise ProposalError("Invalid proposal identity")

    admission = admit(contract, sources)
    semantic = semantic_snapshot(contract, sources)

    if proposal["base_contract_sha256"] != admission.contract_digest:
        raise ProposalError("Proposal is bound to a different contract")
    if proposal["base_graph_fingerprint"] != admission.graph_digest:
        raise ProposalError("Proposal is stale for the current graph")
    if proposal["base_semantic_fingerprint"] != semantic.semantic_fingerprint:
        raise ProposalError("Proposal is stale for the current semantic state")
    if proposal["base_hypothesis_fingerprint"] != semantic.hypothesis_fingerprint:
        raise ProposalError("Proposal is stale for the current hypothesis state")
    _validate_model(proposal["model"])

    context = proposal["context_occurrences"]
    if (
        not isinstance(context, list)
        or len(context) == 0
        or len(context) > MAX_CONTEXT_OCCURRENCES
        or any(not isinstance(x, str) or not x or len(x) > 256 or x.strip() != x for x in context)
        or len(set(context)) != len(context)
    ):
        raise ProposalError("Invalid proposal context")

    base = _assertion_map(contract)
    if any(x not in base for x in context):
        raise ProposalError("Context occurrence is not in the admitted graph")

    # Model context is restricted to authoritative source-bound facts. A prior
    # candidate hypothesis may remain visible in the graph, but it cannot serve
    # as the context that a new proposal claims to have reasoned over.
    non_authoritative = [
        x for x in context if base[x]["origin"] not in {"declared", "observed"}
    ]
    if non_authoritative:
        raise ProposalError("Context occurrence must be declared or observed")

    expected_context = _context_fingerprint(
        admission.graph_digest,
        semantic.semantic_fingerprint,
        context,
    )
    if proposal["model"]["context_sha256"] != expected_context:
        raise ProposalError("Model context digest mismatch")

    candidates = proposal["candidate_assertions"]
    if (
        not isinstance(candidates, list)
        or not candidates
        or len(candidates) > MAX_CANDIDATES
    ):
        raise ProposalError("Invalid candidate set")

    candidate_ids: set[str] = set()
    for candidate in candidates:
        _validate_candidate_shape(
            contract,
            sources,
            candidate,
            set(base) | candidate_ids,
        )
        candidate_ids.add(candidate["id"])

    links = proposal["evidence_links"]
    if not isinstance(links, list) or len(links) > MAX_LINKS:
        raise ProposalError("Invalid evidence-link set")
    seen_links = set()
    for link in links:
        if (
            not isinstance(link, dict)
            or set(link) != {"candidate_occurrence_id", "evidence_occurrence_id", "kind"}
        ):
            raise ProposalError("Invalid evidence link")
        cid = link["candidate_occurrence_id"]
        eid = link["evidence_occurrence_id"]
        kind = link["kind"]
        key = (cid, eid)
        if (
            cid not in candidate_ids
            or eid not in base
            or kind not in LINK_KINDS
            or key in seen_links
        ):
            raise ProposalError("Invalid or duplicate evidence link")
        if base[eid]["origin"] == "candidate":
            raise ProposalError("Candidate evidence cannot serve as independent evidence")
        seen_links.add(key)

    if "proposal_sha256" not in proposal:
        raise ProposalError("Proposal digest is required")
    expected_digest = sha(canonical(_body_without_digest(proposal, "proposal_sha256")))
    if proposal["proposal_sha256"] != expected_digest:
        raise ProposalError("Proposal digest mismatch")

    return {
        "admission": admission,
        "semantic_snapshot": semantic,
        "candidate_ids": tuple(sorted(candidate_ids)),
        "context_fingerprint": expected_context,
        "context_semantic_ids": _context_semantic_ids(semantic, context),
        "proposal_sha256": expected_digest,
    }


def _probe_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(candidate)
    result["id"] = "probe:" + candidate["id"]
    result["origin"] = "observed"
    return result


def _probe_ids(candidates: list[dict[str, Any]]) -> dict[str, str]:
    return {candidate["id"]: "probe:" + candidate["id"] for candidate in candidates}


def _symbolic_probe_set_internal(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    base_ids = set(_assertion_map(contract))
    candidate_ids = set()
    for candidate in candidates:
        _validate_candidate_shape(contract, sources, candidate, base_ids | candidate_ids)
        candidate_ids.add(candidate["id"])

    probe_map = _probe_ids(candidates)
    if any(probe_id in base_ids for probe_id in probe_map.values()):
        raise ProposalError("Counterfactual probe occurrence collides with base assertion")

    doc = copy.deepcopy(contract)
    doc["assertions"] = list(doc["assertions"]) + [
        _probe_candidate(candidate) for candidate in candidates
    ]
    result = symbolic_analyze(doc, sources)

    probe_ids = set(probe_map.values())
    candidate_results = []
    set_issues = [
        issue for issue in result["issues"]
        if probe_ids.intersection(issue.get("witness_occurrences", []))
    ]
    set_unknowns = [
        item for item in result["unknowns"]
        if probe_ids.intersection(item.get("witness_occurrences", []))
    ]

    for candidate in sorted(candidates, key=lambda row: row["id"]):
        cid = candidate["id"]
        probe_id = probe_map[cid]
        conflicts = [
            issue for issue in set_issues
            if probe_id in issue.get("witness_occurrences", [])
        ]
        unknowns = [
            item for item in set_unknowns
            if probe_id in item.get("witness_occurrences", [])
        ]
        if conflicts:
            status = "symbolically_conflicted"
        elif unknowns:
            status = "symbolically_inconclusive"
        else:
            status = "not_conflicted_under_admitted_rules"
        candidate_results.append(
            {
                "candidate_occurrence_id": cid,
                "probe_status": status,
                "supporting_issue_ids": [x["id"] for x in conflicts],
                "supporting_unknown_ids": [x["id"] for x in unknowns],
            }
        )

    if set_issues:
        set_status = "symbolically_conflicted"
    elif set_unknowns:
        set_status = "symbolically_inconclusive"
    else:
        set_status = "not_conflicted_under_admitted_rules"

    return {
        "probe_scope": "candidate_set",
        "candidate_results": candidate_results,
        "set_status": set_status,
        "set_issue_ids": [x["id"] for x in set_issues],
        "set_unknown_ids": [x["id"] for x in set_unknowns],
        "authority": {
            "counterfactual_only": True,
            "runtime_behavior_verified": False,
            "candidate_promoted": False,
            "joint_candidate_interactions_evaluated": True,
        },
    }


def symbolic_probe_set(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate a candidate set jointly in one isolated AE-25 counterfactual."""
    if not isinstance(candidates, list) or not candidates or len(candidates) > MAX_CANDIDATES:
        raise ProposalError("Invalid candidate set for symbolic probe")
    return _symbolic_probe_set_internal(contract, sources, candidates)


def symbolic_probe(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one candidate through the same counterfactual machinery as a set."""
    if not isinstance(candidate, dict):
        raise ProposalError("Candidate assertion must be an object")
    result = _symbolic_probe_set_internal(contract, sources, [candidate])
    return result["candidate_results"][0] | {
        "probe_scope": "single_candidate",
        "set_status": result["set_status"],
        "authority": result["authority"],
    }


def _validate_reviews(
    candidate_ids: set[str],
    base_ids: set[str],
    reviews: list[dict[str, Any]],
) -> None:
    if not isinstance(reviews, list) or len(reviews) > MAX_REVIEWS:
        raise ProposalError("Invalid review set")
    seen = set()
    for review in reviews:
        required = {
            "id",
            "reviewer_id",
            "candidate_occurrence_ids",
            "decision",
            "evidence_occurrence_ids",
        }
        if not isinstance(review, dict) or set(review) != required:
            raise ProposalError("Invalid review event")
        if (
            not isinstance(review["id"], str)
            or not SAFE_ID.fullmatch(review["id"])
            or review["id"] in seen
        ):
            raise ProposalError("Invalid or duplicate review identity")
        seen.add(review["id"])
        if (
            not isinstance(review["reviewer_id"], str)
            or not review["reviewer_id"]
            or len(review["reviewer_id"]) > 256
        ):
            raise ProposalError("Invalid reviewer identity")
        cids = review["candidate_occurrence_ids"]
        eids = review["evidence_occurrence_ids"]
        if (
            not isinstance(cids, list)
            or not cids
            or len(set(cids)) != len(cids)
            or any(x not in candidate_ids for x in cids)
        ):
            raise ProposalError("Review references unknown candidate")
        if (
            not isinstance(eids, list)
            or len(set(eids)) != len(eids)
            or any(x not in base_ids for x in eids)
        ):
            raise ProposalError("Review references unknown evidence")
        if review["decision"] not in DECISIONS:
            raise ProposalError("Unsupported review decision")


def _review_digest(reviews: list[dict[str, Any]]) -> str:
    """Order-independent identity of the review event set."""
    return sha(canonical(sorted(copy.deepcopy(reviews), key=lambda item: item["id"])))


def adjudicate(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    proposal: dict[str, Any],
    reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine a proposal, joint symbolic probe, and review without promotion."""
    meta = validate_proposal(contract, sources, proposal)
    base = _assertion_map(contract)
    _validate_reviews(set(meta["candidate_ids"]), set(base), reviews)

    link_map = defaultdict(list)
    for link in proposal["evidence_links"]:
        link_map[link["candidate_occurrence_id"]].append(link)

    review_map = defaultdict(list)
    for review in reviews:
        for cid in review["candidate_occurrence_ids"]:
            review_map[cid].append(review)

    candidates = {x["id"]: x for x in proposal["candidate_assertions"]}
    probe = symbolic_probe_set(contract, sources, list(candidates.values()))
    probe_by_candidate = {
        item["candidate_occurrence_id"]: item
        for item in probe["candidate_results"]
    }

    results = []
    for cid in sorted(candidates):
        candidate_probe = probe_by_candidate[cid]
        decisions = {r["decision"] for r in review_map[cid]}
        accepts = sorted(
            r["reviewer_id"] for r in review_map[cid] if r["decision"] == "accept"
        )
        rejects = sorted(
            r["reviewer_id"] for r in review_map[cid] if r["decision"] == "reject"
        )
        deferred = sorted(
            r["reviewer_id"] for r in review_map[cid] if r["decision"] == "defer"
        )
        linked_support = sorted(
            x["evidence_occurrence_id"]
            for x in link_map[cid]
            if x["kind"] == "supports"
        )
        linked_contra = sorted(
            x["evidence_occurrence_id"]
            for x in link_map[cid]
            if x["kind"] == "contradicts"
        )

        if "accept" in decisions and "reject" in decisions:
            review_status = "review_conflict"
        elif "reject" in decisions:
            review_status = "rejected"
        elif "accept" in decisions:
            review_status = "accepted"
        elif "defer" in decisions:
            review_status = "deferred"
        else:
            review_status = "unreviewed"

        if review_status == "review_conflict":
            disposition = "unresolved_review_conflict"
        elif candidate_probe["probe_status"] == "symbolically_conflicted":
            disposition = "symbolically_conflicted_candidate"
        elif review_status == "rejected":
            disposition = "rejected_candidate"
        elif (
            review_status == "accepted"
            and linked_support
            and not linked_contra
            and candidate_probe["probe_status"]
            == "not_conflicted_under_admitted_rules"
        ):
            disposition = "supported_candidate_requires_explicit_admission"
        else:
            disposition = "unresolved_candidate"

        results.append(
            {
                "candidate_occurrence_id": cid,
                "symbolic_probe": candidate_probe,
                "review_status": review_status,
                "accepting_reviewers": accepts,
                "rejecting_reviewers": rejects,
                "deferring_reviewers": deferred,
                "supporting_evidence_occurrences": linked_support,
                "contradicting_evidence_occurrences": linked_contra,
                "disposition": disposition,
            }
        )

    result = {
        "schema_version": ADJUDICATION_SCHEMA,
        "proposal_id": proposal["proposal_id"],
        "proposal_sha256": meta["proposal_sha256"],
        "base_contract_sha256": meta["admission"].contract_digest,
        "base_graph_fingerprint": meta["admission"].graph_digest,
        "base_semantic_fingerprint": meta["semantic_snapshot"].semantic_fingerprint,
        "base_hypothesis_fingerprint": meta["semantic_snapshot"].hypothesis_fingerprint,
        "context_fingerprint": meta["context_fingerprint"],
        "review_digest": _review_digest(reviews),
        "joint_probe_status": probe["set_status"],
        "candidates": results,
        "authority": {
            "model_output_verified": False,
            "symbolic_probe_is_counterfactual": True,
            "joint_candidate_interactions_evaluated": True,
            "reviewer_independence_established": False,
            "runtime_truth_verified": False,
            "automatic_graph_mutation_permitted": False,
            "candidate_promoted_to_authoritative_fact": False,
        },
    }
    result["adjudication_sha256"] = sha(canonical(result))
    return result


def verify_adjudication(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    proposal: dict[str, Any],
    reviews: list[dict[str, Any]],
    claimed: dict[str, Any],
) -> bool:
    expected = adjudicate(contract, sources, proposal, reviews)
    if not isinstance(claimed, dict) or claimed != expected:
        raise ProposalError("Adjudication does not match exact source replay")
    return True
