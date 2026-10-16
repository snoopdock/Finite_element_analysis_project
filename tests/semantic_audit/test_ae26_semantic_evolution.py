"""G9.28 corrective AE-26 tests.

These tests intentionally exercise the semantic identity boundary, evolution
completeness, candidate quarantine, producer binding, deterministic diffing,
and source-replay verification.  They do not execute target source programs.
"""
import copy
import hashlib
import json

import pytest

from audit_engine.semantic_audit.ae24 import SCHEMA as C_SCHEMA, canonical
from audit_engine.semantic_audit.ae26 import (
    SCHEMA,
    DIFF_SCHEMA,
    VOCABULARY_DIGEST,
    RELATION_SEMANTICS,
    snapshot,
    semantic_projection,
    verify_snapshot,
    verify_projection,
    diff_contracts,
    verify_diff,
    SemanticModelError,
    validate_vocabulary,
)


def fixture():
    raw = {"design": b"design-v1", "observation": b"observed-v1"}
    doc = {
        "schema_version": C_SCHEMA,
        "namespace": "portable/system",
        "sources": [
            {"id": key, "sha256": hashlib.sha256(value).hexdigest()}
            for key, value in raw.items()
        ],
        "entities": [
            {"id": "producer", "kind": "Component", "source_id": "design"},
            {"id": "consumer", "kind": "Component", "source_id": "design"},
            {"id": "artifact", "kind": "Artifact", "source_id": "design"},
            {"id": "publish", "kind": "Action", "source_id": "design"},
        ],
        "assertions": [
            {
                "id": "p1",
                "subject": "producer",
                "predicate": "PRODUCES",
                "object": "artifact",
                "origin": "declared",
                "source_id": "design",
                "attributes": {
                    "format": "json",
                    "schema_id": "v1",
                    "meaning_id": "bytes",
                },
            },
            {
                "id": "c1",
                "subject": "consumer",
                "predicate": "CONSUMES",
                "object": "artifact",
                "origin": "declared",
                "source_id": "design",
                "attributes": {
                    "producer": "producer",
                    "format": "json",
                    "schema_id": "v1",
                    "meaning_id": "bytes",
                },
            },
        ],
    }
    return doc, raw


def add(
    doc,
    aid,
    subject,
    relation,
    obj,
    origin="declared",
    source_id="design",
    attrs=None,
):
    item = {
        "id": aid,
        "subject": subject,
        "predicate": relation,
        "object": obj,
        "origin": origin,
        "source_id": source_id,
    }
    if attrs is not None:
        item["attributes"] = attrs
    doc["assertions"].append(item)


def relation_records(projection):
    return projection["semantic_facts"]


def hypothesis_records(projection):
    return projection["hypotheses"]


def assert_semantic_diff_equivalent(first, second):
    """Compare semantic evolution while preserving exact-contract provenance.

    Reordering assertions may legitimately change ``contract_sha256`` because
    that digest identifies the exact admitted contract bytes.  The semantic
    evolution result must nevertheless remain identical.
    """
    assert first["schema_version"] == second["schema_version"]
    assert first["vocabulary_digest"] == second["vocabulary_digest"]
    assert first["before"]["semantic_fingerprint"] == second["before"]["semantic_fingerprint"]
    assert first["before"]["hypothesis_fingerprint"] == second["before"]["hypothesis_fingerprint"]
    assert first["after"]["semantic_fingerprint"] == second["after"]["semantic_fingerprint"]
    assert first["after"]["hypothesis_fingerprint"] == second["after"]["hypothesis_fingerprint"]
    assert first["changes"] == second["changes"]
    assert first["status"] == second["status"]
    assert first["authority"] == second["authority"]
    assert first["semantic_diff_fingerprint"] == second["semantic_diff_fingerprint"]


