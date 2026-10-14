"""AE-02 independent fixture oracles exercising real AE-01 -> sealed G3 -> AE-02.

No replacement mocks of source extraction, graph construction, rules or G3 receipts.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae02 import (
    AuditSnapshot, CoverageStatus, FindingLifecycleManager, compare_generations,
    compare_snapshots, from_generation, load_generation,
)

POLICY = Path(__file__).resolve().parents[2] / 'specs/rules/architecture/no_production_to_experimental_dependency.yaml'


def source(tmp_path, **files):
    root = tmp_path / 'src'
    root.mkdir(exist_ok=True)
    for path, content in files.items():
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode() if isinstance(content, str) else content)
    return root


def audit(root, output, classification=None):
    return audit_repository(root, output, lifecycle=classification or {}, policy_file=POLICY)['report']


def pair(tmp_path, first, second, old_map, new_map=None):
    root = source(tmp_path, **first)
    old = audit(root, tmp_path/'old', old_map)
    for key in set(first)-set(second):
        (root/key).unlink()
    for key, value in second.items():
        path = root/key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value.encode() if isinstance(value, str) else value)
    new = audit(root, tmp_path/'new', new_map if new_map is not None else old_map)
    return old, new, compare_generations(tmp_path/'old', tmp_path/'new')


def statuses(record):
    return [e['status'] for e in record['finding_evolution']]


def test_forbidden_source_remains_verified_not_inferred(tmp_path):
    src = source(tmp_path, **{'prod.py':'import exp\n', 'exp.py':''})
    report = audit(src, tmp_path/'out', {'prod':'production', 'exp':'experimental'})
    gen = load_generation(tmp_path/'out')
    assert len(report['findings']) == 1
    assert gen.snapshot.generation_id == report['run_id']
    assert from_generation(gen).entries[0].status is CoverageStatus.VERIFIED
    assert from_generation(gen).clean_claim_allowed() is False
    assert gen.facts['imports'][0]['file'] == 'prod.py'


def test_permitted_dependency_is_clean_only_after_executed_policy(tmp_path):
    src = source(tmp_path, **{'prod.py':'import stable\n', 'stable.py':''})
    audit(src, tmp_path/'out', {'prod':'production','stable':'stable'})
    gen = load_generation(tmp_path/'out')
    assert from_generation(gen).clean_claim_allowed() is True
    assert from_generation(gen).entries[0].observations == 1
    assert from_generation(gen).entries[0].obligations == 1
    assert from_generation(gen).entries[0].receipts == 1


def test_no_rule_observations_not_a_clean_vacuous_pass(tmp_path):
    root = source(tmp_path, **{'mod.py':'x = 5\n'})
    audit(root, tmp_path/'out', {'mod':'production'})
    cover = from_generation(load_generation(tmp_path/'out'))
    assert cover.entries[0].status is CoverageStatus.NOT_APPLICABLE
    assert not cover.clean_claim_allowed()


def test_unclassified_policy_incomplete_and_not_clean(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n','exp.py':''})
    audit(root, tmp_path/'out', {'prod':'production'})
    cover = from_generation(load_generation(tmp_path/'out'))
    assert cover.entries[0].status is CoverageStatus.INCOMPLETE
    assert 'unclassified_internal_dependency' in cover.entries[0].reasons
    assert not cover.clean_claim_allowed()


def test_same_source_and_policy_generates_identical_comparison(tmp_path):
    src = source(tmp_path, **{'a.py':'import b\n','b.py':''})
    audit(src, tmp_path/'first', {'a':'production','b':'stable'})
    audit(src, tmp_path/'next', {'a':'production','b':'stable'})
    first = compare_generations(tmp_path/'first',tmp_path/'next')
    second = compare_generations(tmp_path/'first',tmp_path/'next')
    assert canonical(first) == canonical(second)
    assert first['delta']['source_changed'] is False
    assert first['delta']['graph_changed'] is False
    assert first['existing_evolution_graph_delta']['is_noop'] is True
    assert first['finding_evolution'] == []


def test_non_dependency_statement_edit_is_detected(tmp_path):
    _, _, result = pair(tmp_path, {'a.py':'import b\nx=1\n','b.py':''},
                        {'a.py':'import b\nx=2\n','b.py':''}, {'a':'production','b':'stable'})
    assert result['delta']['source_changed']
    assert result['delta']['modified_files'] == ['a.py']
    assert result['delta']['added_dependencies'] == []
    assert result['delta']['removed_dependencies'] == []


def test_forbidden_introduced_reports_new_verified_finding(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import stable\n','stable.py':'','exp.py':''},
                       {'prod.py':'import exp\n','stable.py':'','exp.py':''},
                       {'prod':'production','stable':'stable','exp':'experimental'})
    assert record['delta']['source_changed']
    assert [i['target'] for i in record['delta']['added_dependencies']] == ['exp']
    assert [i['target'] for i in record['delta']['removed_dependencies']] == ['stable']
    assert statuses(record) == ['new_verified_observation']
    assert record['finding_evolution'][0]['source_id'] == 'prod.py'
    assert not record['interpretation']['clean_claim_allowed']
    assert not record['existing_evolution_graph_delta']['is_noop']


def test_disappeared_forbidden_finding_is_not_proven_fix(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import exp\n','exp.py':'','stable.py':''},
                        {'prod.py':'import stable\n','exp.py':'','stable.py':''},
                        {'prod':'production','exp':'experimental','stable':'stable'})
    assert statuses(record) == ['not_observed_in_complete_audit']
    assert record['interpretation']['clean_claim_allowed']


def test_incomplete_successor_never_resolves_a_finding(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import exp\n','exp.py':''},
                        {'prod.py':'import exp\n','exp.py':''},
                        {'prod':'production','exp':'experimental'}, {'prod':'production'})
    # The same finding can persist even when the overall audit is incomplete;
    # if it disappears, no resolution may be claimed.
    assert not record['interpretation']['assurance_complete']
    assert not record['interpretation']['clean_claim_allowed']
    assert record['delta']['policy_changed']
    assert record['coverage']['current']['entries'][0]['status'] == 'incomplete'


def test_policy_change_new_finding_not_mislabeled_regression(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import stable\n','stable.py':''},
                        {'prod.py':'import stable\n','stable.py':''},
                        {'prod':'production','stable':'stable'},
                        {'prod':'production','stable':'experimental'})
    assert statuses(record) == ['new_under_changed_policy']
    assert record['delta']['policy_changed']
    assert not record['interpretation']['policy_comparable']
    assert record['delta']['source_changed'] is False


def test_finding_same_location_new_source_bytes_requires_reverification(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import exp\nx=1\n','exp.py':''},
                        {'prod.py':'import exp\nx=2\n','exp.py':''},
                        {'prod':'production','exp':'experimental'})
    assert statuses(record) == ['revalidated_with_changed_evidence']
    assert record['finding_evolution'][0]['previous_receipt_id'] != record['finding_evolution'][0]['current_receipt_id']
    assert not record['delta']['policy_changed']


def test_finding_relocated_is_distinct_occurrence(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import exp\nx=1\n','exp.py':''},
                        {'prod.py':'x=1\nimport exp\n','exp.py':''},
                        {'prod':'production','exp':'experimental'})
    assert sorted(statuses(record)) == ['new_verified_observation', 'not_observed_in_complete_audit']


def test_duplicate_imports_preserved_as_parallel_evidence(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import exp\n','exp.py':''},
                        {'prod.py':'import exp\nimport exp\n','exp.py':''},
                        {'prod':'production','exp':'experimental'})
    assert statuses(record).count('new_verified_observation') == 1
    assert record['coverage']['current']['entries'][0]['observations'] == 2
    assert len(record['delta']['added_dependencies']) == 1


def test_file_add_and_remove_detection(tmp_path):
    _, _, record = pair(tmp_path, {'prod.py':'import exp\n','exp.py':'','delete.py':'x=1\n'},
                        {'prod.py':'import exp\n','exp.py':'','add.py':'x=2\n'},
                        {'prod':'production','exp':'experimental'})
    assert record['delta']['added_files'] == ['add.py']
    assert record['delta']['removed_files'] == ['delete.py']


def test_explicit_historic_generation_valid_after_latest_failure(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n','exp.py':''})
    one = audit(root, tmp_path/'out', {'prod':'production','exp':'experimental'})
    (root/'prod.py').write_text('import exp\nadded = 2\n')
    two = audit(root, tmp_path/'out', {'prod':'production','exp':'experimental'})
    historic = compare_generations(tmp_path/'out',tmp_path/'out',
                                   before_generation=one['run_id'], after_generation=two['run_id'])
    assert historic['delta']['source_changed']
    (tmp_path/'out'/'LATEST.json').write_text('{"status":"failed","generation":null}')
    with pytest.raises(ValueError, match='not completed'):
        load_generation(tmp_path/'out')
    assert load_generation(tmp_path/'out', one['run_id']).snapshot.generation_id == one['run_id']


def test_artifact_modified_without_seal_update_is_rejected(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n','exp.py':''})
    report = audit(root, tmp_path/'out', {'prod':'production','exp':'experimental'})
    artifact = tmp_path/'out'/'generations'/report['run_id']/'source_facts.json'
    artifact.write_bytes(artifact.read_bytes()+b' ')
    with pytest.raises(ValueError, match='checksum'):
        load_generation(tmp_path/'out', report['run_id'])


def test_resigning_report_cannot_circumvent_source_to_finding_verification(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n','exp.py':''})
    report = audit(root, tmp_path/'out', {'prod':'production','exp':'experimental'})
    folder = tmp_path/'out'/'generations'/report['run_id']
    report_file = folder/'report.json'
    record = json.loads(report_file.read_text())
    record['findings'][0]['witness']['source_id'] = 'different.py'
    report_file.write_bytes(canonical(record))
    seal_file = folder/'SEAL.json'
    seal = json.loads(seal_file.read_text())
    seal['artifacts']['report.json'] = sha(report_file.read_bytes())
    seal_file.write_bytes(canonical(seal))
    with pytest.raises(ValueError, match='witness|Finding|Source'):
        load_generation(tmp_path/'out',report['run_id'])


def test_extra_generation_member_rejected(tmp_path):
    root = source(tmp_path, **{'a.py':'import b\n','b.py':''})
    report = audit(root, tmp_path/'out', {'a':'production','b':'stable'})
    folder = tmp_path/'out'/'generations'/report['run_id']
    (folder/'rogue.json').write_text('{}')
    with pytest.raises(ValueError, match='Unexpected'):
        load_generation(tmp_path/'out',report['run_id'])


def test_symlinked_generation_member_is_rejected(tmp_path):
    root = source(tmp_path, **{'a.py':'import b\n','b.py':''})
    report = audit(root, tmp_path/'out', {'a':'production','b':'stable'})
    folder = tmp_path/'out'/'generations'/report['run_id']
    target = folder/'manifest.json'
    target.rename(folder/'actual')
    target.symlink_to(folder/'actual')
    with pytest.raises(ValueError, match='Unexpected|Symlink'):
        load_generation(tmp_path/'out',report['run_id'])


def test_bad_generation_path_is_rejected(tmp_path):
    root = source(tmp_path, **{'a.py':'import b\n','b.py':''})
    audit(root,tmp_path/'out',{'a':'production','b':'stable'})
    with pytest.raises(ValueError, match='Unsafe'):
        load_generation(tmp_path/'out', '../escape')


def test_compare_requires_verified_objects(tmp_path):
    with pytest.raises(TypeError, match='verified'):
        compare_snapshots({'generation_id':'fake'}, {'generation_id':'fake'})


def test_lifecycle_requires_actor_and_evidence_and_legal_transitions():
    manager = FindingLifecycleManager()
    with pytest.raises(ValueError, match='Invalid'):
        manager.transition('f','resolved','receipt-1',actor='reviewer')
    assert manager.transition('f','observed','receipt-1',actor='auditor') == 'observed'
    assert manager.transition('f','verified','receipt-2',actor='verifier') == 'verified'
    with pytest.raises(ValueError, match='Invalid'):
        manager.transition('f','resolved','receipt-3',actor='reviewer')
    manager.transition('f','accepted','decision-1',actor='reviewer')
    manager.transition('f','resolved','receipt-4',actor='reviewer')
    manager.transition('f','reopened','receipt-5',actor='reviewer')
    assert len({row['event_sha256'] for row in manager.history}) == 5


def test_lifecycle_rejects_missing_evidence_and_mutability_shortcuts():
    manager = FindingLifecycleManager()
    with pytest.raises(ValueError, match='requires'):
        manager.transition('f','observed','',actor='auditor')
    with pytest.raises(ValueError, match='requires'):
        manager.transition('f','observed','receipt',actor='')


def test_cli_emits_verifiable_change_report(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n','exp.py':''})
    audit(root,tmp_path/'old',{'prod':'production','exp':'experimental'})
    (root/'prod.py').write_text('import exp\nx=1\n')
    audit(root,tmp_path/'new',{'prod':'production','exp':'experimental'})
    proc = subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae02',
                          '--before-output',str(tmp_path/'old'),
                          '--after-output',str(tmp_path/'new')], capture_output=True,text=True)
    assert proc.returncode == 0, proc.stderr
    output = json.loads(proc.stdout)
    assert output['delta']['source_changed']
    recorded = output.pop('comparison_sha256')
    assert recorded == sha(canonical(output))


def test_cli_incomplete_and_broken_seal_exit_codes(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n','exp.py':''})
    r=audit(root,tmp_path/'old',{'prod':'production','exp':'experimental'})
    audit(root,tmp_path/'new',{'prod':'production'})
    cmd = [sys.executable,'-m','audit_engine.semantic_audit.ae02',
           '--before-output',str(tmp_path/'old'),'--after-output',str(tmp_path/'new')]
    assert subprocess.run(cmd,capture_output=True).returncode == 3
    (tmp_path/'old'/'generations'/r['run_id']/'manifest.json').write_text('wrong')
    assert subprocess.run(cmd,capture_output=True).returncode == 4




def test_verified_generation_nested_evidence_is_deeply_immutable(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n','exp.py':''})
    audit(root, tmp_path/'out', {'prod':'production','exp':'experimental'})
    gen = load_generation(tmp_path/'out')
    with pytest.raises(TypeError):
        gen.report['findings'][0]['witness']['source_id'] = 'forged.py'
    with pytest.raises(TypeError):
        gen.facts['imports'][0]['target'] = 'forged'
    with pytest.raises(AttributeError):
        gen.facts['imports'].append({'id':'forged'})
    assert gen.report['findings'][0]['witness']['source_id'] == 'prod.py'


def test_resealed_import_target_corruption_rejected(tmp_path):
    root = source(tmp_path, **{'prod.py':'import exp\n', 'exp.py':'', 'stable.py':''})
    report = audit(root, tmp_path/'out', {'prod':'production','exp':'experimental','stable':'stable'})
    folder = tmp_path/'out'/'generations'/report['run_id']
    facts_path = folder/'source_facts.json'
    facts = json.loads(facts_path.read_bytes())
    facts['imports'][0]['target'] = 'stable'  # same line and occurrence, wrong semantic binding
    facts_path.write_bytes(canonical(facts))
    seal_file = folder/'SEAL.json'
    seal = json.loads(seal_file.read_bytes())
    seal['artifacts']['source_facts.json'] = sha(facts_path.read_bytes())
    seal_file.write_bytes(canonical(seal))
    with pytest.raises(ValueError, match='Import resolution disagrees'):
        load_generation(tmp_path/'out', report['run_id'])


def test_release_checker_detects_missing_profile_and_compiled_files(tmp_path):
    import zipfile
    from tools.check_validation_patch import check
    repo = Path(__file__).resolve().parents[2]
    archive = tmp_path/'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae02_evolution.py', '# no profile')
        z.writestr('STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae02/__pycache__/a.pyc', 'bad')
    problems = check(archive, repo, 'G9.2')
    assert any('profiles/G9.2.yaml' in p for p in problems)
    assert any('Compiled Python' in p for p in problems)
    assert any('SHA256SUMS' in p for p in problems)


def test_release_checker_detects_broken_test_target(tmp_path):
    import zipfile
    from tools.check_validation_patch import check
    repo = Path(__file__).resolve().parents[2]
    archive = tmp_path/'broken.zip'
    missing_test = 'tests/does-not-exist.py'
    profile = 'id: G9.2\nname: test\ntarget_tests:\n  - ' + missing_test + '\n  - tests/ae01/test_vertical_slice.py\nregression:\n  enabled: true\n  path: tests/\n'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('STAGE1_SECTION_UUIDS/validation/profiles/G9.2.yaml', profile)
    assert any('does not exist' in p for p in check(archive, repo, 'G9.2'))


def test_profile_selects_real_paths_with_complete_regression():
    import yaml
    root = Path(__file__).resolve().parents[2]
    profile = yaml.safe_load((root/'validation/profiles/G9.2.yaml').read_text())
    assert profile['id'] == 'G9.2'
    assert profile['regression'] == {'enabled':True,'path':'tests/'}
    assert len(profile['target_tests']) >= 5
    assert all((root/p).is_file() for p in profile['target_tests'])
    assert 'tests/semantic_audit/test_ae02_evolution.py' in profile['target_tests']
    assert 'tests/ae01/test_vertical_slice.py' in profile['target_tests']
