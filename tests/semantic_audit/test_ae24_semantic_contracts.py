"""AE-24: source-bound, language-neutral graph admission acceptance controls."""
import copy
import hashlib

import pytest

from audit_engine.semantic_audit.ae24 import (
    SCHEMA, ContractError, admit, verify_admission, to_graph_assertions, canonical,
)


def fixture():
    data = {'design': b'architecture-contract/v1: pipeline roles',
            'observation': b'workflow step reads a declared artifact'}
    sources = [{'id': k, 'sha256': hashlib.sha256(v).hexdigest()} for k,v in data.items()]
    record = dict(schema_version=SCHEMA, namespace='system/portable', sources=sources,
                  entities=[{'id': 'producer', 'kind': 'Component', 'source_id': 'design'},
                            {'id': 'consumer', 'kind': 'Component', 'source_id': 'design'},
                            {'id': 'bundle', 'kind': 'Artifact', 'source_id': 'design'},
                            {'id': 'publish', 'kind': 'Action', 'source_id': 'design'},
                            {'id': 'audit', 'kind': 'Check', 'source_id': 'design'}],
                  assertions=[
                      dict(id='e1', subject='producer', predicate='PRODUCES', object='bundle',
                           origin='declared', source_id='design',
                           attributes={'format':'json', 'schema_id':'bundle/v1', 'meaning_id':'digest_of_bytes'}),
                      dict(id='e2', subject='consumer', predicate='CONSUMES', object='bundle',
                           origin='observed', source_id='observation',
                           attributes={'producer':'producer', 'format':'json', 'schema_id':'bundle/v1', 'meaning_id':'digest_of_bytes'}),
                      dict(id='e3', subject='consumer', predicate='REQUIRES_CHECK', object='audit',
                           origin='declared', source_id='design'),
                  ], coverage=[dict(component='consumer', relation='HAS_CHECK', complete=False, source_id='observation')],
                  policies=[dict(id='p1', kind='acyclic_dependencies', source_id='design')])
    return record, data


def test_admitted_evidence_graph_integrity():
    doc, evidence = fixture()
    value = admit(doc, evidence)
    assert value.status.endswith('not_behavioral_verification')
    assert value.proposed_count == 0
    assert len(value.graph.edges) == 3
    assert verify_admission(doc, evidence, value)
    assert set(r['metadata']['ae13_occurrence_id'] for r in to_graph_assertions(value)) == {'e1', 'e2', 'e3'}


def test_graph_preserves_parallel_occurrences():
    doc, evidence = fixture()
    another = dict(doc['assertions'][0], id='e4')
    doc['assertions'].append(another)
    value = admit(doc, evidence)
    assert len(value.graph.edges) == 4
    assert len({e.metadata['ae13_occurrence_id'] for e in value.graph.edges}) == 4
    assert value.graph.edges[0].relation_type == value.graph.edges[-1].relation_type


def test_admission_does_not_mutate_caller_inputs():
    doc, evidence = fixture()
    frozen = copy.deepcopy(doc)
    admit(doc, evidence)
    assert doc == frozen


def test_mutated_graph_cannot_pass_independent_replay():
    doc, evidence = fixture()
    val = admit(doc, evidence)
    val.graph.edges[0].attributes['format'] = 'yaml'
    with pytest.raises(ContractError, match='replay'):
        verify_admission(doc, evidence, val)


def test_rehashed_but_replaced_observation_rejected():
    doc, evidence = fixture()
    val = admit(doc, evidence)
    val.graph.edges[0].metadata['origin'] = 'candidate'
    from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
    object.__setattr__(val, 'graph_digest', graph_fingerprint(val.graph))
    with pytest.raises(ContractError, match='replay'):
        verify_admission(doc, evidence, val)


def test_mutated_evidence_detected():
    doc, evidence = fixture()
    evidence['design'] = b'changed-contract'
    with pytest.raises(ContractError, match='Evidence byte mismatch'):
        admit(doc, evidence)


def test_missing_evidence_not_clean():
    doc, evidence = fixture()
    evidence.pop('observation')
    with pytest.raises(ContractError, match='Missing exact evidence'):
        admit(doc, evidence)


def test_extra_evidence_rejected():
    doc, evidence = fixture()
    evidence['surplus'] = b'x'
    with pytest.raises(ContractError, match='Unexpected'):
        admit(doc, evidence)


