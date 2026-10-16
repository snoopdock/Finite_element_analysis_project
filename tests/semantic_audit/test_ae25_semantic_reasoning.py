"""AE-25: adversarial structural audits, witness semantics, incompleteness, impact."""
import copy
import hashlib

import pytest

from audit_engine.semantic_audit.ae24 import SCHEMA as C_SCHEMA, admit
from audit_engine.semantic_audit.ae25 import RULES, analyze, verify_report, impact, ReasoningError


def model():
    raw = {'contract': b'neutral graph contract with explicit declared obligations',
           'observed': b'adapter-derived observed system facts'}
    doc = {
        'schema_version': C_SCHEMA, 'namespace': 'portable/architecture',
        'sources': [{'id':k,'sha256':hashlib.sha256(v).hexdigest()} for k,v in raw.items()],
        'entities': [{'id':k,'kind':v,'source_id':'contract'} for k,v in [
            ('build','Component'),('deploy','Component'),('review','Component'),
            ('artifact','Artifact'),('publish','Action'),('integrity','Check')]],
        'assertions': [
            {'id':'out', 'subject':'build','predicate':'PRODUCES','object':'artifact','origin':'declared',
             'source_id':'contract','attributes': {'format':'json','schema_id':'v1','meaning_id':'actual_bytes'}},
            {'id':'in', 'subject':'deploy','predicate':'CONSUMES','object':'artifact','origin':'declared',
             'source_id':'contract','attributes': {'producer':'build','format':'json','schema_id':'v1','meaning_id':'actual_bytes'}},
            {'id':'req', 'subject':'deploy','predicate':'REQUIRES_CHECK','object':'integrity','origin':'declared','source_id':'contract'},
            {'id':'done', 'subject':'deploy','predicate':'HAS_CHECK','object':'integrity','origin':'observed','source_id':'observed'},
        ],
        'coverage': [{'component':'deploy','relation':'HAS_CHECK','complete':True,'source_id':'contract'}],
        'policies': [{'id':'acyclic','kind':'acyclic_dependencies','source_id':'contract'}],
    }
    return doc, raw


def add(doc, aid, sub, relation, obj, origin='declared', source_id='contract', attrs=None):
    item = dict(id=aid,subject=sub,predicate=relation,object=obj,origin=origin,source_id=source_id)
    if attrs is not None:
        item['attributes'] = attrs
    doc['assertions'].append(item)


def evaluate(doc, raw):
    out = analyze(doc,raw)
    assert verify_report(doc,raw,out)['status']=='source_replayed'
    return out


def test_compatible_artifact_no_false_violation():
    doc, raw=model()
    result=evaluate(doc,raw)
    assert result['issues'] == []
    assert result['unknowns'] == []
    assert not result['authority']['external_clean_assurance_established']


@pytest.mark.parametrize('field', ['format','schema_id','meaning_id'])
def test_incompatible_artifact_field_is_witnessed(field):
    doc,raw=model()
    doc['assertions'][1]['attributes'][field]='incompatible'
    out=evaluate(doc,raw)
    assert any(x['rule_id']==RULES[0] and 'in' in x['witness_occurrences'] and 'out' in x['witness_occurrences'] for x in out['issues'])
    assert field in out['issues'][0]['detail']['incompatible_fields']


def test_missing_producer_unknown_not_verified_clean():
    doc,raw=model()
    doc['assertions']=[e for e in doc['assertions'] if e['id']!='out']
    out=evaluate(doc,raw)
    assert not out['issues']
    assert any('missing_producer' in x['detail']['reason'] for x in out['unknowns'])


def test_multiple_candidate_producers_ambiguous_not_violation():
    doc,raw=model()
    add(doc,'out2','review','PRODUCES','artifact',attrs={'format':'json','schema_id':'v1','meaning_id':'actual_bytes'})
    doc['assertions'][1]['attributes'].pop('producer')
    out=evaluate(doc,raw)
    assert any(x['detail'].get('reason')=='ambiguous_producer_selection' for x in out['unknowns'])


def test_explicit_source_selection_prevents_cross_producer_substitution():
    doc,raw=model()
    add(doc,'out2','review','PRODUCES','artifact',attrs={'format':'yaml','schema_id':'v2','meaning_id':'different'})
    out=evaluate(doc,raw)
    assert out['issues'] == []


def test_missing_interface_meaning_is_unknown_not_clean():
    doc,raw=model()
    del doc['assertions'][1]['attributes']['meaning_id']
    out=evaluate(doc,raw)
    assert any(x['detail'].get('reason','').startswith('consumer_contract_unspecified') for x in out['unknowns'])


