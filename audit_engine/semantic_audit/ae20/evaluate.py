"""AE-20: bounded regression-oracle evaluation of actual AE-18/AE-19 corrections.

The evaluator is NOT a production code-failure investigator. It deliberately
executes five repository-curated, byte-pinned historical snapshots for an
explicitly authorized GitHub test run. It must never be wired to untrusted
uploaded code, automatic pull-request execution, or generic arbitrary sources.

Original failures are independently supported by G9.20/G9.21 CI logs, while
specified before/after outcomes are an internal regression oracle, not an
external expert adjudication or proof of general diagnostic accuracy.
"""
from __future__ import annotations

import json
import os
import runpy
import shutil
import stat
import tempfile
from pathlib import Path

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae18.evaluate import evaluate_corpus
from audit_engine.semantic_audit.ae19.evaluate import admit, evaluate_casebook

SCHEMA = 'ae20/pinned_historical_defect_oracles/v1'
# These digests are code-pinned, not self-authorizing assertions from an editable manifest.
SNAPSHOTS = {
    'ae18_before.py': '144c311befc161de320243f54c8680a87fcfe22ad61d3cb954ba69893da90267',
    'ae18_after.py': 'f82b08501c975ac9e1bd996fc434dde20b3013f1dd9de5760712b9ece328d4ba',
    'ae19_before_labels.json': 'c9d93c2f2e32d465d2646f41347042368184c606a3d7986d431e15032519e55d',
    'ae19_after_labels.json': '6c701936ea16466f2e110603ff1f94bd337cf21e39bd9512fd8bbd132d049a61',
    'ae19_noncanonical_labels.json': '3ed8788ec23c93c9ab0fc4655dfe0079eca6bc7c960b22f21bc0888f6d01fcf0',
}
EXPECTED = {
    'E01_empty_evidence_checkout': {'before':'rejected_missing_evidence_root','after':'accepted_complete_reference'},
    'E02_failure_catalog_label': {'before':'rejected_wrong_reference_label','after':'accepted_historical_concordance'},
    'E03_canonical_json_admission': {'before':'rejected_noncanonical_reference','after':'accepted_canonical_reference'},
}
MAX_SNAPSHOT_BYTES = 100_000


def _files(root: Path) -> dict[str, str]:
    root = Path(os.path.abspath(root))
    _no_symlink_components(root)
    if not root.is_dir():
        raise ValueError('Historical snapshot directory is missing')
    actual = {}
    for item in root.iterdir():
        _no_symlink_components(item)
        if not stat.S_ISREG(item.lstat().st_mode) or item.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise ValueError('Historical snapshot must be a bounded regular file')
        actual[item.name] = sha(item.read_bytes())
    if actual != SNAPSHOTS:
        raise ValueError('Historical snapshot bytes or membership differ from source-pinned expectations')
    return actual


def _ae18_before_after(snapshots: Path, ae18_corpus: Path) -> tuple[str, str]:
    # The original module is a trusted, exactly hash-pinned repository artifact,
    # and is executed ONLY in a user-authorized test job, never on uploads.
    original = runpy.run_path(str(snapshots/'ae18_before.py'))['evaluate_corpus']
    fixed = runpy.run_path(str(snapshots/'ae18_after.py'))['evaluate_corpus']
    with tempfile.TemporaryDirectory(prefix='ae20-missing-evidence-') as temp:
        copied = Path(temp)/'reference'
        shutil.copytree(ae18_corpus,copied)
        absent = copied/'cases'/'R05_missing_log'/'evidence'
        if absent.is_dir():
            if any(absent.iterdir()):
                raise ValueError('Original missing-log fixture unexpectedly has evidence')
            absent.rmdir()  # Reproduce Git's omission of an empty directory.
        if absent.exists() or absent.is_symlink():
            raise ValueError('Missing-log historical fixture must have no evidence root')
        try:
            original(copied)
        except ValueError as exc:
            before = ('rejected_missing_evidence_root' if 'Evidence root must be a directory' in str(exc)
                      else 'unexpected_error')
        else:
            before = 'unexpected_acceptance'
        result = fixed(copied)
        after = ('accepted_complete_reference' if result['candidate_gate']=='pass_controlled_reference_only'
                 and result['metrics']['case_count']==12 and result['metrics']['false_negative']==0
                 and result['metrics']['false_positive']==0 and result['verified_findings']==[]
                 else 'unexpected_evaluation')
        return before, after


def _casebook_with_labels(casebook: Path, labels: bytes, directory: Path) -> Path:
    copied = directory/'historical'
    shutil.copytree(casebook, copied)
    document = copied/'labels.json'
    document.write_bytes(labels)
    manifest_file = copied/'MANIFEST.json'
    manifest = json.loads(manifest_file.read_bytes())
    manifest['sha256']['labels.json'] = sha(labels)
    manifest_file.write_bytes(canonical(manifest))
    return copied


