"""AE-02.1 adversarial behavioral oracles over actual AE-01 and G3 integrations.

These tests do not mock the source analyzer, G3 rule executor, evidence seals,
or verified generation loading. The expected impact paths are independently
specified from small source fixtures, not generated from the planner itself.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae02 import compare_generations, load_generation
from audit_engine.semantic_audit.ae02.impact import build_impact_plan
from audit_engine.semantic_audit.ae02.service import _graph_snapshot
from audit_engine.semantic_audit.evolution.delta import compare_snapshots as g3_delta

POLICY = Path(__file__).resolve().parents[2] / 'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
ROOT = Path(__file__).resolve().parents[2]


def fixture(tmp_path, original, updated, *, old_labels=None, new_labels=None):
    source = tmp_path / 'source'; source.mkdir()
    for name, code in original.items():
        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(code if isinstance(code, bytes) else code.encode())
    old_labels = old_labels or {name[:-3]: 'stable' for name in original if name.endswith('.py') and '/' not in name}
    new_labels = new_labels if new_labels is not None else old_labels
    first = audit_repository(source, tmp_path / 'before', policy_file=POLICY, lifecycle=old_labels)['report']
    for name in original.keys() - updated.keys():
        (source/name).unlink()
    for name, code in updated.items():
        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(code if isinstance(code, bytes) else code.encode())
    second = audit_repository(source, tmp_path / 'after', policy_file=POLICY, lifecycle=new_labels)['report']
    return first, second, compare_generations(tmp_path / 'before', tmp_path / 'after')


def modules(result):
    return [t['module'] for t in result['impact_plan']['tasks']]


def task(result, name):
    return next(t for t in result['impact_plan']['tasks'] if t['module'] == name)


def test_changed_leaf_rechecks_transitive_dependents_even_without_import_change(tmp_path):
    files = {'app.py': 'import service\n', 'service.py': 'import db\n', 'db.py': 'x=1\n'}
    _, _, result = fixture(tmp_path, files, {**files, 'db.py':'x=2\n'})
    assert modules(result) == ['db', 'service', 'app']
    assert [task(result, name)['depth'] for name in ('db', 'service', 'app')] == [0, 1, 2]
    assert task(result,'db')['reasons'] == ['source_bytes_changed']
    assert 'transitive_static_import_dependent' in task(result,'app')['reasons']
    assert result['impact_plan']['source_digest_changed']
    assert result['impact_plan']['completeness'] == 'incremental_review_required'


def test_old_graph_retained_for_deleted_import_and_reverse_impact(tmp_path):
    a = {'app.py':'import service\n', 'service.py':'import db\n','db.py':'v=1\n'}
    b = {'app.py':'import service\n', 'service.py':'x=1\n','db.py':'v=1\n'}
    _, _, result = fixture(tmp_path, a, b)
    assert {'service','app','db'} <= set(modules(result))
    assert 'import_occurrence_removed_or_changed' in task(result,'service')['reasons']
    assert task(result, 'app')['depth'] == 1
    assert task(result, 'service')['supporting_occurrences']


def test_new_graph_used_for_addition(tmp_path):
    a = {'app.py':'import service\n','service.py':'x=1\n','db.py':'v=1\n'}
    b = {**a, 'service.py':'import db\n'}
    _, _, r = fixture(tmp_path,a,b)
    assert {'db','service','app'} <= set(modules(r))
    assert task(r,'app')['depth'] == 1
    assert task(r,'db')['supporting_occurrences']


def test_edit_without_dependents_only_rechecks_module(tmp_path):
    a={'a.py':'x=1\n','b.py':'import stable\n','stable.py':''}
    _,_,r=fixture(tmp_path,a,{**a,'a.py':'x=3\n'})
    assert modules(r)==['a']
    assert r['impact_plan']['completeness']=='incremental_review_required'


def test_unchanged_source_and_policy_produces_zero_review_tasks(tmp_path):
    f={'app.py':'import db\n','db.py':'v=1\n'}
    _,_,r=fixture(tmp_path,f,f)
    assert modules(r)==[]
    assert r['impact_plan']['completeness']=='no_detected_change'
    assert not r['impact_plan']['truncated']
    assert r['impact_plan']['g3_change_atoms']==[]


def test_forbidden_dependency_introduction_is_verified_and_prioritized(tmp_path):
    a={'prod.py':'import stable\n','stable.py':'','exp.py':''}
    b={**a,'prod.py':'import exp\n'}
    _,_,r=fixture(tmp_path,a,b,old_labels={'prod':'production','stable':'stable','exp':'experimental'})
    assert [f['status'] for f in r['finding_evolution']]==['new_verified_observation']
    assert len(r['impact_plan']['g3_change_atoms'])>0
    assert 'prod' in modules(r)
    assert task(r,'prod')['supporting_occurrences']
    assert r['interpretation']['clean_claim_allowed'] is False


def test_policy_mapping_change_is_full_scope_review_not_simple_dependency_delta(tmp_path):
    f={'prod.py':'import stable\n','stable.py':'','other.py':'x=1\n'}
    _,_,r=fixture(tmp_path,f,f,old_labels={'prod':'production','stable':'stable','other':'stable'},
                  new_labels={'prod':'production','stable':'experimental','other':'stable'})
    assert r['impact_plan']['completeness']=='full_review_required'
    assert 'lifecycle_mapping_changed' in r['impact_plan']['full_recheck_reasons']
    assert set(modules(r))=={'prod','stable','other'}
    assert r['impact_plan']['policy_changed']


def test_old_incomplete_run_cannot_be_treated_as_sufficiently_scoped(tmp_path):
    f={'prod.py':'import exp\n','exp.py':''}
    _,_,r=fixture(tmp_path,f,f,old_labels={'prod':'production'},
                  new_labels={'prod':'production','exp':'experimental'})
    assert r['impact_plan']['completeness']=='full_review_required'
    assert 'incomplete_ae01_assurance_scope' in r['impact_plan']['full_recheck_reasons']


def test_successor_incomplete_scan_never_qualifies_as_no_change(tmp_path):
    f={'prod.py':'import exp\n','exp.py':''}
    _,_,r=fixture(tmp_path,f,f,old_labels={'prod':'production','exp':'experimental'},
                  new_labels={'prod':'production'})
    assert r['impact_plan']['completeness']=='full_review_required'
    assert r['interpretation']['assurance_complete'] is False


def test_module_removal_preserves_old_reverse_import_paths(tmp_path):
    before={'app.py':'import core\n','core.py':'import leaf\n','leaf.py':'v=1\n'}
    after={'app.py':'import core\n','core.py':'import leaf\n'}
    _,_,r=fixture(tmp_path,before,after)
    assert 'leaf' in modules(r)
    assert 'app' in modules(r)
    assert 'source_file_removed' in task(r,'leaf')['reasons']


def test_addition_without_edges_is_not_dropped(tmp_path):
    a={'a.py':'import stable\n','stable.py':''}
    _,_,r=fixture(tmp_path,a,{**a,'empty.py':''})
    assert modules(r)==['empty']
    assert task(r,'empty')['source_files']==['empty.py']


def test_move_detected_as_removed_and_added_not_proven_semantically_equal(tmp_path):
    a={'old.py':'x=1\n','consumer.py':'import old\n'}
    b={'new.py':'x=1\n','consumer.py':'import old\n'}
    _,_,r=fixture(tmp_path,a,b)
    assert {'old','new','consumer'}<=set(modules(r))
    assert 'source_file_removed' in task(r,'old')['reasons']
    assert 'source_file_added' in task(r,'new')['reasons']


def test_cycle_propagation_terminates_and_is_deterministic(tmp_path):
    a={'a.py':'import b\nx=1\n','b.py':'import a\n','c.py':'import a\n'}
    _,_,r=fixture(tmp_path,a,{**a,'a.py':'import b\nx=2\n'})
    assert modules(r)==['a','b','c']
    assert len(modules(r))==len(set(modules(r)))
    assert modules(r)==modules(compare_generations(tmp_path/'before',tmp_path/'after'))


def test_depth_budget_fails_closed(tmp_path):
    a={'root.py':'import mid\n','mid.py':'import leaf\n','leaf.py':'v=1\n'}
    fixture(tmp_path,a,{**a,'leaf.py':'v=2\n'})
    r=compare_generations(tmp_path/'before',tmp_path/'after',max_depth=0)
    assert r['impact_plan']['completeness']=='full_review_required'
    assert r['impact_plan']['truncated']
    assert 'budget_exhausted' in r['impact_plan']['full_recheck_reasons']


def test_task_budget_fails_closed_and_never_trusts_omitted_tasks(tmp_path):
    a={'root.py':'import leaf\n','mid.py':'import leaf\n','leaf.py':'v=1\n','other.py':'x=1\n'}
    fixture(tmp_path,a,{**a,'leaf.py':'v=2\n'})
    r=compare_generations(tmp_path/'before',tmp_path/'after',max_tasks=1)
    assert r['impact_plan']['total_detected_modules']>=3
    assert len(r['impact_plan']['tasks'])==1
    assert r['impact_plan']['truncated']
    assert r['impact_plan']['completeness']=='full_review_required'


@pytest.mark.parametrize('bad_depth,bad_tasks', [(-1,2),(0,0),(10001,2),(1,100001)])
def test_invalid_budgets_rejected(tmp_path,bad_depth,bad_tasks):
    a={'a.py':'x=1\n'}
    fixture(tmp_path,a,a)
    with pytest.raises(ValueError,match='budget'):
        compare_generations(tmp_path/'before',tmp_path/'after',max_depth=bad_depth,max_tasks=bad_tasks)


def test_plan_identity_changes_when_recheck_budget_changes(tmp_path):
    f={'app.py':'import db\n','db.py':'v=1\n'}
    fixture(tmp_path,f,{**f,'db.py':'v=2\n'})
    a=compare_generations(tmp_path/'before',tmp_path/'after',max_depth=1)
    b=compare_generations(tmp_path/'before',tmp_path/'after',max_depth=2)
    assert a['impact_plan']['plan_sha256']!=b['impact_plan']['plan_sha256']
    assert a['comparison_sha256']!=b['comparison_sha256']


def test_impact_plan_self_hash_matches_canonical_record(tmp_path):
    f={'app.py':'import db\n','db.py':'v=1\n'}
    _,_,r=fixture(tmp_path,f,{**f,'db.py':'v=2\n'})
    plan=dict(r['impact_plan']);digest=plan.pop('plan_sha256')
    assert sha(canonical(plan))==digest
    record=dict(r);digest=record.pop('comparison_sha256')
    assert sha(canonical(record))==digest


def test_reject_unauthenticated_generations(tmp_path):
    f={'a.py':'x=1\n'}
    fixture(tmp_path,f,f)
    before=load_generation(tmp_path/'before')
    delta=g3_delta(_graph_snapshot(before),_graph_snapshot(before))
    with pytest.raises(TypeError,match='sealed'):
        build_impact_plan({},before,delta)


def test_modified_artifact_is_rejected_before_planning(tmp_path):
    f={'app.py':'import db\n','db.py':'v=1\n'}
    fixture(tmp_path,f,{**f,'db.py':'v=2\n'})
    before=load_generation(tmp_path/'before')
    p=tmp_path/'after'/'generations'/load_generation(tmp_path/'after').snapshot.generation_id/'policy_graph.json'
    p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError,match='checksum'):
        compare_generations(tmp_path/'before',tmp_path/'after')


def test_cli_detached_comparison_verifier_detects_mutation(tmp_path):
    f={'app.py':'import db\n','db.py':'v=1\n'}
    _,_,r=fixture(tmp_path,f,{**f,'db.py':'v=2\n'})
    record=tmp_path/'comparison.json';record.write_bytes(canonical(r))
    cmd=[sys.executable,'-m','audit_engine.semantic_audit.ae02',
         '--before-output',str(tmp_path/'before'), '--after-output',str(tmp_path/'after'),
         '--verify-record',str(record)]
    ok=subprocess.run(cmd,cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
    assert ok.returncode==0,ok.stderr
    assert 'passed' in ok.stdout
    corrupted=dict(r);corrupted['impact_plan']=dict(r['impact_plan']);corrupted['impact_plan']['tasks']=[]
    record.write_bytes(canonical(corrupted))
    bad=subprocess.run(cmd,cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
    assert bad.returncode==4
    assert 'mismatch' in bad.stderr


def test_cli_read_only_and_budget_exit_semantics(tmp_path):
    f={'app.py':'import db\n','db.py':'v=1\n'}
    fixture(tmp_path,f,{**f,'db.py':'v=2\n'})
    cmd=[sys.executable,'-m','audit_engine.semantic_audit.ae02',
         '--before-output',str(tmp_path/'before'),'--after-output',str(tmp_path/'after'), '--max-tasks','1']
    outcome=subprocess.run(cmd,cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
    assert outcome.returncode==3
    obj=json.loads(outcome.stdout)
    assert not obj['interpretation']['impact_plan_complete']
    assert obj['impact_plan']['truncated']
    assert obj['impact_plan']['completeness']=='full_review_required'


def test_no_unauthorized_source_mutation(tmp_path):
    f={'app.py':'import db\n','db.py':'v=1\n'}
    fixture(tmp_path,f,{**f,'db.py':'v=2\n'})
    before={p:p.read_bytes() for folder in (tmp_path/'before',tmp_path/'after')
            for p in folder.rglob('*') if p.is_file()}
    compare_generations(tmp_path/'before',tmp_path/'after')
    assert before=={p:p.read_bytes() for folder in (tmp_path/'before',tmp_path/'after')
                    for p in folder.rglob('*') if p.is_file()}


def test_witness_index_is_seal_bound_for_both_generations(tmp_path):
    a={'app.py':'import db\n','db.py':'v=1\n'}
    _,_,r=fixture(tmp_path,a,{**a,'db.py':'v=2\n'})
    plan=r['impact_plan']
    witness_id=task(r,'app')['supporting_occurrences'][0]
    row=plan['evidence_index'][witness_id]
    assert len(row)==2
    assert {w['generation_id'] for w in row}=={
        r['previous']['generation_id'],r['current']['generation_id']}
    assert {w['seal_sha256'] for w in row}=={
        r['previous']['publication_seal_hash'],r['current']['publication_seal_hash']}
    assert all(w['line']==1 and w['column']==0 and w['source_file']=='app.py' for w in row)
    assert all(w['source_module']=='app' and w['target_module']=='db' for w in row)


def test_witness_for_deleted_import_is_historical_not_fabricated_current(tmp_path):
    a={'app.py':'import core\n','core.py':'import db\n','db.py':''}
    b={'app.py':'import core\n','core.py':'x=1\n','db.py':''}
    _,_,r=fixture(tmp_path,a,b)
    removed=next(d for d in r['delta']['removed_dependencies'] if d['file']=='core.py')
    index=r['impact_plan']['evidence_index'][removed['id']]
    assert all(w['generation_id']==r['previous']['generation_id'] for w in index)
    assert index[0]['source_sha256']==sha(b'import db\n')


def test_source_bytes_change_reflected_in_verified_witness_hash(tmp_path):
    a={'app.py':'import core\n','core.py':'v=1\n'}
    _,_,r=fixture(tmp_path,a,{**a,'app.py':'import core\nx=4\n'})
    ref=task(r,'app')['supporting_occurrences'][0]
    entries=r['impact_plan']['evidence_index'][ref]
    assert {row['source_sha256'] for row in entries}=={
        sha(b'import core\n'),sha(b'import core\nx=4\n')}


def test_package_relative_import_impact_path(tmp_path):
    a={'pkg/__init__.py':'','pkg/app.py':'from . import core\n',
       'pkg/core.py':'from . import leaf\n','pkg/leaf.py':'x=1\n'}
    _,_,r=fixture(tmp_path,a,{**a,'pkg/leaf.py':'x=2\n'},
                  old_labels={'pkg':'stable','pkg.app':'production','pkg.core':'stable','pkg.leaf':'stable'})
    assert {'pkg.leaf','pkg.core','pkg.app'} <= set(modules(r))
    assert task(r,'pkg.app')['depth']==2


def test_conditional_import_still_conservatively_propagates(tmp_path):
    a={'app.py':'if condition:\n    import lib\n','lib.py':'x=1\n'}
    _,_,r=fixture(tmp_path,a,{**a,'lib.py':'x=2\n'})
    assert 'app' in modules(r)
    assert 'transitive_static_import_dependent' in task(r,'app')['reasons']
    ref=task(r,'app')['supporting_occurrences'][0]
    assert r['impact_plan']['evidence_index'][ref][0]['line']==2


def test_deterministic_across_distinct_sealed_output_paths(tmp_path):
    a={'app.py':'import lib\n','lib.py':'x=1\n'}
    _,_,r=fixture(tmp_path,a,{**a,'lib.py':'x=2\n'})
    r2=compare_generations(tmp_path/'before',tmp_path/'after')
    assert canonical(r)==canonical(r2)
    assert r['impact_plan']['plan_sha256']==r2['impact_plan']['plan_sha256']