def test_snapshot_is_language_neutral():
    doc, raw = fixture()
    first = snapshot(doc, raw)
    doc2 = copy.deepcopy(doc)
    doc2["namespace"] = "rust/service-adapter"
    second = snapshot(doc2, raw)
    assert first.semantic_fingerprint == second.semantic_fingerprint
    assert first.contract_sha256 != second.contract_sha256


def test_snapshot_schema_and_vocabulary_are_explicit():
    doc, raw = fixture()
    value = snapshot(doc, raw)
    assert value.schema_version == SCHEMA
    assert value.vocabulary_digest == VOCABULARY_DIGEST
    assert value.vocabulary_digest == hashlib.sha256(
        canonical(
            {
                "concept_types": sorted(
                    {"Component", "Artifact", "Action", "Check", "Meaning", "Contract", "Policy"}
                ),
                "relations": RELATION_SEMANTICS,
            }
        )
    ).hexdigest()


def test_occurrence_id_change_does_not_change_semantic_identity():
    doc, raw = fixture()
    first = snapshot(doc, raw)
    first_producer = next(
        edge for edge in first.edges if edge.occurrence_id == "p1"
    )
    doc["assertions"][0]["id"] = "new-occurrence"
    second = snapshot(doc, raw)
    second_producer = next(
        edge for edge in second.edges if edge.subject == "producer"
    )
    assert first_producer.occurrence_id != second_producer.occurrence_id
    assert first_producer.semantic_id == second_producer.semantic_id
    assert first.semantic_fingerprint == second.semantic_fingerprint


def test_duplicate_occurrences_share_one_semantic_fact():
    doc, raw = fixture()
    one = semantic_projection(snapshot(doc, raw))
    doc["assertions"].append(dict(doc["assertions"][0], id="duplicate-observation"))
    two = semantic_projection(snapshot(doc, raw))
    assert len(two["edges"]) == len(one["edges"]) + 1
    assert len(two["semantic_facts"]) == len(one["semantic_facts"])
    assert one["semantic_facts"] == two["semantic_facts"]


def test_semantic_id_excludes_source_and_occurrence_identity():
    doc, raw = fixture()
    one = snapshot(doc, raw)
    doc["assertions"][0]["id"] = "p2"
    doc["assertions"][0]["source_id"] = "observation"
    two = snapshot(doc, raw)
    a = next(x for x in one.edges if x.subject == "producer")
    b = next(x for x in two.edges if x.subject == "producer")
    assert a.semantic_id == b.semantic_id
    assert one.semantic_fingerprint == two.semantic_fingerprint


def test_projection_is_detached_at_nested_levels():
    doc, raw = fixture()
    projected = semantic_projection(snapshot(doc, raw))
    projected["semantic_facts"][0]["meaning"]["format"] = "mutated"
    projected["edges"][0]["meaning"][0]["value"] = "mutated"
    projected["coverage"].append({"component": "consumer", "relation": "HAS_CHECK", "complete": True})
    fresh = semantic_projection(snapshot(doc, raw))
    assert fresh["semantic_facts"][0]["meaning"]["format"] == "json"
    assert fresh["coverage"] == []


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


def test_projection_exact_replay():
    doc, raw = fixture()
    projection = semantic_projection(snapshot(doc, raw))
    result = verify_projection(doc, raw, projection)
    assert result["status"] == "source_replayed"


def test_tampered_projection_rejected():
    doc, raw = fixture()
    projection = semantic_projection(snapshot(doc, raw))
    projection["semantic_fingerprint"] = "0" * 64
    with pytest.raises(SemanticModelError, match="projection"):
        verify_projection(doc, raw, projection)


def test_supported_relation_vocabulary_is_fixed():
    assert set(
        ("PRODUCES", "CONSUMES", "PERFORMS", "FORBIDS",
         "DEPENDS_ON", "REQUIRES_CHECK", "HAS_CHECK")
    ) == set(RELATION_SEMANTICS)


def test_unknown_semantic_predicate_is_not_coerced():
    doc, raw = fixture()
    doc["assertions"][0]["predicate"] = "ALMOST_PRODUCES"
    with pytest.raises(ValueError):
        validate_vocabulary(doc, raw)


