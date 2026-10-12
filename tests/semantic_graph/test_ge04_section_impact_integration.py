"""Integration and adversarial acceptance tests for GE-04 review planning."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from audit_engine.semantic_audit.graph.section_impact_integration import (
    GE04Error, _write_new_report, plan
)
from audit_engine.semantic_audit.graph.persistent_domain_state import GraphStoreError
from audit_engine.semantic_audit.graph.native_impact_analysis import GE03Error
from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph

ROOT = Path(__file__).resolve().parents[2]
DOC = 'examples/graph_engine/ge04_demo_document.json'
LINK = 'examples/graph_engine/ge04_demo_section_bindings.json'
CAND = 'examples/graph_engine/ge03_demo_changed_graph.json'


@pytest.fixture
def repo(tmp_path):
    target = tmp_path / 'source'
    (target / 'examples/graph_engine').mkdir(parents=True)
    shutil.copytree(ROOT / '.graph-state/scientific', target / '.graph-state/scientific')
    for name in ('ge03_demo_changed_graph.json', 'ge02_demo_graph.json',
                 'ge04_demo_document.json', 'ge04_demo_section_bindings.json'):
        shutil.copy2(ROOT / 'examples/graph_engine' / name,
                     target / 'examples/graph_engine' / name)
    return target


def execute(repo, **kwargs):
    return plan(repo, document_path=DOC, bindings_path=LINK,
                knowledge_graph=CAND, **kwargs)


def read(repo, relative):
    return json.loads((repo / relative).read_text())


def write(repo, relative, data):
    (repo / relative).write_text(json.dumps(data, sort_keys=True, indent=2) + '\n')


def tweak_link(repo, change):
    doc = read(repo, LINK)
    change(doc)
    write(repo, LINK, doc)


def tweak_doc(repo, change, update_digest=False):
    doc = read(repo, DOC)
    change(doc)
    write(repo, DOC, doc)
    if update_digest:
        tweak_link(repo, lambda x: x.update(document_sha256=hashlib.sha256((repo / DOC).read_bytes()).hexdigest()))


def test_end_to_end_real_ge03_and_ge02_provenance(repo):
    result = execute(repo)
    assert result['status'] == 'review_plan_ready'
    assert result['impact_status'] == 'review_candidates_only'
    assert result['graph_store_generation'] == 1
    assert result['review_candidate_count'] == 3
    assert result['section_review_count'] == 2
    assert not result['unmapped_graph_node_ids']
    assert result['explicit_binding_count'] == 3
    assert [x['minimum_structural_distance'] for x in result['section_review_tasks']] == [0, 2]
    assert len(result['section_review_tasks'][0]['triggers']) == 2
    assert result['scientific_truth_established'] is False
    assert result['automatic_approval_permitted'] is False
    assert result['automatic_document_modification_permitted'] is False
    assert result['persisted_graph_mutated'] is False


def test_report_digest_is_recomputed_from_canonical_body(repo):
    from audit_engine.semantic_audit.graph.persistent_domain_state import canonical, sha
    report = execute(repo)
    digest = report.pop('report_sha256')
    assert sha(canonical(report)) == digest


def test_deterministic_and_immutable_repository(repo):
    files = list((repo / '.graph-state').rglob('*')) + list((repo / 'examples/graph_engine').iterdir())
    prior = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()}
    assert execute(repo) == execute(repo)
    assert prior == {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()}


def test_review_tasks_are_structurally_linked_not_unrelated(repo):
    report = execute(repo)
    nodes = [trigger['graph_node_id'] for task in report['section_review_tasks'] for trigger in task['triggers']]
    assert len(nodes) == len(set(nodes)) == 3
    assert all(t['task'] == 'human_scientific_review' and not t['approval_permitted'] for t in report['section_review_tasks'])


def test_partial_mapping_does_not_silently_drop_graph_impacts(repo):
    tweak_link(repo, lambda x: x['links'].pop())
    report = execute(repo)
    assert report['status'] == 'partial_mapping_requires_review'
    assert report['section_review_count'] == 1
    assert report['review_candidate_count'] == 3
    assert report['unmapped_graph_node_ids'] == ['scientific:proposition:00000000-0000-0000-0000-000000000003']


def test_no_section_mapping_blocks_review_plan(repo, monkeypatch):
    # Construct a logically valid narrowed GE-03 frontier containing only the
    # proposition, while all explicit links refer to the two concepts.
    import audit_engine.semantic_audit.graph.section_impact_integration as module
    real_analyze = module.analyze
    def narrowed(*args, **kwargs):
        result = real_analyze(*args, **kwargs)
        result['review_candidates'] = [c for c in result['review_candidates']
                                       if c['node_id'].startswith('scientific:proposition:')]
        return result
    monkeypatch.setattr(module, 'analyze', narrowed)
    tweak_link(repo, lambda x: x['links'].pop())
    # Two concept links remain, neither describes the affected proposition.
    report = execute(repo)
    assert report['status'] == 'blocked_no_section_mapping'
    assert report['section_review_count'] == 0
    assert report['unmapped_graph_node_ids'] == ['scientific:proposition:00000000-0000-0000-0000-000000000003']


def test_bindings_document_tamper_fails(repo):
    tweak_doc(repo, lambda x: x['children'][0].update(title='Tampered title'))
    with pytest.raises(GE04Error, match='Document changed'):
        execute(repo)


def test_stale_binding_graph_head_fails(repo):
    tweak_link(repo, lambda x: x.update(expected_store_head_sha256='0'*64))
    with pytest.raises(GE04Error, match='stale'):
        execute(repo)


def test_stale_binding_compared_graph_fails(repo):
    tweak_link(repo, lambda x: x.update(expected_compared_snapshot_sha256='0'*64))
    with pytest.raises(GE04Error, match='stale'):
        execute(repo)


def test_wrong_document_identity_fails(repo):
    tweak_link(repo, lambda x: x.update(document_id='20000000-0000-0000-0000-000000000001'))
    with pytest.raises(GE04Error, match='another document'):
        execute(repo)


def test_duplicate_section_ids_fail(repo):
    tweak_doc(repo, lambda x: x['children'].append(copy.deepcopy(x['children'][0])), True)
    with pytest.raises(GE04Error, match='Duplicate document section'):
        execute(repo)


def test_unknown_linked_section_fails(repo):
    tweak_link(repo, lambda x: x['links'][0].update(section_id='20000000-0000-0000-0000-000000000001'))
    with pytest.raises(GE04Error, match='Dangling'):
        execute(repo)


def test_unknown_graph_node_fails(repo):
    tweak_link(repo, lambda x: x['links'][0].update(graph_node_id='scientific:concept:never-present'))
    with pytest.raises(GE04Error, match='Dangling'):
        execute(repo)


def test_duplicate_explicit_links_fail(repo):
    tweak_link(repo, lambda x: x['links'].append(dict(x['links'][0])))
    with pytest.raises(GE04Error, match='Duplicate'):
        execute(repo)


def test_no_explicit_links_fail(repo):
    tweak_link(repo, lambda x: x.update(links=[]))
    with pytest.raises(GE04Error, match='required'):
        execute(repo)


@pytest.mark.parametrize('relation', ['SUPPORTED_BY', 'SCIENTIFICALLY_VERIFIED', 'DEPENDS_ON', '', None])
def test_no_forged_link_relation(repo, relation):
    tweak_link(repo, lambda x: x['links'][0].update(relation=relation))
    with pytest.raises(GE04Error, match='Only structural'):
        execute(repo)


def test_missing_rationale_fails(repo):
    tweak_link(repo, lambda x: x['links'][0].update(rationale=''))
    with pytest.raises(GE04Error, match='rationale'):
        execute(repo)


def test_profile_fields_cannot_be_forged(repo):
    tweak_link(repo, lambda x: x.update(automatic_approval_permitted=True))
    with pytest.raises(GE04Error, match='contract'):
        execute(repo)


def test_noncanonical_section_uuid_fails(repo):
    tweak_link(repo, lambda x: x['links'][0].update(section_id='NOT-A-UUID'))
    with pytest.raises(GE04Error, match='Invalid'):
        execute(repo)


def test_document_without_stable_id_is_rejected(repo):
    tweak_doc(repo, lambda x: x['children'][0].pop('section_id'), True)
    with pytest.raises(GE04Error, match='canonical UUID'):
        execute(repo)


def test_document_cannot_be_inferred_from_legacy_strings(repo):
    legacy = read(repo, DOC)
    legacy['children'] = [{'title':'Legacy equation references','content':'Some free text cites FEM'}]
    write(repo, DOC, legacy)
    tweak_link(repo, lambda x: x.update(document_sha256=hashlib.sha256((repo / DOC).read_bytes()).hexdigest()))
    with pytest.raises(GE04Error, match='invalid section'):
        execute(repo)


def test_file_traversal_is_rejected(repo):
    with pytest.raises(GE04Error, match='Unsafe'):
        plan(repo, document_path='../outside.json', bindings_path=LINK, knowledge_graph=CAND)


def test_symlink_document_is_rejected(repo):
    original = repo / DOC
    original.rename(original.with_name('real_document.json'))
    original.symlink_to(original.with_name('real_document.json'))
    with pytest.raises(GE04Error, match='Unsafe|Symlink'):
        execute(repo)


def test_symlink_binding_is_rejected(repo):
    original = repo / LINK
    original.rename(original.with_name('real_links.json'))
    original.symlink_to(original.with_name('real_links.json'))
    with pytest.raises(GE04Error, match='Unsafe|Symlink'):
        execute(repo)


def test_duplicated_json_object_keys_are_rejected(repo):
    (repo / LINK).write_text('{"a":1,"a":2}')
    with pytest.raises(GE04Error, match='Invalid input JSON'):
        execute(repo)


def test_nonfinite_json_is_rejected(repo):
    (repo / LINK).write_text('{"a": NaN}')
    with pytest.raises((GE04Error, GraphStoreError)):
        execute(repo)


def test_corrupt_ge02_state_is_rejected(repo):
    (repo / '.graph-state/scientific/HEAD.json').write_text('{"corrupted":true}')
    with pytest.raises((GE04Error, GraphStoreError)):
        execute(repo)


def test_missing_candidate_file_rejected(repo):
    with pytest.raises((GE03Error, GE04Error)):
        plan(repo, document_path=DOC, bindings_path=LINK, knowledge_graph='examples/graph_engine/does_not_exist.json')


def test_existing_output_file_is_never_replaced(repo, tmp_path):
    out=tmp_path/'report.json'
    out.write_text('keep-me')
    with pytest.raises(GE04Error, match='already exists'):
        _write_new_report(out, repo, execute(repo))
    assert out.read_text() == 'keep-me'


def test_report_inside_repo_forbidden(repo):
    with pytest.raises(GE04Error, match='outside source'):
        _write_new_report(repo/'report.json', repo, execute(repo))


def test_new_output_file_can_be_verified(repo, tmp_path):
    out=tmp_path/'report.json'
    report=execute(repo)
    _write_new_report(out, repo, report)
    assert json.loads(out.read_text()) == report
    assert not (repo/'report.json').exists()


def test_latest_transition_without_prior_history_reports_no_change(repo):
    tweak_link(repo, lambda x: x.update(expected_compared_snapshot_sha256=None))
    report=plan(repo, mode='latest-transition', document_path=DOC, bindings_path=LINK)
    assert report['impact_status'] == 'no_prior_transition'
    assert report['status'] == 'no_change_to_review'
    assert report['section_review_count'] == 0


def test_latest_transition_stale_binding_is_rejected(repo):
    with pytest.raises(GE04Error, match='Unexpected candidate snapshot'):
        plan(repo, mode='latest-transition', document_path=DOC, bindings_path=LINK)


def test_mutated_graph_input_invalidates_binding(repo):
    graph = read(repo, CAND)
    graph['concepts']['00000000-0000-0000-0000-000000000001']['name']='New unreviewed modified name'
    write(repo, CAND, graph)
    with pytest.raises(GE04Error, match='stale'):
        execute(repo)


def test_schema_version_is_enforced(repo):
    tweak_link(repo, lambda x: x.update(schema_version='unrecognized'))
    with pytest.raises(GE04Error, match='contract'):
        execute(repo)


def test_document_changed_but_digest_up_to_date_can_be_valid(repo):
    tweak_doc(repo, lambda x: x['children'][0].update(title='Updated editorial section label'), True)
    result = execute(repo)
    assert result['section_review_tasks'][0]['title'] == 'Updated editorial section label'


def test_wrong_document_schema_version_is_rejected(repo):
    tweak_doc(repo, lambda x: x.update(version=999), True)
    with pytest.raises(GE04Error, match='schema version'):
        execute(repo)

def test_malformed_persisted_document_child_is_rejected(repo):
    tweak_doc(repo, lambda x: x['children'][0]['children'].append('not a node'), True)
    with pytest.raises(GE04Error, match='Malformed persisted'):
        execute(repo)
