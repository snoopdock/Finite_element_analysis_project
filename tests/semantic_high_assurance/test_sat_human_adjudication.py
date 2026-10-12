"""G3.4.21 adversarial validation of untrusted human review data."""
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
from decision_memory import proposal_audit as audits
from decision_memory import review_dossier as dossiers
from decision_memory import human_adjudication as adjud

DEC='DEC-G3.4.13-001'
ACT='ACTION-G3.4.15-001'
RULE='RULE-G3.4.17-001'

@pytest.fixture
def repo(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    for sub in ('decision_memory','validation'):
        shutil.copytree(ROOT/sub,root/sub,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    return root

def sample(repo,text=None):
    if text is None:
        text=f'Engineering decisions preserve rationale [[{DEC}]]\nAction pending independent review [[{ACT}]]'
    audit=audits.audit(repo,'engineering decision validation',text)
    dossier=dossiers.create_dossier(repo,audit)
    claim=dossier['claim_reviews'][0]
    submission={'schema_version':adjud.SUBMISSION_SCHEMA,'dossier_sha256':dossier['dossier_sha256'],
       'reviewer_label':'reviewer-self-declared','assessments':[{
          'claim_index':claim['claim_index'],'claim_sha256':claim['claim_sha256'],
          'verdict':'insufficient_evidence',
          'rationale':'The local decision record alone is not sufficient to establish the claim.',
          'reviewed_source_ids':claim['resolved_record_ids']} ]}
    return audit,dossier,submission

def test_read_only_unverified_report(repo):
    a,d,s=sample(repo)
    result=adjud.create_annotations(repo,a,d,s,'github-actor')
    assert result['schema_version']==adjud.REPORT_SCHEMA
    assert result['summary']['review_completeness']=='partial'
    assert result['summary']['reviewed_claims']==1
    assert result['summary']['unreviewed_claims']==1
    assert all(x is False for x in result['approval'].values())
    assert all(x is False for x in result['execution_constraints'].values())
    assert all(x['independent_semantic_entailment_verified'] is False for x in result['reviews'])
    assert adjud.verify_annotations(result,repo,a,d,s,'github-actor')

def test_complete_review_still_not_approved(repo):
    a,d,s=sample(repo)
    claim=d['claim_reviews'][1]
    s['assessments'].append({'claim_index':claim['claim_index'],'claim_sha256':claim['claim_sha256'],
       'verdict':'needs_revision','rationale':'Action remains pending and cannot be called successfully completed.',
       'reviewed_source_ids':claim['resolved_record_ids']})
    obj=adjud.create_annotations(repo,a,d,s)
    assert obj['summary']['review_completeness']=='complete'
    assert not any(obj['approval'].values())

def test_positive_human_opinion_cannot_authorize(repo):
    a,d,s=sample(repo,f'This record preserves rationale [[{DEC}]]')
    s['assessments'][0]['verdict']='supported_by_reviewer'
    obj=adjud.create_annotations(repo,a,d,s)
    assert obj['reviews'][0]['reviewer_verdict_unverified']=='supported_by_reviewer'
    assert obj['approval']['sat_action_authorized'] is False
    assert obj['summary']['semantic_truth_verified_by_software'] is False

@pytest.mark.parametrize('bad',['approved','proven','',12,None,'yes'])
def test_reject_unsupported_verdict(repo,bad):
    a,d,s=sample(repo);s['assessments'][0]['verdict']=bad
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

@pytest.mark.parametrize('bad',['too short','',123,None,' x'*1100,' '+'q'*30])
def test_reject_invalid_rationale(repo,bad):
    a,d,s=sample(repo);s['assessments'][0]['rationale']=bad
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

@pytest.mark.parametrize('bad',[0,False,-1,999,'1'])
def test_invalid_claim_number(repo,bad):
    a,d,s=sample(repo);s['assessments'][0]['claim_index']=bad
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

@pytest.mark.parametrize('field,value', [('dossier_sha256','0'*64),('schema_version','wrong')])
def test_stale_binding(repo,field,value):
    a,d,s=sample(repo);s[field]=value
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_stale_claim_digest(repo):
    a,d,s=sample(repo);s['assessments'][0]['claim_sha256']='f'*64
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_duplicate_reviews_rejected(repo):
    a,d,s=sample(repo);s['assessments'].append(copy.deepcopy(s['assessments'][0]))
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_extra_submission_key_rejected(repo):
    a,d,s=sample(repo);s['auto_approve']=True
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_extra_assessment_key_rejected(repo):
    a,d,s=sample(repo);s['assessments'][0]['semantic_truth']=True
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_no_assessments_rejected(repo):
    a,d,s=sample(repo);s['assessments']=[]
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_forged_source_id_rejected(repo):
    a,d,s=sample(repo);s['assessments'][0]['reviewed_source_ids']=['DEC-G9.9.9-999']
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_duplicate_source_id_rejected(repo):
    a,d,s=sample(repo);s['assessments'][0]['reviewed_source_ids']=[DEC,DEC]
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

@pytest.mark.parametrize('text', ['Uncited assertion','Invalid citation [[DEC-G9.9.9-999]]',f'Action is completed [[{ACT}]]',f'Rule is approved [[{RULE}]]'])
def test_positive_verdict_cannot_override_blockers(repo,text):
    a,d,s=sample(repo,text);s['assessments'][0]['verdict']='supported_by_reviewer'
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_tampered_dossier_rejected(repo):
    a,d,s=sample(repo);d['claim_reviews'][0]['claim_text_untrusted']='tampered'
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_changed_record_bytes_rejected(repo):
    a,d,s=sample(repo)
    p=repo/'decision_memory/decisions'/f'{DEC}.yaml';p.write_text(p.read_text()+'\n# alteration\n')
    with pytest.raises(adjud.AdjudicationError):adjud.create_annotations(repo,a,d,s)

def test_modification_of_report_rejected(repo):
    a,d,s=sample(repo);r=adjud.create_annotations(repo,a,d,s)
    r['summary']['review_completeness']='complete'
    with pytest.raises(adjud.AdjudicationError):adjud.verify_annotations(r,repo,a,d,s)

def test_rehashed_forged_approval_rejected(repo):
    a,d,s=sample(repo);r=adjud.create_annotations(repo,a,d,s)
    r['approval']['sat_action_authorized']=True
    r['annotations_sha256']=adjud._hash({k:v for k,v in r.items() if k!='annotations_sha256'})
    with pytest.raises(adjud.AdjudicationError):adjud.verify_annotations(r,repo,a,d,s)

def test_rehashed_forged_assessment_rejected(repo):
    a,d,s=sample(repo);r=adjud.create_annotations(repo,a,d,s)
    r['reviews'][0]['reviewer_verdict_unverified']='supported_by_reviewer'
    r['annotations_sha256']=adjud._hash({k:v for k,v in r.items() if k!='annotations_sha256'})
    with pytest.raises(adjud.AdjudicationError):adjud.verify_annotations(r,repo,a,d,s)

def test_actor_substitution_rejected(repo):
    a,d,s=sample(repo);r=adjud.create_annotations(repo,a,d,s,'actor-one')
    with pytest.raises(adjud.AdjudicationError):adjud.verify_annotations(r,repo,a,d,s,'actor-two')

def test_deterministic(repo):
    a,d,s=sample(repo)
    assert adjud.create_annotations(repo,a,d,s)==adjud.create_annotations(repo,a,d,s)

def run_cli(repo,tmp_path,change=None):
    a,d,s=sample(repo)
    out=tmp_path/'artifacts';out.mkdir()
    for key,data in (('audit',a),('dossier',d),('review',s)):
        (out/f'{key}.json').write_text(json.dumps(data))
    if change:change(out)
    exe=ROOT/'decision_memory/human_adjudication.py'
    args=['--repository',str(repo),'--audit-file',str(out/'audit.json'),
      '--dossier-file',str(out/'dossier.json'),'--review-file',str(out/'review.json'),
      '--github-actor','github-ci']
    return out,exe,args

def test_cli_generate_verify_and_no_source_write(repo,tmp_path):
    out,exe,args=run_cli(repo,tmp_path)
    snapshot={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in repo.rglob('*') if p.is_file()}
    r=subprocess.run([sys.executable,str(exe),*args,'--output',str(out/'annotation.json')],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    r=subprocess.run([sys.executable,str(exe),*args,'--verify-file',str(out/'annotation.json')],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    after={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in repo.rglob('*') if p.is_file()}
    assert snapshot==after

def test_cli_refuses_repository_write(repo,tmp_path):
    out,exe,args=run_cli(repo,tmp_path)
    target=repo/'forbidden.json'
    r=subprocess.run([sys.executable,str(exe),*args,'--output',str(target)],capture_output=True,text=True)
    assert r.returncode!=0 and not target.exists()

def test_cli_rejects_duplicate_json_keys(repo,tmp_path):
    def alter(out):
        (out/'review.json').write_text('{"schema_version":"a","schema_version":"b"}')
    out,exe,args=run_cli(repo,tmp_path,alter)
    r=subprocess.run([sys.executable,str(exe),*args,'--output',str(out/'x.json')],capture_output=True,text=True)
    assert r.returncode!=0

def test_cli_rejects_symlink_input(repo,tmp_path):
    def alter(out):
        (out/'review.json').rename(out/'real.json')
        (out/'review.json').symlink_to(out/'real.json')
    out,exe,args=run_cli(repo,tmp_path,alter)
    r=subprocess.run([sys.executable,str(exe),*args,'--output',str(out/'x.json')],capture_output=True,text=True)
    assert r.returncode!=0

def test_schema_restricts_approval(repo):
    schema=json.loads((ROOT/'decision_memory/human_adjudication_schema.json').read_text())
    assert schema['properties']['approval']['additionalProperties']['const'] is False
    assert schema['properties']['execution_constraints']['additionalProperties']['const'] is False