def test_meaning_field_not_applicable_to_non_interface_relation():
    doc, raw = fixture()
    doc["entities"].append(
        {"id": "action", "kind": "Action", "source_id": "design"}
    )
    add(
        doc,
        "a1",
        "producer",
        "PERFORMS",
        "action",
        attrs={"meaning_id": "wrong-scope"},
    )
    with pytest.raises(ValueError, match="Meaning field|Only artifact interfaces"):
        validate_vocabulary(doc, raw)


def test_candidate_remains_visible_as_provenance():
    doc, raw = fixture()
    add(
        doc,
        "candidate1",
        "producer",
        "PERFORMS",
        "publish",
        origin="candidate",
        source_id="observation",
    )
    value = snapshot(doc, raw)
    assert any(edge.origin == "candidate" for edge in value.edges)


def test_candidate_does_not_change_authoritative_semantic_fingerprint():
    doc, raw = fixture()
    before = snapshot(doc, raw)
    add(
        doc,
        "candidate1",
        "producer",
        "PERFORMS",
        "publish",
        origin="candidate",
        source_id="observation",
    )
    after = snapshot(doc, raw)
    assert before.semantic_fingerprint == after.semantic_fingerprint
    assert before.hypothesis_fingerprint != after.hypothesis_fingerprint


def test_candidate_has_separate_hypothesis_projection():
    doc, raw = fixture()
    add(
        doc,
        "candidate1",
        "producer",
        "PERFORMS",
        "publish",
        origin="candidate",
        source_id="observation",
    )
    projected = semantic_projection(snapshot(doc, raw))
    assert all(row["origin"] != "candidate" for row in relation_records(projected))
    assert len(hypothesis_records(projected)) == 1
    assert hypothesis_records(projected)[0]["origin"] == "candidate"


def test_candidate_occurrence_id_does_not_change_hypothesis_identity():
    doc, raw = fixture()
    add(
        doc,
        "candidate1",
        "producer",
        "PERFORMS",
        "publish",
        origin="candidate",
        source_id="observation",
    )
    first = snapshot(doc, raw)
    doc["assertions"][-1]["id"] = "candidate2"
    second = snapshot(doc, raw)
    assert first.hypothesis_fingerprint == second.hypothesis_fingerprint
    assert first.semantic_fingerprint == second.semantic_fingerprint


def test_added_relationship_is_classified():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(after, "dep1", "consumer", "DEPENDS_ON", "producer")
    result = diff_contracts(before, raw, after, raw)
    assert result["schema_version"] == DIFF_SCHEMA
    assert any(
        x["change_type"] == "relationship_added"
        and x["predicate"] == "DEPENDS_ON"
        for x in result["changes"]
    )


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
    assert any(
        x["change_type"] == "interface_meaning_changed"
        and field in x["before"]
        and x["before"][field] != x["after"][field]
        for x in result["changes"]
    )


def test_producer_binding_is_semantic_when_producer_entity_changes():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["entities"].append(
        {"id": "producer2", "kind": "Component", "source_id": "design"}
    )
    add(
        after,
        "p2",
        "producer2",
        "PRODUCES",
        "artifact",
        attrs={"format": "json", "schema_id": "v1", "meaning_id": "bytes"},
    )
    after["assertions"][1]["attributes"]["producer"] = "producer2"
    first = snapshot(before, raw)
    second = snapshot(after, raw)
    assert first.semantic_fingerprint != second.semantic_fingerprint
    result = diff_contracts(before, raw, after, raw)
    assert any(x["change_type"] == "interface_binding_changed" for x in result["changes"])


