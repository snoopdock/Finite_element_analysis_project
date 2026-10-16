"""G9.28: adversarial semantic vocabulary, normalization, and evolution tests."""
import copy
import hashlib

import pytest

from audit_engine.semantic_audit.ae24 import SCHEMA as C_SCHEMA
from audit_engine.semantic_audit.ae26 import (
    SCHEMA, DIFF_SCHEMA, snapshot, semantic_projection, verify_snapshot,
    diff_contracts, verify_diff, SemanticModelError, validate_vocabulary,
)


def fixture():
    raw = {"design": b"design-v1", "observation": b"observed-v1"}
    doc = {
        "schema_version": C_SCHEMA, "namespace": "portable/system",
        "sources": [{"id": k, "sha256": hashlib.sha256(v).hexdigest()} for k, v in raw.items()],
        "entities": [
            {"id": "producer", "kind": "Component", "source_id": "design"},
            {"id": "consumer", "kind": "Component", "source_id": "design"},
            {"id": "artifact", "kind": "Artifact", "source_id": "design"},
            {"id": "publish", "kind": "Action", "source_id": "design"},
        ],
        "assertions": [
            {"id": "p1", "subject": "producer", "predicate": "PRODUCES", "object": "artifact",
             "origin": "declared", "source_id": "design",
             "attributes": {"format": "json", "schema_id": "v1", "meaning_id": "bytes"}},
            {"id": "c1", "subject": "consumer", "predicate": "CONSUMES", "object": "artifact",
             "origin": "declared", "source_id": "design",
             "attributes": {"producer": "producer", "format": "json",
                            "schema_id": "v1", "meaning_id": "bytes"}},
        ],
    }
    return doc, raw


def test_snapshot_is_language_neutral():
    doc, raw = fixture()
    a = snapshot(doc, raw)
    doc2 = copy.deepcopy(doc)
    doc2["namespace"] = "rust/service-adapter"
    b = snapshot(doc2, raw)
    assert a.semantic_fingerprint == b.semantic_fingerprint
    assert a.contract_sha256 != b.contract_sha256


def test_snapshot_preserves_occurrences_but_semantic_fingerprint_ignores_duplicate_evidence():
    doc, raw = fixture()
    one = snapshot(doc, raw)
    doc["assertions"].append(dict(doc["assertions"][0], id="duplicate-observation"))
    two = snapshot(doc, raw)
    assert len(two.edges) == len(one.edges) + 1
    assert one.semantic_fingerprint == two.semantic_fingerprint


def test_occurrence_id_change_does_not_change_semantic_identity():
    doc, raw = fixture()
    a = snapshot(doc, raw)
    doc["assertions"][0]["id"] = "new-occurrence"
    b = snapshot(doc, raw)
    assert a.edges[0].occurrence_id != b.edges[0].occurrence_id
    assert a.semantic_fingerprint == b.semantic_fingerprint


def test_projection_is_detached():
    doc, raw = fixture()
    projected = semantic_projection(snapshot(doc, raw))
    original_id = projected["entities"][0]["id"]
    projected["entities"][0]["id"] = "mutated"
    assert semantic_projection(snapshot(doc, raw))["entities"][0]["id"] == original_id


def test_exact_snapshot_replay():
    doc, raw = fixture()
    value = snapshot(doc, raw)
    assert verify_snapshot(doc, raw, value)


def test_tampered_snapshot_rejected():
    doc, raw = fixture()
    value = snapshot(doc, raw)
    object.__setattr__(value, "semantic_fingerprint", "0" * 64)
    with pytest.raises(SemanticModelError, match="mismatch"):
        verify_snapshot(doc, raw, value)


def test_supported_relation_vocabulary_is_fixed():
    assert set(("PRODUCES", "CONSUMES", "PERFORMS", "FORBIDS",
                "DEPENDS_ON", "REQUIRES_CHECK", "HAS_CHECK")) == set(
        __import__("audit_engine.semantic_audit.ae26", fromlist=["RELATION_SEMANTICS"]).RELATION_SEMANTICS
    )


def test_unknown_semantic_predicate_is_not_coerced():
    doc, raw = fixture()
    doc["assertions"][0]["predicate"] = "ALMOST_PRODUCES"
    with pytest.raises(ValueError):
        validate_vocabulary(doc, raw)


def test_meaning_field_not_applicable_to_non_interface_relation():
    doc, raw = fixture()
    doc["entities"].append({"id": "action", "kind": "Action", "source_id": "design"})
    doc["assertions"].append({
        "id": "a1", "subject": "producer", "predicate": "PERFORMS", "object": "action",
        "origin": "declared", "source_id": "design", "attributes": {"meaning_id": "wrong-scope"},
    })
    with pytest.raises(ValueError, match="Meaning field|Only artifact interfaces"):
        validate_vocabulary(doc, raw)


def test_candidate_remains_visible_as_provenance():
    doc, raw = fixture()
    doc["assertions"].append({
        "id": "candidate1", "subject": "producer", "predicate": "PERFORMS",
        "object": "publish", "origin": "candidate", "source_id": "observation",
    })
    value = snapshot(doc, raw)
    assert any(e.origin == "candidate" for e in value.edges)


def test_added_relationship_is_classified():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"].append({
        "id": "dep1", "subject": "consumer", "predicate": "DEPENDS_ON",
        "object": "producer", "origin": "declared", "source_id": "design",
    })
    result = diff_contracts(before, raw, after, raw)
    assert result["schema_version"] == DIFF_SCHEMA
    assert any(x["change_type"] == "relationship_added" for x in result["changes"])


