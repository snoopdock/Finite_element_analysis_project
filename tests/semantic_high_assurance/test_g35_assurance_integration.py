"""G3.5 real integration, source-binding and adversarial closure tests."""
from __future__ import annotations
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from decision_memory import assurance_integration as gate  # noqa:E402
from decision_memory import human_adjudication as adjud  # noqa:E402

DEC = 'DEC-G3.4.13-001'
ACTION = 'ACTION-G3.4.15-001'
OUTCOME = 'OUTCOME-G3.4.16-001'
RULE = 'RULE-G3.4.17-001'
QUERY = 'engineering decision validation'
DRAFT = f'Rationale must be reviewed [[{DEC}]]\nAction is still pending [[{ACTION}]]'

@pytest.fixture
def repo(tmp_path):
    r = tmp_path / 'checked-out-source'
    r.mkdir()
    for folder in ('decision_memory', 'validation'):
        shutil.copytree(ROOT / folder, r / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return r


def generate(repo, draft=DRAFT, query=QUERY):
    return gate.create_cycle(repo, query, draft)


def review_for(record, idx=0, verdict='insufficient_evidence'):
    dossier = record['dossier']
    claim = dossier['claim_reviews'][idx]
    return {
        'schema_version': adjud.SUBMISSION_SCHEMA,
        'dossier_sha256': dossier['dossier_sha256'],
        'reviewer_label': 'external-self-label',
        'assessments': [{
            'claim_index': claim['claim_index'],
            'claim_sha256': claim['claim_sha256'],
            'verdict': verdict,
            'rationale': 'This cannot establish independent engineering validity without further evidence.',
            'reviewed_source_ids': list(claim['resolved_record_ids']),
        }],
    }


def test_complete_chain_end_to_end(repo):
    r = generate(repo)
    assert r['schema_version'] == gate.SCHEMA
    assert r['audit']['audit_sha256'] == r['dossier']['proposal_audit_sha256']
    assert r['audit']['retrieval_context_sha256'] == r['dossier']['retrieval_context_sha256']
    assert r['summary']['claims'] == 2
    assert r['summary']['resolved_citation_edges'] == 2
    assert gate.verify_cycle(r, repo)


def test_graph_handoff_has_typed_nodes_and_citation_edges(repo):
    graph = generate(repo)['graph_handoff']
    assert graph['schema_version'] == 'sat-audit-graph-handoff/v1'
    assert len([x for x in graph['nodes'] if x['type']=='generated_claim']) == 2
    assert len(graph['edges']) == 2
    assert all(e['type'] == 'cites_structurally' and not e['semantic_entailment_verified'] for e in graph['edges'])
    assert len({n['id'] for n in graph['nodes']}) == len(graph['nodes'])
    assert not graph['authoritative_graph_mutation_permitted']


def test_sources_are_bound_to_file_bytes(repo):
    graph = generate(repo)['graph_handoff']
    for n in graph['nodes']:
        if n['type'] == 'memory_record':
            assert n['source_sha256'] == hashlib.sha256((repo/n['source_path']).read_bytes()).hexdigest()
            assert not n['support_verified']


def test_history_conflict_routed_for_review(repo):
    r = generate(repo)
    assert 'reconcile_historical_outcome' in r['review_routes'][1]['required_next_steps']
    assert not r['review_routes'][1]['eligible_for_automatic_approval']


def test_candidate_learning_rule_unapproved(repo):
    r = generate(repo, f'Recommendation from candidate [[{RULE}]]')
    assert 'review_candidate_rule' in r['review_routes'][0]['required_next_steps']
    assert not r['graph_handoff']['projection_is_semantic_entailment']


def test_uncited_claim_routed_for_correction(repo):
    r = generate(repo, 'A statement without a citation')
    assert r['summary']['resolved_citation_edges'] == 0
    assert r['review_routes'][0]['trace_status'] == 'uncited'
    assert 'add_explicit_citation' in r['review_routes'][0]['required_next_steps']


def test_unresolved_reference_routed_not_invented(repo):
    r = generate(repo, 'Unknown assertion [[DEC-G9.9.9-999]]')
    assert r['graph_handoff']['edges'] == []
    assert 'resolve_citation_identifier' in r['review_routes'][0]['required_next_steps']


def test_outcome_conflict_surfaces(repo):
    r = generate(repo, f'Successful feedback despite pending action [[{OUTCOME}]]')
    assert 'reconcile_historical_outcome' in r['review_routes'][0]['required_next_steps']


def test_deterministic_without_clock(repo):
    a = generate(repo)
    b = generate(repo)
    assert a == b
    assert a['cycle_sha256'] == gate._digest({k:v for k,v in a.items() if k != 'cycle_sha256'})


def test_draft_change_updates_identity(repo):
    a = generate(repo)
    b = generate(repo, DRAFT+'\nOther claim')
    assert a['cycle_sha256'] != b['cycle_sha256']
    assert a['draft_sha256'] != b['draft_sha256']


def test_source_edit_invalidates_previous_cycle(repo):
    a = generate(repo)
    src = repo / f'decision_memory/decisions/{DEC}.yaml'
    src.write_text(src.read_text()+'\n# changed bytes\n')
    with pytest.raises(gate.AssuranceIntegrationError):
        gate.verify_cycle(a,repo)


@pytest.mark.parametrize('field,value',[
    ('profile_id','G9.9'), ('schema_version','wrong'), ('source_commit_sha','fake'),
])
def test_forged_top_level_fields_rejected(repo,field,value):
    a = generate(repo)
    a[field] = value
    with pytest.raises(gate.AssuranceIntegrationError):gate.verify_cycle(a,repo)


def test_forged_graph_edge_rejected_even_if_digest_recomputed(repo):
    r=generate(repo)
    r['graph_handoff']['edges'][0]['type']='proves'
    r['cycle_sha256']=gate._digest({k:v for k,v in r.items() if k != 'cycle_sha256'})
    with pytest.raises(gate.AssuranceIntegrationError):gate.verify_cycle(r,repo)


def test_forged_authorization_rejected_even_if_digest_recomputed(repo):
    r=generate(repo)
    r['authorization']['automatic_sat_action_allowed']=True
    r['cycle_sha256']=gate._digest({k:v for k,v in r.items() if k != 'cycle_sha256'})
    with pytest.raises(gate.AssuranceIntegrationError):gate.verify_cycle(r,repo)


def test_review_annotations_remain_unverified(repo):
    base=generate(repo)
    sub=review_for(base)
    r=gate.create_cycle(repo,QUERY,DRAFT,review_submission=sub,github_actor='github-actor')
    assert r['review_annotations']['summary']['reviewed_claims']==1
    assert r['review_routes'][0]['reviewer_verdict_unverified']=='insufficient_evidence'
    assert 'gather_independent_evidence' in r['review_routes'][0]['required_next_steps']
    assert not any(r['authorization'].values())
    assert gate.verify_cycle(r,repo,review_submission=sub,github_actor='github-actor')


def test_positive_human_opinion_still_not_authorize(repo):
    sub=review_for(generate(repo),verdict='supported_by_reviewer')
    r=gate.create_cycle(repo,QUERY,DRAFT,review_submission=sub)
    assert not any(r['authorization'].values())
    assert not r['review_routes'][0]['scientific_truth_established']
    assert 'independently_assess_semantic_support' in r['review_routes'][0]['required_next_steps']


def test_changed_review_submission_rejected(repo):
    sub=review_for(generate(repo))
    r=gate.create_cycle(repo,QUERY,DRAFT,review_submission=sub)
    sub['assessments'][0]['rationale']='Different independent assessment rationale requiring more work.'
    with pytest.raises(gate.AssuranceIntegrationError):gate.verify_cycle(r,repo,review_submission=sub)


def test_review_required_for_verifying_reviewed_record(repo):
    sub=review_for(generate(repo))
    r=gate.create_cycle(repo,QUERY,DRAFT,review_submission=sub)
    with pytest.raises(gate.AssuranceIntegrationError):gate.verify_cycle(r,repo)


def test_unreviewed_record_rejects_review_substitution(repo):
    plain=generate(repo)
    with pytest.raises(gate.AssuranceIntegrationError):
        gate.verify_cycle(plain, repo, review_submission=review_for(plain))


def test_malformed_review_does_not_produce_cycle(repo):
    sub=review_for(generate(repo));sub['assessments'][0]['claim_sha256']='0'*64
    with pytest.raises(gate.AssuranceIntegrationError):gate.create_cycle(repo,QUERY,DRAFT,review_submission=sub)


def test_invalid_reviewer_actor_rejected(repo):
    sub=review_for(generate(repo))
    with pytest.raises(gate.AssuranceIntegrationError):
        gate.create_cycle(repo,QUERY,DRAFT,review_submission=sub,github_actor='x\x00bad')


def test_repo_files_unchanged_by_generation(repo):
    a={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest()
       for p in repo.rglob('*') if p.is_file()}
    generate(repo)
    b={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest()
       for p in repo.rglob('*') if p.is_file()}
    assert a==b


def test_read_json_reject_duplicate_keys(tmp_path):
    p=tmp_path/'x.json';p.write_text('{"x":1,"x":2}')
    with pytest.raises(gate.AssuranceIntegrationError):gate._read_json(p)


def test_read_json_reject_nonfinite(tmp_path):
    p=tmp_path/'x.json';p.write_text('{"x":NaN}')
    with pytest.raises(gate.AssuranceIntegrationError):gate._read_json(p)


def test_read_json_reject_symlink(tmp_path):
    p=tmp_path/'good.json';p.write_text('{}')
    l=tmp_path/'link.json';l.symlink_to(p)
    with pytest.raises(gate.AssuranceIntegrationError):gate._read_json(l)


def test_oversized_draft_rejected(tmp_path):
    p=tmp_path/'draft.txt';p.write_text('x'*(gate.MAX_INPUT_BYTES+1))
    with pytest.raises(gate.AssuranceIntegrationError):gate._read_draft(p)


def test_cli_end_to_end_external_output(repo,tmp_path):
    draft=tmp_path/'draft.txt';draft.write_text(DRAFT)
    out=tmp_path/'cycle.json'
    cmd=[sys.executable,'-m','decision_memory.assurance_integration','--repository',str(repo),
         '--query',QUERY,'--draft-file',str(draft),'--output',str(out)]
    call=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=40)
    assert call.returncode == 0,call.stderr
    assert out.is_file()
    parsed=json.loads(out.read_text())
    assert gate.verify_cycle(parsed,repo)
    verify=[sys.executable,'-m','decision_memory.assurance_integration',
            '--repository',str(repo),'--verify-file',str(out)]
    v=subprocess.run(verify,cwd=ROOT,capture_output=True,text=True,timeout=40)
    assert v.returncode == 0,v.stderr
    assert 'no engineering approval' in v.stdout


def test_cli_refuses_output_into_repository(repo,tmp_path):
    draft=tmp_path/'draft.txt';draft.write_text(DRAFT)
    cmd=[sys.executable,'-m','decision_memory.assurance_integration','--repository',str(repo),
         '--query',QUERY,'--draft-file',str(draft),'--output',str(repo/'forbidden.json')]
    v=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=40)
    assert v.returncode != 0
    assert not (repo/'forbidden.json').exists()


def test_cli_rejects_mutated_report_even_with_updated_digest(repo,tmp_path):
    out=tmp_path/'cycle.json';r=generate(repo)
    r['review_routes'][0]['required_next_steps']=['publish']
    r['cycle_sha256']=gate._digest({k:v for k,v in r.items() if k!='cycle_sha256'})
    out.write_text(json.dumps(r))
    cmd=[sys.executable,'-m','decision_memory.assurance_integration','--repository',str(repo),'--verify-file',str(out)]
    v=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=40)
    assert v.returncode != 0


def test_profile_declares_full_regression():
    text=(ROOT/'validation/profiles/G3.5.yaml').read_text()
    assert 'regression:' in text and 'enabled: true' in text
    assert 'test_g35_assurance_integration.py' in text