def test_producer_occurrence_selector_is_provenance_not_semantic_identity():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(
        after,
        "p2",
        "producer",
        "PRODUCES",
        "artifact",
        attrs={"format": "json", "schema_id": "v1", "meaning_id": "bytes"},
    )
    after["assertions"][1]["attributes"]["producer_occurrence"] = "p2"
    first = snapshot(before, raw)
    second = snapshot(after, raw)
    first_consumer = next(e for e in first.edges if e.occurrence_id == "c1")
    second_consumer = next(e for e in second.edges if e.occurrence_id == "c1")
    assert first_consumer.semantic_id == second_consumer.semantic_id
    assert first.semantic_fingerprint == second.semantic_fingerprint


def test_producer_occurrence_selector_changes_semantics_when_contract_changes():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(
        after,
        "p2",
        "producer",
        "PRODUCES",
        "artifact",
        attrs={"format": "yaml", "schema_id": "v2", "meaning_id": "other"},
    )
    after["assertions"][1]["attributes"]["producer_occurrence"] = "p2"
    first = snapshot(before, raw)
    second = snapshot(after, raw)
    assert first.semantic_fingerprint != second.semantic_fingerprint
    consumer = next(e for e in second.edges if e.occurrence_id == "c1")
    assert json.loads(consumer.binding)["producer_contract"]["meaning_id"] == "other"


def test_ambiguous_producer_binding_is_explicitly_represented():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(
        after,
        "p2",
        "producer",
        "PRODUCES",
        "artifact",
        attrs={"format": "yaml", "schema_id": "v2", "meaning_id": "other"},
    )
    after["assertions"][1]["attributes"].pop("producer_occurrence", None)
    second = snapshot(after, raw)
    consumer = next(e for e in second.edges if e.occurrence_id == "c1")
    binding = json.loads(consumer.binding)
    assert binding["resolution"] == "ambiguous"
    assert len(binding["producer_contracts"]) == 2


def test_unresolved_producer_occurrence_is_fail_closed():
    doc, raw = fixture()
    doc["assertions"][1]["attributes"]["producer_occurrence"] = "does-not-exist"
    value = snapshot(doc, raw)
    consumer = next(e for e in value.edges if e.occurrence_id == "c1")
    assert json.loads(consumer.binding)["resolution"] == "unresolved"


def test_candidate_producer_is_not_used_as_authoritative_binding():
    doc, raw = fixture()
    doc["assertions"][0]["origin"] = "candidate"
    doc["assertions"][1]["attributes"]["producer_occurrence"] = "p1"
    value = snapshot(doc, raw)
    consumer = next(e for e in value.edges if e.occurrence_id == "c1")
    assert json.loads(consumer.binding)["resolution"] == "candidate_only"


def test_entity_kind_change_is_rejected_when_it_breaks_typed_relation():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["entities"][0]["kind"] = "Artifact"
    with pytest.raises(ValueError):
        diff_contracts(before, raw, after, raw)


def test_unused_entity_kind_change_is_explicit():
    before, raw = fixture()
    before["entities"].append(
        {"id": "unused", "kind": "Component", "source_id": "design"}
    )
    after = copy.deepcopy(before)
    after["entities"][-1]["kind"] = "Artifact"
    result = diff_contracts(before, raw, after, raw)
    assert any(
        x["change_type"] == "entity_semantic_kind_changed"
        and x["entity_id"] == "unused"
        for x in result["changes"]
    )


def test_entity_addition_and_removal_are_classified():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["entities"].append(
        {"id": "unused", "kind": "Component", "source_id": "design"}
    )
    added = diff_contracts(before, raw, after, raw)
    assert any(x["change_type"] == "entity_added" for x in added["changes"])
    removed = diff_contracts(after, raw, before, raw)
    assert any(x["change_type"] == "entity_removed" for x in removed["changes"])


def test_source_tampering_invalidates_snapshot_replay():
    before, raw = fixture()
    value = snapshot(before, raw)
    raw["design"] = b"tampered"
    with pytest.raises(ValueError):
        verify_snapshot(before, raw, value)


def test_source_tampering_invalidates_diff_replay():
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
    result["status"] = "semantic_change_detected"
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


