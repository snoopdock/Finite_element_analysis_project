"""AE-23 adversarial source admission and attribution tests.

Fixtures are local Git histories created by this test; they are *not* authenticated
real-world bugs and target source is never imported/executed.
"""
from __future__ import annotations

import copy
import hashlib
import subprocess
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae23.admission import (
    admit, git_source, read_canonical, sha, validate_lock,
)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()


def source_ref(root: Path, commit: str, path: str) -> dict:
    blob = git(root, 'rev-parse', f'{commit}:{path}')
    source = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', blob])
    return {'commit':commit,'path':path,'git_blob_oid':blob,'sha256':sha(source)}


@pytest.fixture
def book(tmp_path):
    repo=tmp_path/'git';repo.mkdir()
    git(repo,'init','-q');git(repo,'config','user.name','Test Fixture');git(repo,'config','user.email','fixture@example.invalid')
    (repo/'alpha.py').write_text('def alpha(flag):\n    if flag:\n        result = 1\n    return result\n')
    (repo/'beta.py').write_text('def beta(items):\n    for n in items:\n        item = n\n    return item\n')
    git(repo,'add','.');git(repo,'commit','-qm','two intentional faulty programs')
    bad=git(repo,'rev-parse','HEAD')
    (repo/'alpha.py').write_text('def alpha(flag):\n    result = 0\n    if flag:\n        result = 1\n    return result\n')
    (repo/'beta.py').write_text('def beta(items):\n    item = None\n    for n in items:\n        item = n\n    return item\n')
    git(repo,'add','.');git(repo,'commit','-qm','two corrected programs')
    good=git(repo,'rev-parse','HEAD')
    lock={'schema':'ae23/external_case_lock/v1','dataset':'local_git_fixture',
          'repositories':{'sample':{'claimed_upstream_url':'https://example.invalid/local-fixture'}},
          'protocol':{'execution':'static_only','source_authority':'git_tree_integrity_only',
                     'review_policy':'two_distinct_reviewers_required_for_adjudicated_subset'},
          'cases':[
            {'case_id':cid,'repository':'sample','family':'possibly_unbound',
             'split':split,'scope':'bounded_static','signal_variable':variable,
             'faulty':source_ref(repo,bad,path),'correct':source_ref(repo,good,path)}
            for cid,path,split,variable in [('ALPHA','alpha.py','development','result'),
                                            ('BETA','beta.py','holdout','item')]]}
    path=tmp_path/'LOCK.json';path.write_bytes(canonical(lock))
    return {'repo':repo,'lock':lock,'path':path, 'map':{'sample':repo}}


def save(book, altered, tmp_path):
    p=tmp_path/'ALTERED.json';p.write_bytes(canonical(altered));return p


def test_exact_git_tree_identity_and_full_case_admission(book):
    a=admit(book['path'],book['map'])
    assert len(a['cases'])==2 and len(a['sources'])==4
    assert all(s['git_tree_binding']=='verified' for c in a['cases'] for s in c['source_bindings'].values())
    assert all(s['upstream_owner_authenticated'] is False for c in a['cases'] for s in c['source_bindings'].values())
    assert a['lock_sha256']==sha(book['path'].read_bytes())


def test_faulty_and_fixed_versions_are_distinct_exact_git_commits(book):
    for case in book['lock']['cases']:
        a,_=git_source(book['repo'],case['faulty'])
        b,_=git_source(book['repo'],case['correct'])
        assert a!=b
        assert hashlib.sha256(a).hexdigest()==case['faulty']['sha256']


def test_lock_noncanonical_json_rejected(book):
    book['path'].write_bytes(book['path'].read_bytes().rstrip(b'\n'))
    with pytest.raises(ValueError,match='canonical'):
        admit(book['path'],book['map'])


def test_mismatched_blob_object_rejected(book):
    alt=copy.deepcopy(book['lock'])
    alt['cases'][0]['faulty']['git_blob_oid']=alt['cases'][0]['correct']['git_blob_oid']
    with pytest.raises(ValueError,match='Declared blob'):
        admit(save(book,alt,book['path'].parent),book['map'])


def test_mismatched_checksum_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][0]['faulty']['sha256']='0'*64
    with pytest.raises(ValueError,match='SHA-256'):
        admit(save(book,alt,book['path'].parent),book['map'])


def test_wrong_commit_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][0]['faulty']['commit']='0'*40
    with pytest.raises(ValueError,match='Git source-reference'):
        admit(save(book,alt,book['path'].parent),book['map'])


