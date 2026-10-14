"""Independent expected behavior for AE-03: assertions are stated here, outside implementation."""
from __future__ import annotations
import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest
from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae03 import discover, run_experiment, verify_mutation, verify_record
from audit_engine.semantic_audit.ae03.runner import _check_tree
from audit_engine.semantic_audit.ae03.source import checked_relative


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'pkg' / '__init__.py').write_text('')
    (tmp_path / 'pkg' / 'value.py').write_text(
        'def is_allowed(value):\n'
        '    return value == 7\n'
        '\n'
        'def is_small(value):\n'
        '    return value < 3\n', encoding='utf-8')
    (tmp_path / 'tests' / 'test_value.py').write_text(
        'from pkg.value import is_allowed, is_small\n'
        'def test_allowed():\n    assert is_allowed(7)\n    assert not is_allowed(5)\n'
        'def test_small():\n    assert is_small(1)\n    assert not is_small(4)\n', encoding='utf-8')
    return tmp_path


def audit(corpus, *, max_mutants=2):
    return run_experiment(corpus, ['pkg/value.py'], ['tests/test_value.py'],
                          max_mutants=max_mutants, timeout=15)


def reseal(record):
    record['record_sha256'] = sha(canonical({k: v for k, v in record.items() if k != 'record_sha256'}))
    return record


def test_known_positive_oracles_kill_two_mutants(corpus):
    report = audit(corpus)
    assert report['assurance'] == 'complete_for_selected_sites'
    assert report['counts']['killed'] == 2
    assert report['counts']['survived'] == 0
    assert report['mutation_score'] == 1.0
    assert [x['mutation']['original'] for x in report['mutants']] == ['==', '<']
    assert [x['mutation']['replacement'] for x in report['mutants']] == ['!=', '>=']
    assert verify_record(report, corpus)['test_outcomes'] == 'not_verified_without_replay'


def test_weak_oracle_survives(corpus):
    (corpus / 'tests/test_value.py').write_text(
        'from pkg.value import is_allowed, is_small\ndef test_weak():\n    assert callable(is_allowed)\n')
    report = audit(corpus)
    assert report['counts']['survived'] == 2
    assert report['mutation_score'] == 0.0
    assert report['assurance'] == 'complete_for_selected_sites'


def test_oracle_replay_independently(corpus):
    report = audit(corpus, max_mutants=1)
    assert verify_record(report, corpus, replay=True)['test_outcomes'] == 'replayed'


def test_budget_is_not_false_complete(corpus):
    report = audit(corpus, max_mutants=1)
    assert report['assurance'] == 'partial_experiment'
    assert report['available_sites'] == 2
    assert report['counts']['not_executed'] == 1
    assert verify_record(report, corpus)['accounting'] == 'verified'


def test_failing_baseline_prevents_all_mutations(corpus):
    (corpus / 'tests/test_value.py').write_text('def test_broken():\n    assert False\n')
    report = audit(corpus)
    assert report['assurance'] == 'inconclusive_baseline'
    assert report['mutants'] == []
    assert report['counts']['not_executed'] == 2
    assert report['mutation_score'] is None


def test_syntax_error_in_test_is_inconclusive(corpus):
    (corpus / 'tests/test_value.py').write_text('def test_bad(:\n')
    assert audit(corpus)['assurance'] == 'inconclusive_baseline'


def test_no_mutation_sites_refuses_false_completeness(corpus):
    (corpus / 'pkg/value.py').write_text('VALUE = 3\n')
    with pytest.raises(ValueError, match='No supported'):
        audit(corpus)


def test_source_remains_unchanged(corpus):
    before = (corpus / 'pkg/value.py').read_bytes()
    audit(corpus)
    assert (corpus / 'pkg/value.py').read_bytes() == before
    assert not (corpus / 'pkg/value.py').with_suffix('.bak').exists()


def test_mutation_id_is_repeatable_and_source_bound(corpus):
    first = discover(corpus, ['pkg/value.py'])
    again = discover(corpus, ['pkg/value.py'])
    assert [x[0] for x in first] == [x[0] for x in again]
    (corpus / 'pkg/value.py').write_text('# changed bytes\n' + (corpus / 'pkg/value.py').read_text())
    changed = discover(corpus, ['pkg/value.py'])
    assert first[0][0].mutation_id != changed[0][0].mutation_id


def test_mutant_provenance_rederivable(corpus):
    m, candidate = discover(corpus, ['pkg/value.py'])[0]
    assert verify_mutation(corpus, m) == candidate
    assert candidate != (corpus / 'pkg/value.py').read_bytes()


def test_forged_mutation_identity_rejected(corpus):
    m, _ = discover(corpus, ['pkg/value.py'])[0]
    with pytest.raises(ValueError, match='cannot be independently reproduced'):
        verify_mutation(corpus, replace(m, replacement='=='))


def test_source_edit_invalidates_report(corpus):
    r = audit(corpus, max_mutants=1)
    (corpus / 'pkg/value.py').write_text((corpus / 'pkg/value.py').read_text() + '\n# edit\n')
    with pytest.raises(ValueError, match='Live workspace bytes'):
        verify_record(r, corpus)