def test_removed_relationship_is_classified():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"].pop()
    result = diff_contracts(before, raw, after, raw)
    assert any(x["change_type"] == "relationship_removed" for x in result["changes"])


@pytest.mark.parametrize("field", ["format", "schema_id", "meaning_id"])
def test_interface_semantic_change_is_explicit(field):
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"][1]["attributes"][field] = "changed"
    result = diff_contracts(before, raw, after, raw)
    assert any(x["change_type"] == "interface_meaning_changed" for x in result["changes"])


def test_entity_kind_change_is_rejected_before_semantic_reasoning():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["entities"][0]["kind"] = "Artifact"
    with pytest.raises(ValueError):
        diff_contracts(before, raw, after, raw)


def test_source_tampering_invalidates_replay():
    before, raw = fixture()
    after = copy.deepcopy(before)
    result = diff_contracts(before, raw, after, raw)
    raw["design"] = b"tampered"
    with pytest.raises(ValueError):
        verify_diff(before, raw, after, raw, result)


def test_exact_diff_replay():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"][0]["attributes"]["meaning_id"] = "different"
    result = diff_contracts(before, raw, after, raw)
    assert verify_diff(before, raw, after, raw, result)


def test_rehashed_but_modified_diff_is_rejected():
    before, raw = fixture()
    after = copy.deepcopy(before)
    result = diff_contracts(before, raw, after, raw)
    result["status"] = "no_semantic_change_in_admitted_projection"
    result["report_sha256"] = hashlib.sha256(b"forged").hexdigest()
    with pytest.raises(SemanticModelError, match="does not match"):
        verify_diff(before, raw, after, raw, result)


def test_origin_change_is_not_silent():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"][0]["origin"] = "observed"
    result = diff_contracts(before, raw, after, raw)
    assert any(x["change_type"] == "relationship_removed" for x in result["changes"])
    assert any(x["change_type"] == "relationship_added" for x in result["changes"])


def test_no_change_has_stable_status():
    before, raw = fixture()
    result = diff_contracts(before, raw, copy.deepcopy(before), raw)
    assert result["changes"] == []
    assert result["status"] == "no_semantic_change_in_admitted_projection"


def test_multiple_occurrences_can_share_one_semantic_relation():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"].append(dict(after["assertions"][0], id="p2"))
    assert snapshot(before, raw).semantic_fingerprint == snapshot(after, raw).semantic_fingerprint


def test_different_meaning_ids_change_semantic_fingerprint():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"][0]["attributes"]["meaning_id"] = "different"
    assert snapshot(before, raw).semantic_fingerprint != snapshot(after, raw).semantic_fingerprint


def test_projection_contains_all_source_digests():
    doc, raw = fixture()
    p = semantic_projection(snapshot(doc, raw))
    assert {x["id"] for x in p["source_digests"]} == {"design", "observation"}


def test_policy_addition_is_visible_in_semantic_fingerprint():
    before, raw = fixture()
    before["policies"] = []
    after = copy.deepcopy(before)
    after["policies"] = [{"id": "p1", "kind": "acyclic_dependencies", "source_id": "design"}]
    assert snapshot(before, raw).semantic_fingerprint != snapshot(after, raw).semantic_fingerprint




def test_policy_local_id_does_not_change_semantic_fingerprint():
    before, raw = fixture()
    before["policies"] = [{"id": "p1", "kind": "acyclic_dependencies", "source_id": "design"}]
    after = copy.deepcopy(before)
    after["policies"][0]["id"] = "renamed"
    assert snapshot(before, raw).semantic_fingerprint == snapshot(after, raw).semantic_fingerprint


def test_coverage_change_is_visible_in_semantic_fingerprint():
    before, raw = fixture()
    before["coverage"] = [{"component": "consumer", "relation": "HAS_CHECK",
                           "source_id": "design", "complete": False}]
    after = copy.deepcopy(before)
    after["coverage"][0]["complete"] = True
    assert snapshot(before, raw).semantic_fingerprint != snapshot(after, raw).semantic_fingerprint


def test_semantic_fingerprint_is_deterministic_under_assertion_order():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"].reverse()
    assert snapshot(before, raw).semantic_fingerprint == snapshot(after, raw).semantic_fingerprint


def test_source_revision_changes_contract_identity_but_not_truth_claim():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after_raw = dict(raw)
    after_raw["design"] = b"design-v2"
    after["sources"] = [{"id": k, "sha256": hashlib.sha256(v).hexdigest()} for k, v in after_raw.items()]
    result = diff_contracts(before, raw, after, after_raw)
    assert result["before"]["contract_sha256"] != result["after"]["contract_sha256"]
    assert result["authority"]["semantic_truth_verified"] is False


def test_large_change_set_fails_closed():
    before, raw = fixture()
    after = copy.deepcopy(before)
    for i in range(12001):
        # AE-24's own assertion budget is deliberately lower than this test;
        # either layer failing closed is acceptable.
        after["assertions"].append({
            "id": f"d{i}", "subject": "consumer", "predicate": "DEPENDS_ON",
            "object": "producer", "origin": "declared", "source_id": "design",
        })
    with pytest.raises(ValueError):
        diff_contracts(before, raw, after, raw)