def test_policy_addition_is_visible_in_semantic_fingerprint():
    before, raw = fixture()
    before["policies"] = []
    after = copy.deepcopy(before)
    after["policies"] = [
        {"id": "p1", "kind": "acyclic_dependencies", "source_id": "design"}
    ]
    assert snapshot(before, raw).semantic_fingerprint != snapshot(after, raw).semantic_fingerprint


def test_policy_local_id_does_not_change_semantic_fingerprint():
    before, raw = fixture()
    before["policies"] = [
        {"id": "p1", "kind": "acyclic_dependencies", "source_id": "design"}
    ]
    after = copy.deepcopy(before)
    after["policies"][0]["id"] = "renamed"
    assert snapshot(before, raw).semantic_fingerprint == snapshot(after, raw).semantic_fingerprint


def test_policy_addition_is_explicit_in_diff():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["policies"] = [
        {"id": "p1", "kind": "acyclic_dependencies", "source_id": "design"}
    ]
    result = diff_contracts(before, raw, after, raw)
    assert any(x["change_type"] == "policy_added" for x in result["changes"])
    assert result["status"] == "semantic_change_detected"


def test_policy_removal_is_explicit_in_diff():
    before, raw = fixture()
    before["policies"] = [
        {"id": "p1", "kind": "acyclic_dependencies", "source_id": "design"}
    ]
    after = copy.deepcopy(before)
    after["policies"] = []
    result = diff_contracts(before, raw, after, raw)
    assert any(x["change_type"] == "policy_removed" for x in result["changes"])


def test_coverage_change_is_visible_in_semantic_fingerprint():
    before, raw = fixture()
    before["coverage"] = [
        {
            "component": "consumer",
            "relation": "HAS_CHECK",
            "source_id": "design",
            "complete": False,
        }
    ]
    after = copy.deepcopy(before)
    after["coverage"][0]["complete"] = True
    assert snapshot(before, raw).semantic_fingerprint != snapshot(after, raw).semantic_fingerprint


def test_coverage_source_identity_does_not_change_semantic_fingerprint():
    before, raw = fixture()
    before["coverage"] = [
        {
            "component": "consumer",
            "relation": "HAS_CHECK",
            "source_id": "design",
            "complete": False,
        }
    ]
    after = copy.deepcopy(before)
    after["coverage"][0]["source_id"] = "observation"
    assert snapshot(before, raw).semantic_fingerprint == snapshot(after, raw).semantic_fingerprint


def test_coverage_completeness_change_is_explicit():
    before, raw = fixture()
    before["coverage"] = [
        {
            "component": "consumer",
            "relation": "HAS_CHECK",
            "source_id": "design",
            "complete": False,
        }
    ]
    after = copy.deepcopy(before)
    after["coverage"][0]["complete"] = True
    result = diff_contracts(before, raw, after, raw)
    assert any(
        x["change_type"] == "coverage_completeness_changed"
        for x in result["changes"]
    )


def test_semantic_fingerprint_is_deterministic_under_assertion_order():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after["assertions"].reverse()
    assert snapshot(before, raw).semantic_fingerprint == snapshot(after, raw).semantic_fingerprint


def test_semantic_diff_is_deterministic_under_assertion_order():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(
        after,
        "p2",
        "producer",
        "PRODUCES",
        "artifact",
        attrs={"format": "yaml", "schema_id": "v2", "meaning_id": "other"},
    )
    after["assertions"].reverse()
    one = diff_contracts(before, raw, after, raw)
    after["assertions"].reverse()
    two = diff_contracts(before, raw, after, raw)
    assert_semantic_diff_equivalent(one, two)
    assert one["after"]["contract_sha256"] != two["after"]["contract_sha256"]
    assert one["report_sha256"] != two["report_sha256"]