def _ae19_wrong_then_fixed(snapshots: Path, casebook: Path) -> tuple[str,str]:
    with tempfile.TemporaryDirectory(prefix='ae20-reference-') as temp:
        base=Path(temp)
        # Each case must have a separate, writable parent; the underlying pinned casebook is immutable.
        old_parent=base/'old';old_parent.mkdir()
        before=_casebook_with_labels(casebook,(snapshots/'ae19_before_labels.json').read_bytes(),old_parent)
        old = evaluate_casebook(before)
        new_parent=base/'new';new_parent.mkdir()
        after=_casebook_with_labels(casebook,(snapshots/'ae19_after_labels.json').read_bytes(),new_parent)
        fresh = evaluate_casebook(after)
        return ('rejected_wrong_reference_label' if old['candidate_gate']=='fail_historical_reference'
                and old['exact_manual_case_matches']<old['case_count'] else 'unexpected_evaluation',
                'accepted_historical_concordance' if fresh['candidate_gate']=='pass_historical_run_outcome_concordance_only'
                and fresh['exact_manual_case_matches']==fresh['case_count']==2
                and fresh['verified_root_causes']==[] else 'unexpected_evaluation')


def _ae19_noncanonical_then_fixed(snapshots: Path, casebook: Path) -> tuple[str,str]:
    with tempfile.TemporaryDirectory(prefix='ae20-serialization-') as temp:
        base=Path(temp)
        old_parent=base/'old';old_parent.mkdir()
        before=_casebook_with_labels(casebook,(snapshots/'ae19_noncanonical_labels.json').read_bytes(),old_parent)
        try:
            admit(before)
        except ValueError as exc:
            old = 'rejected_noncanonical_reference' if 'canonical JSON' in str(exc) else 'unexpected_error'
        else:
            old = 'unexpected_acceptance'
        new_parent=base/'new';new_parent.mkdir()
        after=_casebook_with_labels(casebook,(snapshots/'ae19_after_labels.json').read_bytes(),new_parent)
        manifest, labels=admit(after)
        current='accepted_canonical_reference' if len(manifest['cases'])==2 and labels['cases']['H01_g920_initial_failure']['catalog_verified'] is False else 'unexpected_evaluation'
        return old,current


def evaluate_trusted_historical_regressions(snapshot_root: Path | str,
                                            ae18_corpus: Path | str,
                                            ae19_corpus: Path | str,
                                            *, explicit_trusted_execution: bool = False) -> dict:
    """Reproduce curator-pinned historical before/after behavior, no arbitrary code.

    Requires explicit execution opt-in; designed for a manual trusted GitHub test
    job. No external commands, network calls or target-repository execution.
    """
    if explicit_trusted_execution is not True:
        raise PermissionError('Trusted archived Python execution requires explicit opt-in')
    snapshots = Path(os.path.abspath(snapshot_root))
    ae18_corpus = Path(os.path.abspath(ae18_corpus))
    ae19_corpus = Path(os.path.abspath(ae19_corpus))
    members = _files(snapshots)
    _no_symlink_components(ae18_corpus); _no_symlink_components(ae19_corpus)
    # Input identity and completeness are verified before any snapshot execution.
    from audit_engine.semantic_audit.ae18.evaluate import _admit
    _admit(ae18_corpus)
    admit(ae19_corpus)
    outcomes = {
        'E01_empty_evidence_checkout': _ae18_before_after(snapshots,ae18_corpus),
        'E02_failure_catalog_label': _ae19_wrong_then_fixed(snapshots,ae19_corpus),
        'E03_canonical_json_admission': _ae19_noncanonical_then_fixed(snapshots,ae19_corpus),
    }
    cases=[]
    for case_id in sorted(EXPECTED):
        before,after = outcomes[case_id]
        truth = EXPECTED[case_id]
        cases.append({'id':case_id,'before':before,'after':after,
                      'expected_before':truth['before'],'expected_after':truth['after'],
                      'exact_oracle_match':before==truth['before'] and after==truth['after']})
    count = sum(c['exact_oracle_match'] for c in cases)
    return {
        'schema':SCHEMA,
        'reference_scope':'three_real_project_regressions_two_are_reference_data_defects_one_is_python_code_defect',
        'source_authority':'source_snapshots_pinned_to_locally_supplied_release_archives_not_github_api_authenticated',
        'oracle_authority':'independent_expected_contracts_from_historical_G9_20_G9_21_logs_not_external_expert_review',
        'trusted_code_execution':'explicit_manual_test_only_not_an_isolated_os_sandbox',
        'snapshots_sha256':members,
        'case_count':len(cases),'exact_matches':count,
        'candidate_gate':'pass_trusted_historical_regression_oracles_only' if count==len(cases)
                         else 'fail_trusted_historical_regressions',
        'verified_findings':[],'verified_root_causes':[],
        'cases':cases,
        'limitations':['Two cases are reference-label and canonical-serialization defects, not Python program-analysis defects',
                       'Only AE-18/AE-19 local repository behavior is reproduced',
                       'No independent real-world causal adjudication or external-program defect-detection accuracy',
                       'This executes only committed byte-pinned trusted Python snapshots inside authorized tests; not safe for untrusted code',
                       'Passing these three cases does not establish any of the five audit modes at production readiness'],
    }