def test_commit_not_aligned_to_blob_and_path(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][0]['faulty']['commit']=alt['cases'][0]['correct']['commit']
    with pytest.raises(ValueError,match='Declared blob'):
        admit(save(book,alt,book['path'].parent),book['map'])


def test_nonexistent_git_path_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][0]['faulty']['path']='missing.py'
    with pytest.raises(ValueError,match='not uniquely present'):
        admit(save(book,alt,book['path'].parent),book['map'])


def test_absolute_path_and_traversal_rejected(book):
    for unsafe in ('/tmp/other.py','../bad.py','nested/../../bad.py','x\\y.py','a//b.py'):
        alt=copy.deepcopy(book['lock']);alt['cases'][0]['faulty']['path']=unsafe
        with pytest.raises(ValueError):validate_lock(alt)


def test_duplicate_case_id_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][1]['case_id']=alt['cases'][0]['case_id']
    with pytest.raises(ValueError,match='Duplicate case'):validate_lock(alt)


def test_holdout_sha_leakage_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][1]['faulty']=copy.deepcopy(alt['cases'][0]['faulty'])
    with pytest.raises(ValueError,match='leakage'):validate_lock(alt)


def test_identical_faulty_and_correct_bytes_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][0]['correct']=copy.deepcopy(alt['cases'][0]['faulty'])
    with pytest.raises(ValueError,match='distinct bytes'):validate_lock(alt)


def test_invalid_claim_of_upstream_authentication_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['protocol']['source_authority']='authenticated_external_commit'
    with pytest.raises(ValueError,match='Protocol'):validate_lock(alt)


def test_unknown_repo_mapping_rejected(book):
    with pytest.raises(ValueError,match='exactly match'):
        admit(book['path'],{'another':book['repo']})


def test_symlinked_lock_rejected(book, tmp_path):
    p=tmp_path/'link.json'
    try:p.symlink_to(book['path'])
    except (OSError,NotImplementedError):pytest.skip('Symlink unavailable')
    with pytest.raises(ValueError):read_canonical(p)


def test_symlinked_repository_root_rejected(book, tmp_path):
    p=tmp_path/'linkrepo'
    try:p.symlink_to(book['repo'],target_is_directory=True)
    except (OSError,NotImplementedError):pytest.skip('Symlink unavailable')
    with pytest.raises(ValueError):admit(book['path'],{'sample':p})


def test_git_symlink_blob_is_not_accepted_as_python_source(book):
    repo=book['repo']; path=repo/'sym.py'
    try:path.symlink_to('alpha.py')
    except (OSError,NotImplementedError):pytest.skip('Symlink unavailable')
    git(repo,'add','sym.py');git(repo,'commit','-qm','link entry')
    commit=git(repo,'rev-parse','HEAD');oid=git(repo,'rev-parse',f'{commit}:sym.py')
    raw=subprocess.check_output(['git','-C',str(repo),'cat-file','blob',oid])
    with pytest.raises(ValueError,match='regular source file'):
        git_source(repo,{'commit':commit,'path':'sym.py','git_blob_oid':oid,'sha256':sha(raw)})


def test_extra_lock_field_rejected(book):
    alt=copy.deepcopy(book['lock']);alt['upstream_authenticated']=True
    with pytest.raises(ValueError,match='Unsupported reference lock'):validate_lock(alt)


def test_unsupported_semantics_requires_no_static_name(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][1]['scope']='unsupported_semantics'
    alt['cases'][1]['signal_variable']=None
    validate_lock(alt)


def test_case_scope_not_silently_overridden(book):
    alt=copy.deepcopy(book['lock']);alt['cases'][1]['scope']='mysterious'
    with pytest.raises(ValueError,match='split or static'):validate_lock(alt)

from audit_engine.semantic_audit.ae23.assessment import (
    REVIEW_SCHEMA, PREDICTION_SCHEMA, REPORT_SCHEMA, _static,
    evaluate, predict, replay_equivalent, score, validate_reviews,
)