def test_parallel_interface_variants_do_not_overwrite_each_other():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(
        after,
        "p2",
        "producer",
        "PRODUCES",
        "artifact",
        attrs={"format": "yaml", "schema_id": "v2", "meaning_id": "other"},
    )
    first = diff_contracts(before, raw, after, raw)
    after["assertions"][-1], after["assertions"][-2] = (
        after["assertions"][-2],
        after["assertions"][-1],
    )
    second = diff_contracts(before, raw, after, raw)
    assert_semantic_diff_equivalent(first, second)
    assert first["after"]["contract_sha256"] != second["after"]["contract_sha256"]
    assert first["report_sha256"] != second["report_sha256"]


def test_same_slot_variant_meaning_change_is_order_independent():
    before, raw = fixture()
    before["assertions"][0]["attributes"]["meaning_id"] = "meaning-a"
    add(
        before,
        "p2",
        "producer",
        "PRODUCES",
        "artifact",
        attrs={"format": "json", "schema_id": "v1", "meaning_id": "meaning-b"},
    )
    after = copy.deepcopy(before)
    after["assertions"][0]["attributes"]["meaning_id"] = "meaning-c"
    one = diff_contracts(before, raw, after, raw)
    after["assertions"].reverse()
    two = diff_contracts(before, raw, after, raw)
    assert_semantic_diff_equivalent(one, two)
    assert one["after"]["contract_sha256"] != two["after"]["contract_sha256"]
    assert one["report_sha256"] != two["report_sha256"]
    assert any(
        x["change_type"] == "interface_meaning_changed"
        for x in one["changes"]
    )


def test_source_revision_changes_contract_identity_but_not_semantic_truth_state():
    before, raw = fixture()
    after = copy.deepcopy(before)
    after_raw = dict(raw)
    after_raw["design"] = b"design-v2"
    after["sources"] = [
        {"id": key, "sha256": hashlib.sha256(value).hexdigest()}
        for key, value in after_raw.items()
    ]
    result = diff_contracts(before, raw, after, after_raw)
    assert result["before"]["contract_sha256"] != result["after"]["contract_sha256"]
    assert result["before"]["semantic_fingerprint"] == result["after"]["semantic_fingerprint"]
    assert result["authority"]["semantic_truth_verified"] is False


def test_policy_and_coverage_order_is_deterministic():
    before, raw = fixture()
    before["policies"] = [
        {"id": "p1", "kind": "acyclic_dependencies", "source_id": "design"}
    ]
    before["coverage"] = [
        {
            "component": "consumer",
            "relation": "HAS_CHECK",
            "source_id": "design",
            "complete": False,
        }
    ]
    after = copy.deepcopy(before)
    after["assertions"].reverse()
    result1 = diff_contracts(before, raw, after, raw)
    result2 = diff_contracts(before, raw, copy.deepcopy(after), dict(raw))
    assert result1 == result2


def test_hypothesis_only_change_has_distinct_status():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(
        after,
        "candidate1",
        "producer",
        "PERFORMS",
        "publish",
        origin="candidate",
        source_id="observation",
    )
    result = diff_contracts(before, raw, after, raw)
    assert result["status"] == "hypothesis_change_detected"
    assert result["before"]["semantic_fingerprint"] == result["after"]["semantic_fingerprint"]
    assert any(x["change_type"] == "hypothesis_added" for x in result["changes"])


def test_semantic_and_hypothesis_changes_have_combined_status():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(after, "dep1", "consumer", "DEPENDS_ON", "producer")
    add(
        after,
        "candidate1",
        "producer",
        "PERFORMS",
        "publish",
        origin="candidate",
        source_id="observation",
    )
    result = diff_contracts(before, raw, after, raw)
    assert result["status"] == "semantic_and_hypothesis_change_detected"


def test_large_change_set_fails_closed():
    before, raw = fixture()
    after = copy.deepcopy(before)
    for index in range(12001):
        add(
            after,
            f"d{index}",
            "consumer",
            "DEPENDS_ON",
            "producer",
        )
    with pytest.raises(ValueError):
        diff_contracts(before, raw, after, raw)