def test_forbidden_observed_action_produces_structural_conflict():
    doc,raw=model()
    add(doc,'prohibits','deploy','FORBIDS','publish')
    add(doc,'observes','deploy','PERFORMS','publish',origin='observed',source_id='observed')
    out=evaluate(doc,raw)
    assert any(x['rule_id']==RULES[1] and set(x['witness_occurrences'])=={'prohibits','observes'} for x in out['issues'])


def test_declared_action_does_not_prove_performance():
    doc,raw=model()
    add(doc,'prohibits','deploy','FORBIDS','publish')
    add(doc,'observes','deploy','PERFORMS','publish',origin='declared')
    assert not evaluate(doc,raw)['issues']


def test_neural_proposal_is_not_observed_action():
    doc,raw=model()
    add(doc,'prohibits','deploy','FORBIDS','publish')
    add(doc,'neural','deploy','PERFORMS','publish',origin='candidate')
    out=evaluate(doc,raw)
    assert not out['issues']
    assert out['candidate_count']==1
    assert any('candidate' in x['detail']['reason'] for x in out['unknowns'])


def test_neural_candidate_cannot_supply_missing_producer():
    doc,raw=model()
    doc['assertions'][0]['origin']='candidate'
    out=evaluate(doc,raw)
    assert not out['issues']
    assert out['unknown_count'] > 0


def test_missing_required_check_with_coverage_conflicts():
    doc,raw=model()
    doc['assertions']=[x for x in doc['assertions'] if x['id']!='done']
    out=evaluate(doc,raw)
    assert any(x['rule_id']==RULES[2] for x in out['issues'])
    assert out['authority']['source_assertion_truth_verified'] is False


def test_missing_required_check_without_coverage_is_unknown():
    doc,raw=model()
    doc['assertions']=[x for x in doc['assertions'] if x['id']!='done']
    doc['coverage'] = []
    out=evaluate(doc,raw)
    assert not out['issues']
    assert any(x['rule_id']==RULES[2] for x in out['unknowns'])


def test_missing_required_check_incomplete_coverage_is_unknown():
    doc,raw=model()
    doc['assertions']=[x for x in doc['assertions'] if x['id']!='done']
    doc['coverage'][0]['complete'] = False
    out=evaluate(doc,raw)
    assert not out['issues']
    assert out['unknown_count'] == 1


def test_self_dependency_cycle_requires_policy():
    doc,raw=model()
    add(doc,'self','deploy','DEPENDS_ON','deploy')
    assert any(x['rule_id']==RULES[3] for x in evaluate(doc,raw)['issues'])
    doc['policies'] = []
    assert not evaluate(doc,raw)['issues']


def test_long_cycle_has_exact_witnesses():
    doc,raw=model()
    add(doc,'d1','build','DEPENDS_ON','deploy')
    add(doc,'d2','deploy','DEPENDS_ON','review')
    add(doc,'d3','review','DEPENDS_ON','build')
    report=evaluate(doc,raw)
    cycle=[x for x in report['issues'] if x['rule_id']==RULES[3]]
    assert len(cycle)==1
    assert set(cycle[0]['witness_occurrences']) == {'d1','d2','d3'}


def test_candidate_edge_cannot_complete_cycle():
    doc,raw=model()
    add(doc,'d1','build','DEPENDS_ON','deploy')
    add(doc,'d2','deploy','DEPENDS_ON','build', origin='candidate')
    assert not evaluate(doc,raw)['issues']


def test_impact_uses_reverse_dependency_direction():
    doc,raw=model()
    add(doc,'d1','deploy','DEPENDS_ON','build')
    add(doc,'d2','review','DEPENDS_ON','deploy')
    affected = impact(admit(doc,raw),'build')
    assert affected['possibly_affected_components']==['deploy','review']
    assert affected['effect_is_not_proven']


def test_impact_ignores_neural_proposal():
    doc,raw=model()
    add(doc,'d1','deploy','DEPENDS_ON','build',origin='candidate')
    assert not impact(admit(doc,raw),'build')['possibly_affected_components']


def test_report_mutation_and_rehash_not_enough():
    doc,raw=model()
    report=analyze(doc,raw)
    report['status']='verified_clean'
    from audit_engine.semantic_audit.ae24 import canonical
    from audit_engine.semantic_audit.ae24.contracts import sha
    body=dict(report);body.pop('report_sha256')
    report['report_sha256']=sha(canonical(body))
    with pytest.raises(ReasoningError, match='mismatch'):
        verify_report(doc,raw,report)