def reviews_for(book, *, extra=False):
    lock_hash=sha(canonical(book['lock']))
    entries=[]
    for case in book['lock']['cases']:
        for i in (1,2):
            entries.append({'case_id':case['case_id'],'reviewer_id':f'reviewer_{i}',
                            'faulty':'defective','correct':'not_defective',
                            'rationale':'Reviewed the fixture source and intended failure path.',
                            'prediction_blinded':True})
    if extra:entries.append({'case_id':'ALPHA','reviewer_id':'reviewer_3',
                             'faulty':'defective','correct':'not_defective',
                             'rationale':'Additional self-attested review of code behavior.',
                             'prediction_blinded':True})
    return {'schema':REVIEW_SCHEMA,'lock_sha256':lock_hash,'reviews':entries}


def test_predict_does_not_access_label_file(book):
    a=predict(book['path'],book['map'])
    assert a['schema']==PREDICTION_SCHEMA
    assert a['label_access_during_prediction']=='NOT_READ'
    assert a['upstream_origin_authenticated'] is False
    assert a['verified_findings']==[]
    assert len(a['rows'])==2


def test_live_static_bridge_does_not_issue_verified_findings(book):
    a=predict(book['path'],book['map'])
    for row in a['rows']:
        assert row['faulty']['status'] in {'possible_unbound','unknown','no_unbound_signal'}
        assert row['correct']['status'] in {'possible_unbound','unknown','no_unbound_signal'}
        assert row['faulty']['source_sha256']==row['source_bindings']['faulty']['sha256']


def test_two_reviewer_scoring_preserves_all_denominators(book):
    pred=predict(book['path'],book['map'])
    report=score(pred,reviews_for(book))
    assert report['schema']==REPORT_SCHEMA
    assert report['sample_count']==4 and report['case_count']==2
    assert report['decided_samples']+report['unknown_samples']+report['unsupported_samples']+report['unadjudicated_samples']==4
    assert report['verified_findings']==[] and report['verified_root_causes']==[]
    assert report['upstream_origin_authenticated'] is False
    assert report['by_split']['holdout']['pairs']==1


def test_end_to_end_git_source_replay(book, tmp_path):
    p=tmp_path/'REVIEWS.json';p.write_bytes(canonical(reviews_for(book)))
    report=evaluate(book['path'],book['map'],p)
    assert replay_equivalent(book['path'],book['map'],p,report)
    assert report['claim_status']=='NO_EXTERNAL_GENERALIZATION_OR_VERIFIED_BUGS'


def test_replayed_report_rejects_fabricated_accuracy(book,tmp_path):
    p=tmp_path/'REVIEWS.json';p.write_bytes(canonical(reviews_for(book)))
    report=evaluate(book['path'],book['map'],p)
    fake=copy.deepcopy(report);fake['provisional_two_reviewer_metrics']['tp']+=1
    assert not replay_equivalent(book['path'],book['map'],p,fake)


def test_rehashed_wrong_source_prediction_is_not_accepted_attribution(book):
    prediction=predict(book['path'],book['map'])
    prediction['rows'][0]['faulty']['source_sha256']='0'*64
    with pytest.raises(ValueError,match='source linkage'):
        score(prediction,reviews_for(book))


def test_score_rejects_promotion_of_verification_authority(book):
    prediction=predict(book['path'],book['map'])
    prediction['verified_findings']=[{'claim':'proven cause'}]
    with pytest.raises(ValueError,match='assurance or authority'):
        score(prediction,reviews_for(book))


def test_wrong_review_snapshot_rejected(book):
    reviews=reviews_for(book);reviews['lock_sha256']='f'*64
    pred=predict(book['path'],book['map'])
    with pytest.raises(ValueError,match='stale'):
        score(pred,reviews)


def test_missing_second_reviewer_remains_out_of_scoring_denominator(book):
    rev=reviews_for(book)
    rev['reviews']=[r for r in rev['reviews'] if r['case_id']!='BETA' or r['reviewer_id']=='reviewer_1']
    report=score(predict(book['path'],book['map']),rev)
    assert report['unadjudicated_samples']==2
    assert report['by_split']['holdout']['adjudicated_pairs']==0


def test_disagreement_is_not_silently_resolved(book):
    rev=reviews_for(book);rev['reviews'][1]['faulty']='not_defective'
    result=score(predict(book['path'],book['map']),rev)
    assert result['unadjudicated_samples']==2
    assert next(x for x in result['cases'] if x['case_id']=='ALPHA')['review_status']=='review_disagreement_or_uncertain'


def test_ambiguous_reviewer_is_not_auto_counted(book):
    rev=reviews_for(book);rev['reviews'][0]['faulty']='uncertain'
    report=score(predict(book['path'],book['map']),rev)
    assert report['unadjudicated_samples']==2


