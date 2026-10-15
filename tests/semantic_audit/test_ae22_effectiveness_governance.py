"""G9.24 independent protocol and adversarial source-admission controls.

NO fixture Python is executed. GitHub manual validation must run these tests.
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae22.evaluate import (
    PINNED_MEMBERS, _counts, _observation, _wilson, admit_casebook,
    evaluate_casebook, fingerprint_report, replay_equivalent,
)

ROOT=Path(__file__).parent/'fixtures'/'ae22_casebook'


def _copy(tmp_path):
    target=tmp_path/'book';shutil.copytree(ROOT,target);return target


def test_schema_exact_membership_and_nonblind_protocol():
    labels,protocol,src=admit_casebook(ROOT)
    assert len(labels['cases'])==10
    assert len(src)==20
    assert len(PINNED_MEMBERS)==22
    assert protocol['blinded'] is False
    assert protocol['independent_upstream_byte_authentication'] is False
    assert {c['adjudication'] for c in labels['cases']}=={'single_curator_not_blind'}
    assert len({c['faulty'] for c in labels['cases']})==10
    assert len({c['correct'] for c in labels['cases']})==10


def test_read_only_observation_evaluation_has_no_verified_findings():
    r=evaluate_casebook(ROOT)
    assert r['counts']['all_pairs']==10
    assert r['counts']['all_samples']==20
    assert r['independently_adjudicated_cases']==0
    assert r['held_out_cases']==0
    assert r['upstream_byte_authenticated_external_cases']==0
    assert r['behavioral_oracle_reproduction']=='NOT_RUN'
    assert r['verified_findings']==r['verified_root_causes']==[]
    assert r['authority']=='exploratory_curated_static_observation_only'
    assert r['counts']['false_clean_claims']==0
    assert replay_equivalent(ROOT,r)
    assert len(fingerprint_report(r))==64


def test_unsupported_semantics_are_never_reported_as_decided_clean():
    r=evaluate_casebook(ROOT)
    for c in r['cases']:
        if c['declared_static_scope']=='unsupported_semantics':
            assert c['faulty_observation']['status']=='out_of_scope'
            assert c['correct_observation']['status']=='out_of_scope'
    assert r['counts']['unsupported_samples']==8


def test_all_samples_explicitly_partitioned():
    counts=evaluate_casebook(ROOT)['counts']
    assert counts['scored_samples']+counts['abstained_samples']+counts['unsupported_samples']==counts['all_samples']
    assert 0 <= counts['coverage_fraction'] <= 1
    assert set(counts)>= {'tp','fp','fn','tn','unknown_defective','unknown_control'}


def test_per_family_confusion_avoids_averaging_over_unknown():
    r=evaluate_casebook(ROOT)
    assert sum(v['all_pairs'] for v in r['per_family'].values())==r['counts']['all_pairs']
    assert sum(v['scored_samples'] for v in r['per_family'].values())==r['counts']['scored_samples']
    assert sum(v['unsupported_samples'] for v in r['per_family'].values())==r['counts']['unsupported_samples']


def test_a_missing_observation_is_unknown_not_clean():
    observation=_observation({'scopes':[]},'faulty.py','variable',eligible=True)
    assert observation['status']=='unknown'
    assert observation['basis'].startswith('No matching')


def test_unsupported_never_enters_false_negative_denominator():
    observation=_observation({'scopes':[]},'a.py','x',eligible=False)
    assert observation['status']=='out_of_scope'
    rows=[{'faulty_observation':observation,'correct_observation':observation}]
    matrix=_counts(rows)
    assert matrix['fn']==matrix['tn']==matrix['fp']==matrix['tp']==0
    assert matrix['unsupported_samples']==2
    assert matrix['coverage_fraction']==0.0


def test_ambiguous_case_accounting_has_no_silent_positive_or_negative():
    rows=[{'faulty_observation':{'status':'unknown'},'correct_observation':{'status':'unknown'}},
          {'faulty_observation':{'status':'possible_unbound'},'correct_observation':{'status':'no_unbound_signal'}}]
    m=_counts(rows)
    assert m['tp']==1 and m['tn']==1 and m['unknown_defective']==1 and m['unknown_control']==1
    assert m['coverage_fraction']==0.5
    assert m['false_clean_claims']==0


def test_false_negative_and_false_positive_observation_scoring_is_unembellished():
    rows=[{'faulty_observation':{'status':'no_unbound_signal'},'correct_observation':{'status':'possible_unbound'}}]
    m=_counts(rows)
    assert (m['tp'],m['fp'],m['fn'],m['tn'])==(0,1,1,0)
    assert m['false_clean_claims']==0  # no G3 verified clean claim was produced


def test_confidence_interval_is_only_descriptive():
    assert _wilson(0,0) is None
    for yes,total in ((0,2),(2,2),(1,5),(0,1)):
        v=_wilson(yes,total)
        assert 0<=v['lower']<=v['fraction']<=v['upper']<=1
        assert 'nonrandom' in v['interpretation']


def test_replay_rejects_fabricated_tp_count_even_if_rehashed():
    original=evaluate_casebook(ROOT)
    changed=copy.deepcopy(original)
    changed['counts']['tp']+=1
    _=fingerprint_report(changed)
    assert not replay_equivalent(ROOT,changed)


def test_replay_rejects_authority_promotion():
    r=evaluate_casebook(ROOT)
    r['verified_findings'].append({'cause':'invented'})
    r['authority']='verified_root_cause'
    assert not replay_equivalent(ROOT,r)


def test_changed_source_rejected_despite_unchanged_labels(tmp_path):
    root=_copy(tmp_path)
    p=root/'branch_faulty.py';p.write_bytes(p.read_bytes()+b'\n# change\n')
    with pytest.raises(ValueError,match='membership changed'):
        admit_casebook(root)


def test_rehashed_wrong_labels_do_not_replace_code_pins(tmp_path):
    root=_copy(tmp_path)
    p=root/'LABELS.json';label=json.loads(p.read_bytes())
    label['cases'][0]['faulty_expected']='control'
    p.write_bytes(canonical(label))
    with pytest.raises(ValueError,match='membership changed'):
        admit_casebook(root)


def test_noncanonical_json_is_rejected_by_code_pin(tmp_path):
    root=_copy(tmp_path)
    p=root/'PROTOCOL.json';p.write_bytes(p.read_bytes().rstrip(b'\n'))
    with pytest.raises(ValueError,match='membership changed'):
        admit_casebook(root)


def test_additional_source_rejected(tmp_path):
    root=_copy(tmp_path)
    (root/'surprise.py').write_text('raise RuntimeError("not executed")\n')
    with pytest.raises(ValueError,match='membership changed'):
        admit_casebook(root)


def test_missing_member_rejected(tmp_path):
    root=_copy(tmp_path)
    (root/'branch_correct.py').unlink()
    with pytest.raises(ValueError,match='membership changed'):
        admit_casebook(root)


def test_source_symlink_rejected_even_when_bytes_match(tmp_path):
    root=_copy(tmp_path)
    p=root/'branch_faulty.py';p.unlink()
    try:p.symlink_to(ROOT/'branch_faulty.py')
    except (OSError, NotImplementedError):pytest.skip('Platform lacks symlink support')
    with pytest.raises(ValueError):admit_casebook(root)


def test_member_directory_substitution_rejected(tmp_path):
    root=_copy(tmp_path)
    p=root/'branch_faulty.py';p.unlink();p.mkdir()
    with pytest.raises(ValueError,match='type or size'):admit_casebook(root)


def test_unknown_root_rejected(tmp_path):
    with pytest.raises(ValueError,match='real directory'):admit_casebook(tmp_path/'not-here')


def test_reference_report_identity_is_byte_and_protocol_bound():
    r=evaluate_casebook(ROOT)
    assert r['protocol_sha256']==PINNED_MEMBERS['PROTOCOL.json']
    assert r['labels_sha256']==PINNED_MEMBERS['LABELS.json']
    assert len(r['casebook_identity'])==64
    assert all(len(v)==64 for v in r['source_sha256'].values())


def test_external_reference_claim_avoids_upstream_authentication():
    r=evaluate_casebook(ROOT)
    case=next(c for c in r['cases'] if c['case_id']=='GCD')
    assert case['provenance_class']=='quixbugs_curated_transcription'
    assert case['upstream_byte_authenticated'] is False
    assert case['declared_static_scope']=='unsupported_semantics'
    assert r['upstream_byte_authenticated_external_cases']==0


def test_no_direct_code_execution_used_by_evaluator():
    # Static source-code policy check is a backstop, not an OS security sandbox.
    import ast
    import audit_engine.semantic_audit.ae22.evaluate as evaluator
    tree=ast.parse(Path(evaluator.__file__).read_text())
    called={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert not called.intersection({'exec','eval','compile','__import__'})