def test_semantic_diff_fingerprint_tampering_is_rejected():
    before, raw = fixture()
    after = copy.deepcopy(before)
    add(after, "dep1", "consumer", "DEPENDS_ON", "producer")
    claimed = diff_contracts(before, raw, after, raw)
    tampered = copy.deepcopy(claimed)
    tampered["semantic_diff_fingerprint"] = "0" * 64
    with pytest.raises(SemanticModelError, match="exact source replay"):
        verify_diff(before, raw, after, raw, tampered)


def test_cli_snapshot_and_verify_round_trip(tmp_path, capsys):
    from audit_engine.semantic_audit.ae24 import canonical
    from audit_engine.semantic_audit.ae26.__main__ import main

    doc, raw = fixture()
    folder = tmp_path / "evidence"
    folder.mkdir()
    for source_id, content in raw.items():
        (folder / source_id).write_bytes(content)
    contract_path = tmp_path / "CONTRACT.json"
    contract_path.write_bytes(canonical(doc))

    assert main([
        "snapshot",
        "--contract", str(contract_path),
        "--evidence-dir", str(folder),
    ]) == 0
    projection = json.loads(capsys.readouterr().out)
    snapshot_path = tmp_path / "SNAPSHOT.json"
    snapshot_path.write_bytes(canonical(projection))

    assert main([
        "verify-snapshot",
        "--contract", str(contract_path),
        "--evidence-dir", str(folder),
        "--snapshot", str(snapshot_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "source_replayed"


def test_cli_diff_and_verify_round_trip(tmp_path, capsys):
    from audit_engine.semantic_audit.ae24 import canonical
    from audit_engine.semantic_audit.ae26.__main__ import main

    before, raw = fixture()
    after = copy.deepcopy(before)
    add(after, "dep1", "consumer", "DEPENDS_ON", "producer")

    before_dir = tmp_path / "before-evidence"
    after_dir = tmp_path / "after-evidence"
    before_dir.mkdir()
    after_dir.mkdir()
    for source_id, content in raw.items():
        (before_dir / source_id).write_bytes(content)
        (after_dir / source_id).write_bytes(content)
    before_path = tmp_path / "BEFORE.json"
    after_path = tmp_path / "AFTER.json"
    before_path.write_bytes(canonical(before))
    after_path.write_bytes(canonical(after))

    assert main([
        "diff",
        "--before-contract", str(before_path),
        "--before-evidence-dir", str(before_dir),
        "--after-contract", str(after_path),
        "--after-evidence-dir", str(after_dir),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    report_path = tmp_path / "DIFF.json"
    report_path.write_bytes(canonical(report))

    assert main([
        "verify-diff",
        "--before-contract", str(before_path),
        "--before-evidence-dir", str(before_dir),
        "--after-contract", str(after_path),
        "--after-evidence-dir", str(after_dir),
        "--report", str(report_path),
    ]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["status"] == "source_replayed"
    assert verified["semantic_diff_fingerprint"] == report["semantic_diff_fingerprint"]


def test_cli_rejects_noncanonical_claim(tmp_path):
    from audit_engine.semantic_audit.ae24 import canonical
    from audit_engine.semantic_audit.ae26.__main__ import main

    doc, raw = fixture()
    folder = tmp_path / "evidence"
    folder.mkdir()
    for source_id, content in raw.items():
        (folder / source_id).write_bytes(content)
    contract_path = tmp_path / "CONTRACT.json"
    contract_path.write_bytes(canonical(doc))
    bad = tmp_path / "bad.json"
    bad.write_bytes(canonical({"semantic_fingerprint": "0" * 64}).rstrip(b"\n"))
    with pytest.raises(ValueError, match="canonical"):
        main([
            "verify-snapshot",
            "--contract", str(contract_path),
            "--evidence-dir", str(folder),
            "--snapshot", str(bad),
        ])