def test_nonblinded_review_is_reported_as_unverified(book):
    rev=reviews_for(book);rev['reviews'][0]['prediction_blinded']=False
    report=score(predict(book['path'],book['map']),rev)
    assert report['unadjudicated_samples']==2
    assert report['independent_reviewer_identity_authenticated'] is False


def test_three_reviewers_are_not_silently_considered_independent_quorum(book):
    rev=reviews_for(book,extra=True)
    report=score(predict(book['path'],book['map']),rev)
    assert report['unadjudicated_samples']==2


def test_duplicate_reviewer_rejected(book):
    rev=reviews_for(book);rev['reviews'].append(copy.deepcopy(rev['reviews'][0]))
    with pytest.raises(ValueError,match='Duplicate reviewer'):
        score(predict(book['path'],book['map']),rev)


def test_missing_review_rationale_rejected(book):
    rev=reviews_for(book);rev['reviews'][0]['rationale']='ok'
    with pytest.raises(ValueError,match='rationale'):
        score(predict(book['path'],book['map']),rev)


def test_review_for_unknown_case_rejected(book):
    rev=reviews_for(book);rev['reviews'][0]['case_id']='UNKNOWN'
    with pytest.raises(ValueError,match='unknown case'):
        score(predict(book['path'],book['map']),rev)


def test_unknown_and_outofscope_count_without_false_clean(book):
    pred=predict(book['path'],book['map'])
    pred['rows'][0]['faulty']['status']='unknown'
    pred['rows'][0]['correct']['status']='unknown'
    pred['rows'][1]['scope']='unsupported_semantics'
    for role in ('faulty','correct'):
        pred['rows'][1][role]['status']='out_of_scope'
    result=score(pred,reviews_for(book))
    assert result['unknown_samples']==2 and result['unsupported_samples']==2
    assert result['decided_samples']==0 and result['sample_coverage']==0
    assert result['verified_findings']==[]


def test_out_of_scope_mismatch_rejected(book):
    pred=predict(book['path'],book['map'])
    pred['rows'][0]['faulty']['status']='out_of_scope'
    with pytest.raises(ValueError,match='semantic scope'):
        score(pred,reviews_for(book))


def test_prediction_rows_must_not_repeat_case(book):
    pred=predict(book['path'],book['map']);pred['rows'].append(copy.deepcopy(pred['rows'][0]))
    with pytest.raises(ValueError,match='Duplicate prediction'):
        score(pred,reviews_for(book))


def test_predictions_reject_invalid_claimed_verification(book):
    pred=predict(book['path'],book['map'])
    pred['upstream_origin_authenticated']=True
    with pytest.raises(ValueError,match='assurance or authority'):
        score(pred,reviews_for(book))


def test_changed_git_history_invalidates_replay(book,tmp_path):
    p=tmp_path/'REVIEWS.json';p.write_bytes(canonical(reviews_for(book)))
    report=evaluate(book['path'],book['map'],p)
    # A changed LOCK must fail rather than silently validate the earlier report.
    new_lock=copy.deepcopy(book['lock']);new_lock['cases'][0]['faulty']['sha256']='f'*64
    path=save(book,new_lock,tmp_path)
    with pytest.raises(ValueError):
        replay_equivalent(path,book['map'],p,report)


def test_unsupported_scope_remains_abstention_even_with_reviewer_agreement(book,tmp_path):
    alt=copy.deepcopy(book['lock']);alt['cases'][1]['scope']='unsupported_semantics';alt['cases'][1]['signal_variable']=None
    path=save(book,alt,tmp_path);newbook={'lock':alt}
    pred=predict(path,book['map'])
    rev=reviews_for(newbook)
    res=score(pred,rev)
    assert res['unsupported_samples']==2
    assert res['by_split']['holdout']['adjudicated_pairs']==1


def test_malformed_python_is_unknown_not_clean():
    report=_static(b'def this_is_not_valid(:\n', 'bad.py','x',True)
    assert report['status']=='unknown'
    assert report['incomplete_exception']=='SyntaxError'


def test_no_subprocess_source_execution_in_static_assessor():
    import ast
    import audit_engine.semantic_audit.ae23.assessment as assessor
    tree=ast.parse(Path(assessor.__file__).read_text())
    direct={c.func.id for c in ast.walk(tree) if isinstance(c,ast.Call) and isinstance(c.func,ast.Name)}
    assert not direct.intersection({'exec','eval','compile','__import__'})
