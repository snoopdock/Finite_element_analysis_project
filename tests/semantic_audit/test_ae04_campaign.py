"""AE-04 acceptance: independent oracles over actual sealed AE-01 generations.

No graph/verifier mocks. Fixture expectations follow declared policy and source
content. Tests must reject incomplete evidence, not merely accept JSON existence.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae03 import run_experiment
from audit_engine.semantic_audit.ae04 import (build_campaign, verify_campaign,
                                               publish_campaign, verify_publication)

POLICY = Path(__file__).resolve().parents[2] / 'specs/rules/architecture/no_production_to_experimental_dependency.yaml'


def files(tmp_path, previous, current, *, old_labels=None, labels=None):
    source = tmp_path / 'source'
    source.mkdir()
    for name, contents in previous.items():
        path = source/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8')
    old_labels = old_labels if old_labels is not None else {'prod':'production','stable':'stable','exp':'experimental','other':'stable'}
    labels = labels if labels is not None else old_labels
    audit_repository(source, tmp_path/'before', lifecycle=old_labels, policy_file=POLICY)
    for name in previous.keys()-current.keys():
        (source/name).unlink()
    for name, contents in current.items():
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(contents,encoding='utf-8')
    audit_repository(source, tmp_path/'after', lifecycle=labels, policy_file=POLICY)
    return source, tmp_path/'before', tmp_path/'after'


def setup_clean(tmp_path):
    f={'prod.py':'import stable\n','stable.py':'answer=42\n','exp.py':''}
    return files(tmp_path,f,f)


def test_no_change_clean_policy_is_bounded_pass(tmp_path):
    _, old, new=setup_clean(tmp_path)
    r=build_campaign(old,new)
    assert r['decision']['status']=='bounded_architecture_policy_pass'
    assert r['decision']['architecture_clean_claim_within_scope'] is True
    assert r['decision']['general_software_correctness_certified'] is False
    assert r['decision']['test_effectiveness_certified'] is False
    assert r['review']['tasks']==[]
    assert verify_campaign(r,old,new)['status']=='verified'
    assert r==build_campaign(old,new)


def test_verified_violation_outweighs_clean_change_review(tmp_path):
    before={'prod.py':'import stable\n','stable.py':'','exp.py':''}
    after={**before,'prod.py':'import exp\n'}
    _,old,new=files(tmp_path,before,after)
    r=build_campaign(old,new)
    assert r['decision']['status']=='verified_policy_violation_requires_review'
    p0=[t for t in r['review']['tasks'] if t['priority']=='P0']
    assert len(p0)==1 and p0[0]['module']=='prod'
    assert len(p0[0]['finding_ids'])==1
    assert len(p0[0]['occurrence_ids'])>=1
    assert r['decision']['architecture_clean_claim_within_scope'] is False
    assert verify_campaign(r,old,new)['status']=='verified'


def test_change_with_permitted_dependency_requires_review(tmp_path):
    before={'prod.py':'import stable\n','stable.py':'x=1\n','exp.py':''}
    _,old,new=files(tmp_path,before,{**before,'stable.py':'x=2\n'})
    r=build_campaign(old,new)
    assert r['decision']['status']=='change_review_required'
    assert [t['module'] for t in r['review']['tasks']]==['stable','prod']
    assert r['review']['tasks'][1]['priority']=='P3'


def test_removed_import_requires_review_and_old_witness(tmp_path):
    before={'prod.py':'import stable\n','stable.py':'','exp.py':''}
    _,old,new=files(tmp_path,before,{**before,'prod.py':'x=1\n'})
    # No applicable imports in successor, so coverage cannot claim compliance.
    r=build_campaign(old,new)
    assert r['decision']['status']=='inconclusive_scope_requires_review'
    assert 'prod' in {task['module'] for task in r['review']['tasks']}
    assert r['review']['evidence_index']


def test_unclassified_module_never_clean(tmp_path):
    before={'prod.py':'import stable\n','stable.py':''}
    _,old,new=files(tmp_path,before,before, labels={'prod':'production'})
    r=build_campaign(old,new)
    assert r['decision']['status']=='inconclusive_scope_requires_review'
    assert r['decision']['architecture_clean_claim_within_scope'] is False


def test_source_modified_without_import_topology_change(tmp_path):
    before={'prod.py':'import stable\n','stable.py':'x=1\n'}
    _,old,new=files(tmp_path,before,{**before,'stable.py':'x=5\n'})
    r=build_campaign(old,new)
    assert r['delta']['source_changed']
    assert not r['delta']['findings_changed']
    assert 'source_bytes_changed' in next(t for t in r['review']['tasks'] if t['module']=='stable')['reasons']


def test_policy_change_never_silently_accepted(tmp_path):
    before={'prod.py':'import stable\n','stable.py':''}
    _,old,new=files(tmp_path,before,before, labels={'prod':'production','stable':'experimental'})
    r=build_campaign(old,new)
    assert r['review']['full_review_required']
    assert r['decision']['status']=='verified_policy_violation_requires_review'
    assert 'policy_changed' in r['decision']['reasons']


def test_required_mutation_absence_blocks_pass(tmp_path):
    _,old,new=setup_clean(tmp_path)
    r=build_campaign(old,new,require_mutation=True)
    assert r['decision']['status']=='inconclusive_scope_requires_review'
    assert 'required_mutation_evidence_missing' in r['decision']['reasons']


def test_budget_truncation_fails_closed(tmp_path):
    before={'prod.py':'import stable\n','stable.py':'import other\n','other.py':'v=1\n'}
    _,old,new=files(tmp_path,before,{**before,'other.py':'v=2\n'})
    r=build_campaign(old,new,max_tasks=1)
    assert r['review']['truncated']
    assert r['decision']['status']=='inconclusive_scope_requires_review'
    assert r['review']['listed']==1


def test_receipt_tampering_even_if_rehashed_is_rejected(tmp_path):
    _,old,new=setup_clean(tmp_path)
    r=build_campaign(old,new)
    r['decision']['status']='bounded_architecture_policy_pass_fake'
    r['campaign_sha256']=sha(canonical({k:v for k,v in r.items() if k!='campaign_sha256'}))
    with pytest.raises(ValueError, match='independently rederived'):
        verify_campaign(r,old,new)


def test_source_generation_tampering_rejected(tmp_path):
    _,old,new=setup_clean(tmp_path)
    r=build_campaign(old,new)
    from audit_engine.semantic_audit.ae02 import load_generation
    g=load_generation(new)
    report=new/'generations'/g.snapshot.generation_id/'report.json'
    report.write_bytes(report.read_bytes()+b' ')
    with pytest.raises(ValueError,match='checksum'):
        verify_campaign(r,old,new)


def test_publish_and_detached_verify(tmp_path):
    _,old,new=setup_clean(tmp_path)
    r=build_campaign(old,new)
    pub=publish_campaign(r,tmp_path/'campaign',before_output=old,after_output=new)
    assert pub['generation'].startswith('ae04-')
    result=verify_publication(tmp_path/'campaign',before_output=old,after_output=new)
    assert result['decision']=='bounded_architecture_policy_pass'
    assert result['generation']==pub['generation']
    assert publish_campaign(r,tmp_path/'campaign',before_output=old,after_output=new)==pub


def test_tampered_campaign_seal_or_record_rejected(tmp_path):
    _,old,new=setup_clean(tmp_path)
    pub=publish_campaign(build_campaign(old,new),tmp_path/'campaign',before_output=old,after_output=new)
    p=tmp_path/'campaign'/'generations'/pub['generation']/'campaign.json'
    p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError,match='seal'):
        verify_publication(tmp_path/'campaign',before_output=old,after_output=new)


def test_failed_publication_does_not_leave_stale_success(tmp_path):
    _,old,new=setup_clean(tmp_path)
    r=build_campaign(old,new)
    publish_campaign(r,tmp_path/'campaign',before_output=old,after_output=new)
    forged=copy.deepcopy(r)
    forged['decision']['status']='forged'
    with pytest.raises(ValueError):
        publish_campaign(forged,tmp_path/'campaign',before_output=old,after_output=new)
    p=json.loads((tmp_path/'campaign'/'LATEST.json').read_bytes())
    assert p['status']=='failed'
    with pytest.raises(ValueError,match='not completed'):
        verify_publication(tmp_path/'campaign',before_output=old,after_output=new)


def test_output_symlink_refused(tmp_path):
    _,old,new=setup_clean(tmp_path)
    output=tmp_path/'outside';output.mkdir()
    link=tmp_path/'link';link.symlink_to(output,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlink'):
        publish_campaign(build_campaign(old,new),link,before_output=old,after_output=new)


def test_output_overlap_refused(tmp_path):
    _,old,new=setup_clean(tmp_path)
    with pytest.raises(ValueError,match='overlaps'):
        publish_campaign(build_campaign(old,new),old/'inside',before_output=old,after_output=new)


def test_failure_is_not_hidden_on_wrong_mutation_root(tmp_path):
    _,old,new=setup_clean(tmp_path)
    with pytest.raises(ValueError,match='requires source root'):
        build_campaign(old,new,mutation_record={'source_hashes':{}},replay_mutation=True)


def test_campaign_verifier_does_not_trust_claim_without_rederivation(tmp_path):
    _,old,new=setup_clean(tmp_path)
    r=build_campaign(old,new)
    r['review']['tasks'].append({'fake':'proof'})
    with pytest.raises(ValueError,match='digest'):
        verify_campaign(r,old,new)


def test_cli_publish_and_verify(tmp_path):
    _,old,new=setup_clean(tmp_path)
    repo=Path(__file__).resolve().parents[2]
    args=['--before-output',str(old),'--after-output',str(new),'--output',str(tmp_path/'campaign')]
    for command in ('run','verify'):
        process=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae04',command,*args],
             cwd=repo,capture_output=True,text=True,timeout=30)
        assert process.returncode==0,(command,process.stderr)
    assert json.loads(process.stdout)['status']=='verified'


def test_manual_nonpassing_campaign_exits_three_and_publishes(tmp_path):
    before={'prod.py':'import stable\n','stable.py':'','exp.py':''}
    _,old,new=files(tmp_path,before,{**before,'prod.py':'import exp\n'})
    repo=Path(__file__).resolve().parents[2]
    process=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae04','run',
        '--before-output',str(old),'--after-output',str(new),'--output',str(tmp_path/'campaign')],
        cwd=repo,capture_output=True,text=True,timeout=30)
    assert process.returncode==3,process.stderr
    assert json.loads(process.stdout)['decision']['status']=='verified_policy_violation_requires_review'


def test_mutation_evidence_full_replay_and_source_binding(tmp_path):
    src=tmp_path/'src';src.mkdir()
    (src/'tests').mkdir(); (src/'pkg').mkdir()
    (src/'pkg'/'__init__.py').write_text('')
    (src/'pkg'/'value.py').write_text('def is_allowed(v):\n    return v == 7\n')
    (src/'tests'/'test_value.py').write_text('from pkg.value import is_allowed\ndef test_value():\n    assert is_allowed(7)\n    assert not is_allowed(5)\n')
    old=tmp_path/'old';new=tmp_path/'new'
    labels={'pkg':'stable','pkg.value':'stable','tests.test_value':'stable'}
    audit_repository(src,old,lifecycle=labels,policy_file=POLICY)
    audit_repository(src,new,lifecycle=labels,policy_file=POLICY)
    m=run_experiment(src,['pkg/value.py'],['tests/test_value.py'],max_mutants=1,timeout=15)
    assert m['counts']['killed']==1
    campaign=build_campaign(old,new,mutation_record=m,mutation_root=src,replay_mutation=True,require_mutation=True)
    assert campaign['mutation']['status']=='selected_mutants_detected'
    assert campaign['decision']['status']=='bounded_architecture_policy_pass'
    assert verify_campaign(campaign,old,new,mutation_root=src,replay_mutation=True)['status']=='verified'
    with pytest.raises(ValueError,match='requires source root'):
        verify_campaign(campaign,old,new)
    (src/'pkg'/'value.py').write_text('def is_allowed(v):\n    return v != 7\n')
    with pytest.raises(ValueError,match='Live workspace|not bound'):
        verify_campaign(campaign,old,new,mutation_root=src,replay_mutation=True)


def test_surviving_mutants_trigger_review(tmp_path):
    src=tmp_path/'src';src.mkdir();(src/'tests').mkdir()
    (src/'prod.py').write_text('import stable\ndef predicate(v):\n    return v == 7\n')
    (src/'stable.py').write_text('')
    (src/'tests'/'test_prod.py').write_text('from prod import predicate\ndef test_weak():\n    assert callable(predicate)\n')
    old=tmp_path/'old';new=tmp_path/'new'
    labels={'prod':'production','stable':'stable','tests.test_prod':'stable'}
    audit_repository(src,old,lifecycle=labels,policy_file=POLICY)
    audit_repository(src,new,lifecycle=labels,policy_file=POLICY)
    m=run_experiment(src,['prod.py'],['tests/test_prod.py'],max_mutants=1,timeout=15)
    assert m['counts']['survived']==1
    r=build_campaign(old,new,mutation_record=m,mutation_root=src,replay_mutation=True)
    assert r['decision']['status']=='test_effectiveness_review_required'


def test_mutation_impact_provenance_reverified_against_sealed_generations(tmp_path):
    from audit_engine.semantic_audit.ae03.impact import verified_impact
    src=tmp_path/'src';src.mkdir();(src/'tests').mkdir()
    (src/'prod.py').write_text('import stable\ndef condition(v):\n    return v == 7\n')
    (src/'stable.py').write_text('v=1\n')
    (src/'tests'/'test_prod.py').write_text('from prod import condition\ndef test_v():\n    assert condition(7)\n    assert not condition(5)\n')
    labels={'prod':'production','stable':'stable','tests.test_prod':'stable'}
    old=tmp_path/'old';new=tmp_path/'new'
    audit_repository(src,old,lifecycle=labels,policy_file=POLICY)
    (src/'prod.py').write_text('import stable\ndef condition(v):\n    return v == 7 # revised\n')
    audit_repository(src,new,lifecycle=labels,policy_file=POLICY)
    context=verified_impact(old,new)
    m=run_experiment(src,['prod.py'],['tests/test_prod.py'],max_mutants=1,impact=context,timeout=15)
    assert m['impact_provenance']['comparison_sha256']==context.to_dict()['comparison_sha256']
    r=build_campaign(old,new,mutation_record=m,mutation_root=src,replay_mutation=True)
    assert r['mutation']['status']=='selected_mutants_detected'
    assert r['decision']['status']=='change_review_required'
    assert verify_campaign(r,old,new,mutation_root=src,replay_mutation=True)['status']=='verified'
    forged=copy.deepcopy(m)
    forged['impact_provenance']['comparison_sha256']='0'*64
    forged['record_sha256']=sha(canonical({k:v for k,v in forged.items() if k!='record_sha256'}))
    with pytest.raises(ValueError,match='does not match independently'):
        build_campaign(old,new,mutation_record=forged,mutation_root=src,replay_mutation=True)


def test_symlinked_published_report_is_rejected_even_if_bytes_match(tmp_path):
    _,old,new=setup_clean(tmp_path)
    pub=publish_campaign(build_campaign(old,new),tmp_path/'campaign',before_output=old,after_output=new)
    original=tmp_path/'campaign'/'generations'/pub['generation']/'campaign.json'
    backup=tmp_path/'trusted_copy.json';backup.write_bytes(original.read_bytes())
    original.unlink();original.symlink_to(backup)
    with pytest.raises(ValueError,match='Symlink'):
        verify_publication(tmp_path/'campaign',before_output=old,after_output=new)


def test_failure_injected_final_pointer_commit_marks_attempt_failed(tmp_path,monkeypatch):
    import audit_engine.semantic_audit.ae04.publication as pubmodule
    _,old,new=setup_clean(tmp_path)
    report=build_campaign(old,new)
    write=pubmodule._atomic_bytes
    count={'completed':0}
    def glitch(path, content):
        if path.name=='LATEST.json' and b'"status":"completed"' in content and count['completed']==0:
            count['completed']+=1
            raise OSError('Injected commit failure')
        return write(path,content)
    monkeypatch.setattr(pubmodule,'_atomic_bytes',glitch)
    with pytest.raises(OSError,match='Injected commit'):
        publish_campaign(report,tmp_path/'campaign',before_output=old,after_output=new)
    assert json.loads((tmp_path/'campaign'/'LATEST.json').read_bytes())['status']=='failed'
    with pytest.raises(ValueError,match='not completed'):
        verify_publication(tmp_path/'campaign',before_output=old,after_output=new)