@pytest.mark.parametrize('field,value', [
    ('schema_version','bad/v1'), ('namespace', ''), ('namespace',' x'),
])
def test_bad_envelope_rejected(field, value):
    doc, evidence = fixture()
    doc[field] = value
    with pytest.raises(ContractError):
        admit(doc, evidence)


@pytest.mark.parametrize('change', [
    {'id':'e2'}, {'subject':'bundle'}, {'object':'consumer'},
    {'predicate':'UNKNOWN'}, {'origin':'automatically_verified'},
    {'source_id':'forged'}, {'attributes':{'authoritative': True}},
])
def test_bad_assertion_rejected(change):
    doc, evidence = fixture()
    doc['assertions'][0].update(change)
    with pytest.raises(ContractError):
        admit(doc, evidence)


def test_duplicate_assertion_rejected():
    doc, evidence = fixture()
    doc['assertions'].append(dict(doc['assertions'][0]))
    with pytest.raises(ContractError, match='Duplicate'):
        admit(doc, evidence)


def test_unsupported_entity_type_rejected():
    doc, evidence = fixture()
    doc['entities'][0]['kind'] = 'UnknownSystemConcept'
    with pytest.raises(ContractError):
        admit(doc, evidence)


def test_declared_coverage_requires_witness():
    doc, evidence = fixture()
    doc['coverage'][0]['source_id'] = 'made-up'
    with pytest.raises(ContractError):
        admit(doc, evidence)


def test_no_spontaneous_coverage_assumption():
    doc, evidence = fixture()
    doc.pop('coverage')
    assert admit(doc, evidence).graph_digest


def test_duplicate_coverage_rejected():
    doc, evidence = fixture()
    doc['coverage'].append(dict(doc['coverage'][0]))
    with pytest.raises(ContractError):
        admit(doc, evidence)


def test_policy_must_be_explicit_and_source_bound():
    doc, evidence = fixture()
    doc['policies'][0]['source_id'] = 'not-available'
    with pytest.raises(ContractError):
        admit(doc, evidence)


def test_proposed_neural_relationship_is_quarantined():
    doc, evidence = fixture()
    doc['assertions'][0]['origin'] = 'candidate'
    val = admit(doc, evidence)
    assert val.proposed_count == 1
    assert len(to_graph_assertions(val)) == 2
    assert len(to_graph_assertions(val, include_candidates=True)) == 3


def test_source_revision_changes_graph_and_contract_identity():
    doc, evidence = fixture()
    initial = admit(doc, evidence)
    evidence['design'] = b'architecture-contract/v2: different meaning'
    doc['sources'][0 if doc['sources'][0]['id']=='design' else 1]['sha256'] = hashlib.sha256(evidence['design']).hexdigest()
    revised = admit(doc, evidence)
    assert revised.contract_digest != initial.contract_digest
    # Graph relationships stay structurally equal but the source-bound admission does not.
    assert revised.source_digests != initial.source_digests


def test_contract_boundaries_are_language_neutral():
    doc, evidence = fixture()
    python_snapshot = admit(doc, evidence)
    doc['namespace'] = 'service/workflow'
    workflow_snapshot = admit(doc, evidence)
    assert [x['predicate'] for x in to_graph_assertions(python_snapshot)] == [x['predicate'] for x in to_graph_assertions(workflow_snapshot)]


def test_input_budget_enforced():
    doc, evidence = fixture()
    doc['entities'] = [{'id':f'e{i}', 'kind':'Component', 'source_id':'design'} for i in range(2001)]
    with pytest.raises(ContractError, match='budget'):
        admit(doc, evidence)


def test_noncanonical_values_rejected():
    doc, evidence = fixture()
    doc['unexpected'] = float('nan')
    with pytest.raises(ContractError):
        admit(doc, evidence)


def test_digest_canonical_sorted_order():
    assert canonical({'b':1,'a':2}) == b'{"a":2,"b":1}\n'


def test_producer_occurrence_requires_explicit_producer():
    doc, evidence = fixture()
    doc['assertions'][1]['attributes'].pop('producer')
    doc['assertions'][1]['attributes']['producer_occurrence'] = 'e1'
    with pytest.raises(ContractError, match='requires'):
        admit(doc, evidence)
