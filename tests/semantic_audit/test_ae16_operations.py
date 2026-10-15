"""AE-16 independent positive, negative, evidence-tamper, and uncertainty controls."""
from __future__ import annotations
import json
import os
import stat
from copy import deepcopy
from pathlib import Path
import pytest

from audit_engine.semantic_audit.ae01.publication import canonical,sha
from audit_engine.semantic_audit.ae16 import build_report,publish_observation,verify_observation


def declaration():
    return {'schema':'ae16/declared_execution/v1','run_id':'controlled-run-1',
            'reported_status':'success',
            'jobs':[
                {'id':'build','status':'success','needs':[],
                 'steps':[{'id':'tests','status':'success','exit_code':0,'log':'logs/build.txt',
                           'checks':[{'id':'regression','status':'passed','tests':[
                               {'id':'positive','expected':'passed','observed':'passed'},
                               {'id':'negative_fixture','expected':'failed','observed':'failed'}]}],
                           'produces':[{'id':'test-report','path':'produce/report.json'}], 'consumes':[]}]},
                {'id':'deploy','status':'success','needs':['build'],
                 'steps':[{'id':'inspect','status':'success','exit_code':0,'log':'logs/deploy.txt',
                           'checks':[{'id':'contract','status':'passed','tests':[
                               {'id':'artifact_matches','expected':'passed','observed':'passed'}]}],
                           'produces':[], 'consumes':[{'id':'test-report','path':'receive/report.json'}]}]},
            ],
            'requirements':[{'id':'r-regression','job':'build','step':'tests','check':'regression'},
                            {'id':'r-contract','job':'deploy','step':'inspect','check':'contract'}]}


def write_decl(path,record):
    path.write_bytes(canonical(record))


@pytest.fixture
def lab(tmp_path):
    root=tmp_path/'evidence'
    (root/'logs').mkdir(parents=True)
    (root/'produce').mkdir()
    (root/'receive').mkdir()
    # Deliberate negative test mention inside successful outer job.
    (root/'logs/build.txt').write_text('FAILED tests/test_negative.py::expected_error\n2 passed, 1 xfailed\n')
    (root/'logs/deploy.txt').write_text('Declared step exit=0\n')
    (root/'produce/report.json').write_bytes(b'{"fixture":"same bytes"}\n')
    (root/'receive/report.json').write_bytes(b'{"fixture":"same bytes"}\n')
    declaration_file=tmp_path/'run.json'
    write_decl(declaration_file,declaration())
    return root,declaration_file,tmp_path/'out'


def analyze(root,decl):return build_report(decl,root)


def test_successful_outer_job_can_contain_expected_negative_test(lab):
    root,decl,_=lab
    report,graph=analyze(root,decl)
    assert report['assurance']=='consistent_declared_observations_unattested'
    assert report['reported_status']=='success'
    assert report['source_authority']=='untrusted_execution_declaration_not_github_authenticated'
    assert report['verified_findings']==[]
    assert report['coverage_summary']=={'required':2,'observed_pass_claims':2}
    assert any(e['relation']=='PRODUCES' for e in graph['edges'])
    assert any(e['relation']=='CONSUMES' for e in graph['edges'])
    assert any(e['relation']=='NEEDS_JOB' for e in graph['edges'])
    assert any(e['relation']=='HAS_NESTED_TEST' for e in graph['edges'])


def test_publication_replay_and_idempotence(lab):
    root,decl,out=lab
    first=publish_observation(decl,root,out)
    assert first['verification']=='independent_replay_of_supplied_evidence_not_authenticated_execution'
    assert first['observed_pass_claims']==2
    assert verify_observation(decl,root,out)==first
    assert publish_observation(decl,root,out)==first
    assert len(list((out/'generations').iterdir()))==1