def test_test_edit_invalidates_report(corpus):
    r = audit(corpus, max_mutants=1)
    (corpus / 'tests/test_value.py').write_text('def test_new(): assert True\n')
    with pytest.raises(ValueError, match='Live workspace bytes'):
        verify_record(r, corpus)


def test_digest_tampering_rejected(corpus):
    r = audit(corpus, max_mutants=1)
    r['counts']['killed'] = 500
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_record(r, corpus)


def test_forged_counts_resigned_rejected(corpus):
    r = audit(corpus, max_mutants=1)
    r['counts']['killed'] = 500
    with pytest.raises(ValueError, match='count mismatch'):
        verify_record(reseal(r), corpus)


def test_forged_assurance_resigned_rejected(corpus):
    r = audit(corpus, max_mutants=1)
    r['assurance'] = 'complete_for_selected_sites'
    with pytest.raises(ValueError, match='Assurance state'):
        verify_record(reseal(r), corpus)


def test_forged_occurrence_rejected_even_resigned(corpus):
    r = audit(corpus, max_mutants=1)
    r['mutants'][0]['mutation']['line'] = 42
    with pytest.raises(ValueError, match='occurrence list'):
        verify_record(reseal(r), corpus)


@pytest.mark.parametrize('unsafe', [
    '../secret.py', '/tmp/script.py', 'pkg/../secret.py', 'pkg\\x.py',
    'pkg/../../x.py', 'pkg/.git/a.py', 'pkg/__pycache__/a.py', '', './pkg/a.py',
])
def test_unsafe_source_paths_rejected(corpus, unsafe):
    with pytest.raises(ValueError):
        discover(corpus, [unsafe])


def test_test_path_outside_tests_rejected(corpus):
    with pytest.raises(ValueError, match='under tests/'):
        run_experiment(corpus, ['pkg/value.py'], ['pkg/value.py'])


def test_source_symlink_rejected(corpus, tmp_path):
    (corpus / 'pkg/link.py').symlink_to(corpus / 'pkg/value.py')
    with pytest.raises(ValueError, match='symlink|Symlink'):
        run_experiment(corpus, ['pkg/value.py'], ['tests/test_value.py'])


def test_source_directory_symlink_rejected(corpus):
    (corpus / 'ext').symlink_to(corpus / 'pkg', target_is_directory=True)
    with pytest.raises(ValueError, match='symlink|Symlink'):
        audit(corpus)


def test_invalid_utf8_fails_explicitly(corpus):
    (corpus / 'pkg/value.py').write_bytes(b'\xff\xfe')
    with pytest.raises(UnicodeDecodeError):
        discover(corpus, ['pkg/value.py'])


def test_multiline_comparison_preserves_line_and_column(corpus):
    (corpus / 'pkg/value.py').write_text('def f(x):\n    return (x\n         != 2)\n')
    found = discover(corpus, ['pkg/value.py'])
    assert len(found) == 1
    m, raw = found[0]
    assert (m.line, m.column, m.original, m.replacement) == (3, 9, '!=', '==')
    assert b'== 2' in raw


def test_unicode_before_comparison_correct_location(corpus):
    (corpus / 'pkg/value.py').write_text('def f(caf\u00e9):\n    return caf\u00e9 == 2\n')
    found = discover(corpus, ['pkg/value.py'])
    assert len(found) == 1
    m, mutant = found[0]
    assert m.line == 2 and m.original == '=='
    assert b'caf\xc3\xa9 != 2' in mutant


def test_comments_and_strings_not_mutated(corpus):
    (corpus / 'pkg/value.py').write_text('def f(x):\n    label = "=="  # <=\n    return x == 2\n')
    found = discover(corpus, ['pkg/value.py'])
    assert len(found) == 1
    assert found[0][0].line == 3


def test_chained_comparisons_not_claimed_resolved(corpus):
    (corpus / 'pkg/value.py').write_text('def f(x): return 1 < x < 7\n')
    assert discover(corpus, ['pkg/value.py']) == []


def test_unsupported_operator_skipped(corpus):
    (corpus / 'pkg/value.py').write_text('def f(x): return x in (1,2,3)\n')
    assert discover(corpus, ['pkg/value.py']) == []


def test_deterministic_site_order(corpus):
    (corpus / 'pkg/z.py').write_text('def f(x): return x > 2\n')
    sites = discover(corpus, ['pkg/z.py', 'pkg/value.py', 'pkg/value.py'])
    assert [m.path for m, _ in sites] == ['pkg/value.py', 'pkg/value.py', 'pkg/z.py']


def test_impact_requires_authenticated_type(corpus):
    with pytest.raises(TypeError, match='independently verified'):
        run_experiment(corpus, ['pkg/value.py'], ['tests/test_value.py'], impact={'impact_plan': {}})