def test_changed_source_rejects_old_report():
    doc,raw=model()
    report=analyze(doc,raw)
    raw['observed'] = b'unexpected new version'
    with pytest.raises(ValueError):
        verify_report(doc,raw,report)


def test_report_and_rule_order_deterministic():
    doc,raw=model()
    one=analyze(doc,raw)
    two=analyze(copy.deepcopy(doc),dict(raw))
    assert one == two
    assert one['rule_ids']==list(RULES)


def test_agnostic_to_source_language_when_graph_facts_are_equal():
    doc,raw=model()
    doc['assertions'][1]['attributes']['meaning_id']='mismatched'
    result1=analyze(doc,raw)
    doc['namespace']='c-plus-plus-service'
    result2=analyze(doc,raw)
    assert [(x['rule_id'],x['detail']) for x in result1['issues']] == [(x['rule_id'],x['detail']) for x in result2['issues']]


def test_two_violations_can_use_one_source_occurrence():
    doc,raw=model()
    doc['assertions'][1]['attributes']['format']='yaml'
    doc['assertions'][1]['attributes']['meaning_id']='other-meaning'
    out=evaluate(doc,raw)
    issues=[x for x in out['issues'] if x['rule_id']==RULES[0]]
    assert len(issues)==1
    assert set(issues[0]['detail']['incompatible_fields'])=={'format','meaning_id'}


def test_no_verified_root_cause_even_on_structural_conflict():
    doc,raw=model()
    add(doc,'prohibits','deploy','FORBIDS','publish')
    add(doc,'observes','deploy','PERFORMS','publish',origin='observed',source_id='observed')
    result=evaluate(doc,raw)
    assert result['issues_count']==1
    assert result['authority']['runtime_causality_verified'] is False
    assert result['authority']['external_clean_assurance_established'] is False


def test_cli_canonical_file_replay(tmp_path, capsys):
    from audit_engine.semantic_audit.ae24 import canonical
    from audit_engine.semantic_audit.ae25.__main__ import main
    from pathlib import Path
    import json
    doc, raw = model()
    folder = tmp_path/'evidence'; folder.mkdir()
    for sid, content in raw.items():
        (folder/sid).write_bytes(content)
    contract_path = tmp_path/'CONTRACT.json'
    contract_path.write_bytes(canonical(doc))
    assert main(['analyze','--contract',str(contract_path),'--evidence-dir',str(folder)])==0
    report = json.loads(capsys.readouterr().out)
    report_path = tmp_path/'REPORT.json'
    report_path.write_bytes(canonical(report))
    assert main(['verify','--contract',str(contract_path),'--evidence-dir',str(folder),'--report',str(report_path)])==0
    assert json.loads(capsys.readouterr().out)['status']=='source_replayed'


def test_cli_rejects_symlink_and_noncanonical_file(tmp_path):
    from audit_engine.semantic_audit.ae24 import canonical
    from audit_engine.semantic_audit.ae25.__main__ import load_inputs
    from pathlib import Path
    doc, raw = model()
    folder = tmp_path/'evidence'; folder.mkdir()
    for sid, content in raw.items():
        (folder/sid).write_bytes(content)
    contract_path = tmp_path/'CONTRACT.json'
    contract_path.write_bytes(canonical(doc).rstrip(b'\n'))
    with pytest.raises(ValueError, match='canonical'):
        load_inputs(contract_path, folder)
    contract_path.write_bytes(canonical(doc))
    (folder/'observed').unlink()
    (folder/'observed').symlink_to(folder/'contract')
    with pytest.raises(ValueError, match='Symlink'):
        load_inputs(contract_path, folder)


def test_multiple_versions_same_producer_are_not_arbitrarily_flagged():
    doc, raw = model()
    add(doc,'out_v2','build','PRODUCES','artifact', attrs={
        'format':'yaml','schema_id':'v2','meaning_id':'alternate_semantics'})
    result = evaluate(doc, raw)
    assert not result['issues']
    assert any(x['detail'].get('reason') == 'ambiguous_producer_contract_versions' for x in result['unknowns'])
    doc['assertions'][1]['attributes']['producer_occurrence'] = 'out'
    result = evaluate(doc, raw)
    assert not result['issues']
    assert not result['unknowns']
    doc['assertions'][1]['attributes']['producer_occurrence'] = 'out_v2'
    result = evaluate(doc, raw)
    assert any(x['rule_id'] == RULES[0] for x in result['issues'])


def test_declared_check_does_not_count_as_observed_verification():
    doc, raw = model()
    for row in doc['assertions']:
        if row['id'] == 'done':
            row['origin'] = 'declared'
    result = evaluate(doc, raw)
    assert any(x['rule_id'] == RULES[2] for x in result['issues'])