def test_required_check_missing_never_clean(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['checks'].clear();write_decl(decl,d)
    result,_=analyze(root,decl)
    assert result['assurance']=='incomplete_or_inconsistent'
    assert result['coverage_summary']['observed_pass_claims']==1
    assert 'required_check_not_executed' in {i['kind'] for i in result['issues']}


def test_no_required_check_contract_never_clean(lab):
    root,decl,_=lab
    d=declaration();d['requirements']=[];write_decl(decl,d)
    report,_=analyze(root,decl)
    assert report['assurance']=='incomplete_or_inconsistent'
    assert 'no_required_check_contract' in {i['kind'] for i in report['issues']}


def test_all_skipped_check_never_clean(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['checks'][0]['status']='skipped';write_decl(decl,d)
    report,_=analyze(root,decl)
    assert report['assurance']=='incomplete_or_inconsistent'
    assert report['coverage_summary']['observed_pass_claims']==1


def test_claimed_success_with_nonzero_exit_is_inconsistent(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['exit_code']=3;write_decl(decl,d)
    report,_=analyze(root,decl)
    assert 'claimed_success_without_zero_exit' in {i['kind'] for i in report['issues']}


def test_failed_nested_test_unexpected_must_not_count_as_success(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['checks'][0]['tests'][1]['expected']='passed'
    write_decl(decl,d)
    report,_=analyze(root,decl)
    assert report['assurance']=='incomplete_or_inconsistent'
    assert report['coverage_summary']['observed_pass_claims']==1
    assert 'nested_test_outcome_mismatch' in {i['kind'] for i in report['issues']}


def test_duplicate_nested_test_identity_refused(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['checks'][0]['tests'][1]['id']='positive';write_decl(decl,d)
    with pytest.raises(ValueError,match='Duplicate nested test'):analyze(root,decl)


def test_missing_artifact_producer_explicitly_incomplete(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][1]['steps'][0]['consumes'][0]['id']='unknown';write_decl(decl,d)
    report,_=analyze(root,decl)
    assert report['assurance']=='incomplete_or_inconsistent'
    assert 'consumer_without_declared_producer' in {i['kind'] for i in report['issues']}


def test_consumer_digest_mismatch_explicit(lab):
    root,decl,_=lab
    (root/'receive/report.json').write_bytes(b'changed payload')
    report,_=analyze(root,decl)
    assert report['assurance']=='incomplete_or_inconsistent'
    assert 'producer_consumer_content_mismatch' in {i['kind'] for i in report['issues']}


def test_missing_cross_job_needs_explicit(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][1]['needs']=[];write_decl(decl,d)
    report,_=analyze(root,decl)
    assert 'missing_producer_job_dependency' in {i['kind'] for i in report['issues']}


def test_cyclic_job_needs_refused(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['needs']=['deploy'];write_decl(decl,d)
    with pytest.raises(ValueError,match='Cyclic'):analyze(root,decl)


def test_missing_log_reduces_coverage(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['log']=None;write_decl(decl,d)
    report,_=analyze(root,decl)
    assert report['coverage_summary']['observed_pass_claims']==1
    assert 'executed_step_missing_log' in {i['kind'] for i in report['issues']}


def test_symlink_evidence_rejected(lab):
    root,decl,_=lab
    p=root/'logs/build.txt';p.unlink();p.symlink_to(root/'logs/deploy.txt')
    with pytest.raises(ValueError,match='Symlink'):analyze(root,decl)


def test_fifo_evidence_rejected_without_reading(lab):
    if not hasattr(os,'mkfifo'):pytest.skip('FIFO not supported')
    root,decl,_=lab
    p=root/'logs/build.txt';p.unlink();os.mkfifo(p)
    with pytest.raises(ValueError,match='nonregular'):analyze(root,decl)


@pytest.mark.parametrize('unsafe',['../outside','/tmp/outside','logs/../inside','logs//inside','C:/windows','logs\\file'])
def test_unsafe_log_paths_rejected(lab,unsafe):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['log']=unsafe;write_decl(decl,d)
    with pytest.raises(ValueError,match='Unsafe'):analyze(root,decl)


def test_reject_unsupported_manifest_fields_not_silent(lab):
    root,decl,_=lab
    d=declaration();d['jobs'][0]['steps'][0]['ignore_failures']=True;write_decl(decl,d)
    with pytest.raises(ValueError,match='unsupported keys'):analyze(root,decl)


def test_changed_log_invalidates_sealed_observations(lab):
    root,decl,out=lab
    publish_observation(decl,root,out)
    (root/'logs/build.txt').write_text('changed after publication')
    with pytest.raises(ValueError,match='independently replayed'):verify_observation(decl,root,out)


def test_changed_artifact_invalidates_sealed_observations(lab):
    root,decl,out=lab
    publish_observation(decl,root,out)
    (root/'produce/report.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='independently replayed'):verify_observation(decl,root,out)


def test_resealed_forged_report_rejected_by_replay(lab):
    root,decl,out=lab
    pub=publish_observation(decl,root,out)
    folder=out/'generations'/pub['generation']
    document=json.loads((folder/'report.json').read_bytes())
    document['verified_findings']=[{'fake':'confirmed'}]
    (folder/'report.json').write_bytes(canonical(document))
    seal={'schema':'ae16/observation_seal/v1','artifacts':{
        'report.json':sha(canonical(document)),
        'graph.json':sha((folder/'graph.json').read_bytes())}}
    (folder/'SEAL.json').write_bytes(canonical(seal))
    (out/'LATEST.json').write_bytes(canonical({'status':'completed','generation':pub['generation'],
                                                'seal_sha256':sha(canonical(seal))}))
    with pytest.raises(ValueError):verify_observation(decl,root,out)


def test_failed_last_attempt_blocks_old_success(lab):
    root,decl,out=lab
    publish_observation(decl,root,out)
    d=declaration();d['jobs'][0]['steps'][0]['log']='../invalid.log';write_decl(decl,d)
    with pytest.raises(ValueError,match='Unsafe'):publish_observation(decl,root,out)
    with pytest.raises(ValueError,match='not completed'):verify_observation(decl,root,out)


def test_source_binding_cannot_be_half_enabled(lab):
    root,decl,_=lab
    with pytest.raises(ValueError,match='requires both'):build_report(decl,root,ae01_output=root)


def test_untrusted_declaration_bytes_cannot_change_after_publication(lab):
    root,decl,out=lab
    publish_observation(decl,root,out)
    d=declaration();d['run_id']='new-run-id';write_decl(decl,d)
    with pytest.raises(ValueError):verify_observation(decl,root,out)


def test_noncanonical_json_rejected(lab):
    root,decl,_=lab
    decl.write_text(json.dumps(declaration(),indent=2))
    with pytest.raises(ValueError,match='canonical JSON'):analyze(root,decl)


def test_optional_ae09_source_correlation_is_not_proof_of_root_cause(lab,tmp_path):
    from audit_engine.semantic_audit.ae01.pipeline import audit_repository
    root,decl,_=lab
    src=tmp_path/'src';(src/'pkg').mkdir(parents=True)
    (src/'pkg'/'__init__.py').write_text('')
    (src/'pkg'/'entry.py').write_text('def start():\n    raise RuntimeError("controlled")\n')
    policy=Path(__file__).resolve().parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
    audit=tmp_path/'ae01'
    audit_repository(src,audit,lifecycle={'pkg':'production','pkg.entry':'production'},policy_file=policy)
    (root/'logs/build.txt').write_text('Traceback (most recent call last):\n  File "/runner/pkg/entry.py", line 2, in start\nRuntimeError: controlled\n')
    report,_=build_report(decl,root,ae01_output=audit,source_root=src)
    assert len(report['source_correlations'])==2
    assert report['source_correlations'][0]['frames']==1
    assert report['source_correlations'][0]['conclusion']=='review_hypotheses_only_not_proven_root_cause'
    assert report['verified_findings']==[]


def test_missing_produced_artifact_is_recorded_as_incomplete_not_clean(lab):
    root,decl,_=lab
    (root/'produce/report.json').unlink()
    report,graph=analyze(root,decl)
    assert report['assurance']=='incomplete_or_inconsistent'
    assert 'missing_evidence_file' in {i['kind'] for i in report['issues']}
    assert any(e['relation']=='DECLARES_PRODUCTION' for e in graph['edges'])


def test_missing_declared_step_log_cannot_validate_required_check(lab):
    root,decl,_=lab
    (root/'logs/build.txt').unlink()
    report,_=analyze(root,decl)
    assert report['assurance']=='incomplete_or_inconsistent'
    assert report['coverage_summary']['observed_pass_claims']==1


def test_binary_log_not_admitted_as_evidence(lab):
    root,decl,_=lab
    (root/'logs/build.txt').write_bytes(b'\x00\xff')
    with pytest.raises(ValueError,match='Binary'):analyze(root,decl)


def test_duplicate_json_object_keys_rejected(lab):
    root,decl,_=lab
    blob=decl.read_bytes()
    # Repeat an existing property while preserving syntactically valid JSON.
    decl.write_bytes(blob.replace(b'"schema":',b'"schema":"ae16/declared_execution/v1","schema":',1))
    with pytest.raises(ValueError,match='Duplicate JSON property'):analyze(root,decl)