def test_runner_error_is_not_scored_as_kill(corpus, monkeypatch):
    from audit_engine.semantic_audit.ae03 import runner
    orig = runner._trial
    def forced(root, tests, timeout, mutation=None, mutated_bytes=None):
        if mutation:
            return runner.TestResult('failed', 4, sha(b'bad'), 'pytest usage failure')
        return orig(root, tests, timeout, mutation, mutated_bytes)
    monkeypatch.setattr(runner, '_trial', forced)
    report = audit(corpus, max_mutants=1)
    assert report['counts']['runner_error'] == 1
    assert report['counts']['killed'] == 0
    assert report['mutation_score'] is None
    assert report['assurance'] == 'partial_experiment'


def test_timeout_is_not_scored_as_kill(corpus, monkeypatch):
    from audit_engine.semantic_audit.ae03 import runner
    original = runner._trial
    def forced(root, tests, timeout, mutation=None, mutated_bytes=None):
        if mutation:
            return runner.TestResult('timeout', None, sha(b'timeout'), 'timeout')
        return original(root, tests, timeout, mutation, mutated_bytes)
    monkeypatch.setattr(runner, '_trial', forced)
    report = audit(corpus, max_mutants=1)
    assert report['counts']['timeout'] == 1
    assert report['counts']['killed'] == 0
    assert report['assurance'] == 'partial_experiment'


def test_cli_success_and_detached_check(corpus, tmp_path):
    out = tmp_path.parent / (tmp_path.name + '-report.json')
    cmd = [sys.executable, '-m', 'audit_engine.semantic_audit.ae03',
           '--repo', str(corpus), '--source', 'pkg/value.py',
           '--test', 'tests/test_value.py', '--max-mutants', '2', '--output', str(out)]
    completed = subprocess.run(cmd, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(out.read_text())
    assert payload['counts']['killed'] == 2
    verify = subprocess.run([sys.executable, '-m', 'audit_engine.semantic_audit.ae03',
                             '--repo', str(corpus), '--verify-report', str(out)],
                            text=True, capture_output=True)
    assert verify.returncode == 0, verify.stderr
    assert 'not_verified_without_replay' in verify.stdout


def test_cli_reports_partial_nonzero(corpus, tmp_path):
    out = tmp_path.parent / (tmp_path.name + '-partial.json')
    result = subprocess.run([sys.executable, '-m', 'audit_engine.semantic_audit.ae03',
                             '--repo', str(corpus), '--source', 'pkg/value.py',
                             '--test', 'tests/test_value.py', '--max-mutants', '1',
                             '--output', str(out)], capture_output=True)
    assert result.returncode == 3
    assert json.loads(out.read_text())['assurance'] == 'partial_experiment'


def test_ae02_verified_impact_links_sealed_source_generations(corpus):
    from audit_engine.semantic_audit.ae01 import audit_repository
    from audit_engine.semantic_audit.ae03 import verified_impact
    policy = Path(__file__).resolve().parents[2] / 'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
    before = corpus.parent / ('prior-' + corpus.name)
    after = corpus.parent / ('updated-' + corpus.name)
    audit_repository(corpus, before, policy_file=policy, lifecycle={'pkg.value': 'stable'})
    (corpus / 'pkg/value.py').write_text((corpus / 'pkg/value.py').read_text() + '\n# changed\n')
    audit_repository(corpus, after, policy_file=policy, lifecycle={'pkg.value': 'stable'})
    impact = verified_impact(before, after)
    assert impact.to_dict()['previous_generation'] != impact.to_dict()['current_generation']
    report = run_experiment(corpus, ['pkg/value.py'], ['tests/test_value.py'],
                            max_mutants=1, impact=impact)
    assert report['impact_provenance']['plan_sha256'] == impact.to_dict()['plan_sha256']
    assert report['assurance'] == 'partial_experiment'  # bounded mutation budget
    assert verify_record(report, corpus, verified_impact_context=impact)['impact_provenance'] == 'verified'
    assert verify_record(report, corpus)['impact_provenance'] == 'not_verified_without_sealed_generations'


def test_ae02_verified_impact_rejects_outside_changed_scope(corpus):
    from audit_engine.semantic_audit.ae01 import audit_repository
    from audit_engine.semantic_audit.ae03 import verified_impact
    policy = Path(__file__).resolve().parents[2] / 'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
    before = corpus.parent / ('prior2-' + corpus.name)
    after = corpus.parent / ('updated2-' + corpus.name)
    (corpus / 'pkg/other.py').write_text('def f(x): return x > 5\n')
    audit_repository(corpus, before, policy_file=policy, lifecycle={'pkg.value': 'stable', 'pkg.other': 'stable', 'tests.test_value': 'stable'})
    (corpus / 'pkg/value.py').write_text((corpus / 'pkg/value.py').read_text() + '\n# changed\n')
    audit_repository(corpus, after, policy_file=policy, lifecycle={'pkg.value': 'stable', 'pkg.other': 'stable', 'tests.test_value': 'stable'})
    impact = verified_impact(before, after)
    with pytest.raises(ValueError, match='outside verified impact'):
        run_experiment(corpus, ['pkg/other.py'], ['tests/test_value.py'], impact=impact)
