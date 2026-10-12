"""G3.4.20: adversarial tests of claim-level SAT review gating."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from decision_memory import proposal_audit as proposals  # noqa: E402
from decision_memory import review_dossier as reviews  # noqa: E402

DEC = 'DEC-G3.4.13-001'
ACT = 'ACTION-G3.4.15-001'
OUT = 'OUTCOME-G3.4.16-001'
RULE = 'RULE-G3.4.17-001'


@pytest.fixture
def repo(tmp_path):
    for sub in ('decision_memory', 'validation'):
        shutil.copytree(ROOT / sub, tmp_path / sub, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return tmp_path


def make(repo, draft=None, query='engineering decision validation'):
    if draft is None:
        draft = f'Engineering decisions preserve rationale [[{DEC}]]\nPending action must be reviewed [[{ACT}]]'
    audit = proposals.audit(repo, query, draft)
    return audit, reviews.create_dossier(repo, audit)


def test_ready_dossier_requires_review(repo):
    a, d = make(repo)
    assert d['schema_version'] == 'sat-claim-review-dossier/v1'
    assert d['human_review'] == {
        'status': 'pending', 'required': True,
        'assessment_per_claim': 'not_assessed', 'semantic_entailment_verified': False,
        'external_evidence_reverified': False, 'authorization_granted': False,
    }
    assert all(v is False for v in d['execution_constraints'].values())
    assert all(c['semantic_support_assessed'] is False for c in d['claim_reviews'])
    assert all(c['reviewer_assessment'] == 'not_assessed' for c in d['claim_reviews'])
    assert reviews.verify_dossier(d, a, repo)


def test_trace_complete_only_structural(repo):
    _, d = make(repo)
    assert d['trace_summary']['citations_structurally_complete'] == 2
    assert d['trace_summary']['claims_missing_or_unresolved_citations'] == 0
    assert all(x['trace_status'] == 'structurally_traced_only' for x in d['claim_reviews'])
    assert all('semantic_support_not_assessed' in x['review_blockers'] for x in d['claim_reviews'])
    assert all('human_review_pending' in x['review_blockers'] for x in d['claim_reviews'])


def test_uncited_claim_remains_unapproved(repo):
    _, d = make(repo, f'Claim [[{DEC}]]\nUnsupported statement')
    assert d['claim_reviews'][1]['trace_status'] == 'uncited'
    assert d['trace_summary']['claims_missing_or_unresolved_citations'] == 1
    assert 'missing_explicit_citation' in d['claim_reviews'][1]['review_blockers']
    assert d['human_review']['authorization_granted'] is False


def test_unresolved_citation_cannot_authorize(repo):
    _, d = make(repo, 'Claims [[DEC-G9.9.9-999]]')
    claim = d['claim_reviews'][0]
    assert claim['trace_status'] == 'unresolved'
    assert claim['unresolved_record_ids'] == ['DEC-G9.9.9-999']
    assert 'unresolved_citation' in claim['review_blockers']
    assert d['sources'] == []


def test_mixed_known_and_unknown_ids_are_unresolved(repo):
    _, d = make(repo, f'Claim [[{DEC}]] [[DEC-G9.9.9-999]]')
    claim = d['claim_reviews'][0]
    assert claim['trace_status'] == 'unresolved'
    assert claim['resolved_record_ids'] == [DEC]
    assert claim['unresolved_record_ids'] == ['DEC-G9.9.9-999']


def test_pending_action_cannot_turn_success_by_wording(repo):
    _, d = make(repo, f'Action succeeded [[{ACT}]]')
    assert 'action_outcome_pending' in d['claim_reviews'][0]['historical_caveats']
    assert 'historical_outcome_conflict' in d['claim_reviews'][0]['review_blockers']
    assert d['human_review']['status'] == 'pending'


def test_successful_feedback_conflict_not_silenced(repo):
    _, d = make(repo, f'Feedback was successful [[{OUT}]]')
    assert 'pending_action_with_successful_feedback' in d['claim_reviews'][0]['historical_caveats']
    assert 'historical_outcome_conflict' in d['claim_reviews'][0]['review_blockers']


def test_rule_candidate_is_not_approved(repo):
    _, d = make(repo, f'Reuse this learning rule [[{RULE}]]')
    assert 'candidate_not_approved' in d['claim_reviews'][0]['historical_caveats']
    assert 'unapproved_learning_rule' in d['claim_reviews'][0]['review_blockers']
    assert d['execution_constraints']['learned_rule_promotion_allowed'] is False


def test_source_hashes_match_real_bytes(repo):
    _, d = make(repo)
    for source in d['sources']:
        f = repo / source['source_path']
        assert f.is_file()
        assert source['source_sha256'] == hashlib.sha256(f.read_bytes()).hexdigest()
        assert source['provenance_binding'] == 'local_file_hash_only'
        assert source['semantic_support_verified'] is False
        assert source['external_evidence_verified'] is False


def test_duplicate_marker_deduplication(repo):
    _, d = make(repo, f'Recommendation [[{DEC}]] [[{DEC}]]')
    assert d['claim_reviews'][0]['cited_record_ids'] == [DEC]
    assert d['source_record_count'] == 1


def test_dossier_digest_is_canonical(repo):
    _, d = make(repo)
    raw = {k: v for k, v in d.items() if k != 'dossier_sha256'}
    assert reviews._digest(raw) == d['dossier_sha256']
    assert len(d['dossier_sha256']) == 64


def test_deterministic_without_clock(repo):
    a1, d1 = make(repo)
    a2, d2 = make(repo)
    assert a1 == a2
    assert d1 == d2


def test_draft_change_changes_review_digest(repo):
    _, x = make(repo, f'One [[{DEC}]]')
    _, y = make(repo, f'Two [[{DEC}]]')
    assert x['dossier_sha256'] != y['dossier_sha256']


def test_claim_reordering_changes_review_digest(repo):
    _, x = make(repo, f'One [[{DEC}]]\nTwo [[{ACT}]]')
    _, y = make(repo, f'Two [[{ACT}]]\nOne [[{DEC}]]')
    assert x['dossier_sha256'] != y['dossier_sha256']


def test_stale_cited_source_is_detected(repo):
    a, d = make(repo)
    item = repo / 'decision_memory' / 'decisions' / f'{DEC}.yaml'
    item.write_text(item.read_text() + '\n# intentional edit\n')
    with pytest.raises(reviews.ReviewDossierError):
        reviews.verify_dossier(d, a, repo)
    with pytest.raises(reviews.ReviewDossierError):
        reviews.create_dossier(repo, a)


@pytest.mark.parametrize('field,value', [
    ('status', 'approved'), ('authorization_granted', True),
    ('semantic_entailment_verified', True), ('external_evidence_reverified', True),
])
def test_mutated_human_gate_is_detected(repo, field, value):
    a, d = make(repo)
    d['human_review'][field] = value
    with pytest.raises(reviews.ReviewDossierError):
        reviews.verify_dossier(d, a, repo)


def test_self_consistent_fake_approval_rejected(repo):
    a, d = make(repo)
    d['human_review']['authorization_granted'] = True
    d['dossier_sha256'] = reviews._digest({k: v for k, v in d.items() if k != 'dossier_sha256'})
    with pytest.raises(reviews.ReviewDossierError, match='does not match'):
        reviews.verify_dossier(d, a, repo)


def test_self_consistent_semantic_support_rejected(repo):
    a, d = make(repo)
    d['claim_reviews'][0]['semantic_support_assessed'] = True
    d['dossier_sha256'] = reviews._digest({k: v for k, v in d.items() if k != 'dossier_sha256'})
    with pytest.raises(reviews.ReviewDossierError):
        reviews.verify_dossier(d, a, repo)


def test_self_consistent_fabricated_source_hash_rejected(repo):
    a, d = make(repo)
    d['sources'][0]['source_sha256'] = '0' * 64
    d['dossier_sha256'] = reviews._digest({k: v for k, v in d.items() if k != 'dossier_sha256'})
    with pytest.raises(reviews.ReviewDossierError):
        reviews.verify_dossier(d, a, repo)


def test_bad_report_sha_rejected(repo):
    a, d = make(repo)
    d['dossier_sha256'] = 'x' * 64
    with pytest.raises(reviews.ReviewDossierError):
        reviews.verify_dossier(d, a, repo)


def test_forged_proposal_audit_rejected_even_with_matching_digest(repo):
    a, _ = make(repo)
    a['review_gates']['human_approval_obtained'] = True
    a['audit_sha256'] = hashlib.sha256(proposals._canonical({k: v for k, v in a.items() if k != 'audit_sha256'})).hexdigest()
    with pytest.raises(reviews.ReviewDossierError):
        reviews.create_dossier(repo, a)


def test_retrieval_context_mismatch_rejected(repo):
    a, _ = make(repo)
    a['retrieval_context_sha256'] = 'a' * 64
    with pytest.raises(reviews.ReviewDossierError):
        reviews.create_dossier(repo, a)


def test_missing_memory_record_rejected(repo):
    a, _ = make(repo)
    (repo / 'decision_memory' / 'decisions' / f'{DEC}.yaml').unlink()
    with pytest.raises(reviews.ReviewDossierError):
        reviews.create_dossier(repo, a)


def test_symlinked_source_rejected(repo, tmp_path):
    a, _ = make(repo)
    src = repo / 'decision_memory' / 'decisions' / f'{DEC}.yaml'
    external = tmp_path.parent / (tmp_path.name + '-original.yaml')
    try:
        external.write_bytes(src.read_bytes())
        src.unlink()
        src.symlink_to(external)
        with pytest.raises(reviews.ReviewDossierError):
            reviews.create_dossier(repo, a)
    finally:
        external.unlink(missing_ok=True)


def test_json_duplicate_keys_rejected(tmp_path):
    f = tmp_path / 'bad.json'
    f.write_text('{"a":1,"a":2}')
    with pytest.raises(reviews.ReviewDossierError, match='duplicate'):
        reviews._read_json(f)


def test_json_nan_rejected(tmp_path):
    f = tmp_path / 'bad.json'
    f.write_text('{"a":NaN}')
    with pytest.raises(reviews.ReviewDossierError):
        reviews._read_json(f)


def test_symlink_json_input_rejected(tmp_path):
    original = tmp_path / 'original.json'
    original.write_text('{}')
    alias = tmp_path / 'alias.json'
    alias.symlink_to(original)
    with pytest.raises(reviews.ReviewDossierError):
        reviews._read_json(alias)


def test_oversized_input_rejected(tmp_path):
    src = tmp_path / 'large.json'
    src.write_bytes(b' ' * (reviews.MAX_INPUT_BYTES + 1))
    with pytest.raises(reviews.ReviewDossierError):
        reviews._read_json(src)


def test_nonmapping_json_rejected(tmp_path):
    src = tmp_path / 'array.json'
    src.write_text('[]')
    with pytest.raises(reviews.ReviewDossierError):
        reviews._read_json(src)


def test_proposal_content_not_executed(repo, tmp_path):
    marker = tmp_path / 'should-never-exist'
    _, d = make(repo, f'$(touch {marker}) [[{DEC}]]')
    assert d['human_review']['authorization_granted'] is False
    assert not marker.exists()


def test_output_write_does_not_modify_checkout(repo, tmp_path):
    a, _ = make(repo)
    audit_file = tmp_path.parent / (tmp_path.name + '-audit.json')
    output = tmp_path.parent / (tmp_path.name + '-dossier.json')
    try:
        audit_file.write_text(json.dumps(a))
        run = subprocess.run([
            sys.executable, str(ROOT / 'decision_memory/review_dossier.py'),
            '--repository', str(repo), '--audit-file', str(audit_file), '--output', str(output),
        ], text=True, capture_output=True, timeout=30)
        assert run.returncode == 0, run.stderr
        saved = json.loads(output.read_text())
        assert reviews.verify_dossier(saved, a, repo)
        verified = subprocess.run([
            sys.executable, str(ROOT / 'decision_memory/review_dossier.py'),
            '--repository', str(repo), '--audit-file', str(audit_file), '--verify-file', str(output),
        ], text=True, capture_output=True, timeout=30)
        assert verified.returncode == 0, verified.stderr
        assert 'no approval' in verified.stdout.lower()
    finally:
        audit_file.unlink(missing_ok=True)
        output.unlink(missing_ok=True)


def test_repository_writeback_rejected(repo):
    with pytest.raises(proposals.memory.ContextRetrievalError):
        proposals.memory._write_optional(repo / 'decision_memory' / 'review.json', '{}', repo)


def test_json_schema_has_enforced_gates():
    path = ROOT / 'decision_memory/review_dossier_schema.json'
    schema = json.loads(path.read_text())
    assert schema['properties']['human_review']['properties']['authorization_granted']['const'] is False
    assert schema['properties']['human_review']['properties']['status']['const'] == 'pending'
    assert schema['properties']['execution_constraints']['properties']['automated_sat_action_allowed']['const'] is False
    assert schema['additionalProperties'] is False
