"""Independent contract oracles for AE-01 source-to-verified-finding behavior."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import verify
from audit_engine.semantic_audit.ae01.source import inventory, extract
from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.verification import VerificationAttempt, VerificationDecision, VerificationReceipt
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.immutable_payload import freeze, thaw

POLICY = Path(__file__).resolve().parents[2] / 'specs/rules/architecture/no_production_to_experimental_dependency.yaml'


def project(tmp_path, files: dict[str, str | bytes]):
    root = tmp_path / 'src'
    root.mkdir()
    for name, content in files.items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode('utf8') if isinstance(content, str) else content)
    return root


def run(root: Path, tmp_path: Path, classification: dict[str, str]):
    return audit_repository(root, tmp_path / 'out', lifecycle=classification, policy_file=POLICY)['report']


def finding_witness(report):
    assert len(report['findings']) == 1
    return report['findings'][0]['witness']


def test_forbidden_dependency_uses_real_source_and_sealed_receipt(tmp_path):
    root = project(tmp_path, {'prod.py': 'import exp\n', 'exp.py': 'pass\n'})
    report = run(root, tmp_path, {'prod':'production', 'exp':'experimental'})
    witness = finding_witness(report)
    assert report['assurance_completeness'] == 'complete_within_declared_scope'
    assert witness['source_id'] == 'prod.py' and witness['line'] == 1
    assert witness['column'] == 0
    import hashlib
    assert witness['source_sha256'] == hashlib.sha256((root/'prod.py').read_bytes()).hexdigest()
    assert report['applicable_observations'] == 1
    assert verify(tmp_path/'out')['findings'] == 1
    records = json.loads((tmp_path/'out'/'generations'/report['run_id']/'rule_executions.json').read_text())
    execution = records[0]['rule_execution']
    assert execution['reason'] == 'executed' and len(execution['obligations']) == 1
    assert execution['receipts'][0]['decision'] == 'confirmed'
    assert execution['receipts'][0]['evidence_state'] == 'validated'
    assert execution['findings'][0]['receipt_id'] == execution['receipts'][0]['receipt_id']


def test_permitted_dependency_has_executed_policy_not_silent_skip(tmp_path):
    root = project(tmp_path, {'prod.py':'import stable\n', 'stable.py':'VALUE = 1\n'})
    report = run(root, tmp_path, {'prod':'production', 'stable':'stable'})
    assert report['verified_compliance'] is True
    assert report['findings'] == [] and report['applicable_observations'] == 1
    execution = json.loads((tmp_path/'out'/'generations'/report['run_id']/'rule_executions.json').read_text())[0]['rule_execution']
    assert execution['reason'] == 'executed' and len(execution['receipts']) == 1
    assert execution['receipts'][0]['decision'] == 'refuted'


def test_relative_imports_aliases_and_nested_packages(tmp_path):
    root = project(tmp_path, {'pkg/__init__.py':'', 'pkg/mod.py':'from . import sibling as friend\nfrom ..pkg import sibling\n',
                              'pkg/sibling.py':'VALUE=2\n'})
    manifest, sources = inventory(root)
    imps, calls, funcs, issues = extract(sources, manifest, {})
    assert not issues
    assert [r['target'] for r in imps] == ['pkg.sibling','pkg.sibling']
    assert imps[0]['alias'] == 'friend' and imps[1]['level'] == 2
    assert len({x['id'] for x in imps}) == 2


def test_duplicate_occurrence_ids_are_distinct_and_both_verified(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\nimport exp\n', 'exp.py':''})
    report = run(root, tmp_path, {'prod':'production','exp':'experimental'})
    assert report['applicable_observations'] == 2
    assert len(report['findings']) == 2
    assert {f['witness']['line'] for f in report['findings']} == {1, 2}
    assert len({f['finding']['evidence_ids'][0] for f in report['findings']}) == 2


def test_source_edit_invalidates_run_and_finding_evidence(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\n', 'exp.py':''})
    first = run(root, tmp_path, {'prod':'production', 'exp':'experimental'})
    (root/'prod.py').write_text('import exp\nVALUE = 7\n')
    second = run(root, tmp_path, {'prod':'production','exp':'experimental'})
    assert first['run_id'] != second['run_id']
    assert first['source_digest'] != second['source_digest']
    assert first['graph_fingerprint'] != second['graph_fingerprint']
    assert first['findings'][0]['finding']['receipt_id'] != second['findings'][0]['finding']['receipt_id']
    assert verify(tmp_path/'out')['generation'] == second['run_id']


def test_identical_runs_are_byte_identical_and_reusable(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\n', 'exp.py':''})
    one = run(root, tmp_path, {'prod':'production', 'exp':'experimental'})
    report_file = tmp_path/'out'/'generations'/one['run_id']/'report.json'
    first_bytes = report_file.read_bytes()
    two = run(root, tmp_path, {'prod':'production', 'exp':'experimental'})
    assert two == one and report_file.read_bytes() == first_bytes
    assert verify(tmp_path/'out')['generation'] == one['run_id']


def test_no_import_files_remain_source_covered_but_required_policy_unassessed(tmp_path):
    root = project(tmp_path, {'empty.py':'', 'plain.py':'x=1\n'})
    report = run(root, tmp_path, {'empty':'production', 'plain':'stable'})
    assert report['counts']['source_files'] == 2
    assert report['verified_compliance'] is False
    assert report['rule_status'] == 'not_applicable'
    assert 'required_rule_not_applicable' in {i['kind'] for i in report['issues']}
    graph = json.loads((tmp_path/'out'/'generations'/report['run_id']/'graph.json').read_text())
    assert {'module:empty','module:plain'}.issubset({n['id'] for n in graph['nodes']})


def test_missing_classification_must_not_be_read_as_permitted(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\n', 'exp.py':''})
    report = run(root, tmp_path, {'prod':'production'})
    assert report['assurance_completeness'] == 'inconclusive'
    assert not report['verified_compliance']
    assert 'unclassified_internal_dependency' in {i['kind'] for i in report['issues']}


@pytest.mark.parametrize('bad', [b'\xff\xfe\x80\xff', b'def nope(:\n'])
def test_bad_source_produces_incomplete_record_not_crash(tmp_path, bad):
    root = project(tmp_path, {'prod.py':'import stable\n','stable.py':'', 'broken.py':bad})
    report = run(root, tmp_path, {'prod':'production', 'stable':'stable'})
    assert report['assurance_completeness'] == 'inconclusive'
    manifest = json.loads((tmp_path/'out'/'generations'/report['run_id']/'manifest.json').read_text())
    assert any(row['path']=='broken.py' and row['status']=='error' for row in manifest['files'])


def test_unreadable_file_reported_even_when_privileged(tmp_path):
    root = project(tmp_path, {'prod.py':'import stable\n', 'stable.py':'', 'private.py':'PASSWORD = 1\n'})
    (root/'private.py').chmod(0)
    try:
        report = run(root, tmp_path, {'prod':'production', 'stable':'stable'})
        assert not report['verified_compliance']
        assert 'source_scan_incomplete' in {i['kind'] for i in report['issues']}
    finally:
        (root/'private.py').chmod(0o600)


def test_dynamic_import_and_calls_do_not_claim_exact_binding(tmp_path):
    root = project(tmp_path, {'mod.py': 'import importlib as loader\nname="m"\nloader.import_module(name)\na.save()\nb.save()\n'})
    manifest, sources = inventory(root)
    imports, calls, _, issues = extract(sources, manifest, {})
    assert any(i['status']=='unresolved' and i['reason']=='dynamic_expression' for i in imports)
    assert {c['receiver'] for c in calls if c['spelling'].endswith('.save')} == {'a','b'}
    assert all(c['resolution']=='unresolved' for c in calls if c['spelling'].endswith('.save'))
    assert len({c['id'] for c in calls}) == 3
    assert issues


def test_type_checking_context_cannot_claim_unconditional_clean(tmp_path):
    root = project(tmp_path, {'prod.py':'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import exp\n', 'exp.py':''})
    report = run(root, tmp_path, {'prod':'production','exp':'experimental'})
    assert report['assurance_completeness'] == 'inconclusive'
    assert 'type_checking_only_dependency' in {i['kind'] for i in report['issues']}
    assert 'type_checking' in finding_witness(report)['context']


def test_symlink_outside_root_not_read(tmp_path):
    root = project(tmp_path, {'prod.py':'import stable\n', 'stable.py':''})
    secret = tmp_path/'secret.py'
    secret.write_text('DO_NOT_READ=1\n')
    (root/'leak.py').symlink_to(secret)
    report = run(root, tmp_path, {'prod':'production', 'stable':'stable'})
    manifest = json.loads((tmp_path/'out'/'generations'/report['run_id']/'manifest.json').read_text())
    assert any(r['path']=='leak.py' and r['reason']=='symlink_file' for r in manifest['files'])
    assert 'leak.py' not in json.loads((tmp_path/'out'/'generations'/report['run_id']/'source_facts.json').read_text()).get('files', [])


def test_dot_git_substring_is_not_excluded(tmp_path):
    root = project(tmp_path, {'legitimate.githelper/code.py':'x=1\n', '.git/internal.py':'SECRET=1\n'})
    manifest, sources = inventory(root)
    assert 'legitimate.githelper/code.py' in sources
    assert '.git/internal.py' not in sources
    assert any(r['path']=='.git/' and r['reason']=='excluded_directory' for r in manifest['files'])


def test_output_symlink_refused_and_external_contents_unchanged(tmp_path):
    root = project(tmp_path, {'prod.py':'import stable\n','stable.py':''})
    outside = tmp_path/'outside'; outside.mkdir()
    (tmp_path/'out').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink'):
        run(root, tmp_path, {'prod':'production','stable':'stable'})
    assert not list(outside.iterdir())


def test_tampering_breaks_detached_generation_verification(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\n','exp.py':''})
    report = run(root, tmp_path, {'prod':'production', 'exp':'experimental'})
    path = tmp_path/'out'/'generations'/report['run_id']/'graph.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='checksum'):
        verify(tmp_path/'out')
    with pytest.raises(ValueError, match='modified'):
        run(root, tmp_path, {'prod':'production', 'exp':'experimental'})
    latest = json.loads((tmp_path/'out'/'LATEST.json').read_text())
    assert latest['status'] == 'failed' and latest['generation'] is None


def test_failed_attempt_not_mislabeled_as_previous_success(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\n','exp.py':''})
    prior = run(root, tmp_path, {'prod':'production', 'exp':'experimental'})
    with pytest.raises(ValueError, match='Exclusions must'):
        # No source mutation; failure after attempt started (invalid exclusion name).
        audit_repository(root, tmp_path/'out', lifecycle={'prod':'production', 'exp':'experimental'},
                         policy_file=POLICY, excludes=('../invalid',))
    assert json.loads((tmp_path/'out'/'LATEST.json').read_text())['status'] == 'failed'
    with pytest.raises(ValueError, match='not completed'):
        verify(tmp_path/'out')
    assert (tmp_path/'out'/'generations'/prior['run_id']/'SEAL.json').exists()


def test_nested_published_verification_values_are_immutable():
    nested = {'a': [{'b': [1, 2]}]}
    frozen = freeze(nested)
    with pytest.raises(TypeError): frozen['a'][0]['b'] = []
    with pytest.raises(AttributeError): frozen['a'].append(4)
    nested['a'][0]['b'].append(3)
    assert thaw(frozen) == {'a': [{'b': [1, 2]}]}


def test_weak_test_would_miss_dropped_edge_but_contract_oracle_fails(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\n','exp.py':''})
    report = run(root, tmp_path, {'prod':'production','exp':'experimental'})
    graph = json.loads((tmp_path/'out'/'generations'/report['run_id']/'graph.json').read_text())
    mutant = {**graph, 'edges':[e for e in graph['edges'] if e['relation']!='IMPORTS']}
    assert mutant is not None  # intentionally weak control
    assert not any(e['source']=='module:prod' and e['target']=='module:exp' and e['relation']=='IMPORTS'
                   for e in mutant['edges'])  # strong oracle would reject mutant
    assert any(e['source']=='module:prod' and e['target']=='module:exp' and e['relation']=='IMPORTS'
               for e in graph['edges'])


def test_cli_exit_codes(tmp_path):
    root = project(tmp_path, {'prod.py':'import exp\n','exp.py':''})
    conf = tmp_path/'class.json'
    conf.write_text(json.dumps({'prod':'production','exp':'experimental'}))
    base = [sys.executable, '-m','audit_engine.semantic_audit.ae01', '--source-root',str(root),
            '--output-root',str(tmp_path/'out'), '--policy',str(POLICY),'--lifecycle',str(conf)]
    assert subprocess.run(base, capture_output=True).returncode == 2
    assert subprocess.run(base[:3]+['--output-root',str(tmp_path/'out'),'--verify'],capture_output=True).returncode == 0


def test_import_module_alias_recognizes_dynamic_nonliteral(tmp_path):
    root = project(tmp_path, {'prod.py':'from importlib import import_module as load\nload(name)\n'})
    manifest, sources = inventory(root)
    imps, _, _, issues = extract(sources, manifest, {})
    assert any(i['form']=='dynamic_unresolved' and i['reason']=='dynamic_expression' for i in imps)
    assert issues


def test_exec_is_explicitly_unresolved_in_architecture_audit(tmp_path):
    root = project(tmp_path, {'prod.py':'import stable\nexec(source)\n','stable.py':''})
    report = run(root,tmp_path,{'prod':'production','stable':'stable'})
    assert report['assurance_completeness']=='inconclusive'
    assert any(i['kind']=='unresolved_import' for i in report['issues'])
    assert not report['verified_compliance']


def test_namespace_package_module_and_relative_import(tmp_path):
    root = project(tmp_path, {'space/pkg/a.py':'from . import b\n', 'space/pkg/b.py':'VALUE=2\n'})
    manifest, sources = inventory(root)
    imps, _, _, issues = extract(sources, manifest, {})
    assert imps[0]['target']=='space.pkg.b'
    assert imps[0]['status']=='internal' and not issues


def test_star_import_not_promoted_to_definite_binding(tmp_path):
    root = project(tmp_path, {'prod.py':'from stable import *\n','stable.py':'VALUE=1\n'})
    report = run(root,tmp_path,{'prod':'production','stable':'stable'})
    assert report['assurance_completeness']=='inconclusive'
    assert any(i.get('reason')=='star_import_runtime_bindings' for i in report['issues'])


def test_source_manifest_is_independent_of_creation_order(tmp_path):
    layouts = []
    for dirname, filenames in [('first',['pkg/a.py','pkg/b.py','pkg/__init__.py']),
                                ('second',['pkg/__init__.py','pkg/b.py','pkg/a.py'])]:
        root = tmp_path/dirname; root.mkdir()
        for filename in filenames:
            path = root/filename;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('import pkg.b\n' if filename=='pkg/a.py' else '')
        layouts.append(root)
    outputs = [run(root,tmp_path/('out'+str(i)),{'pkg.a':'production','pkg.b':'stable'})
               for i,root in enumerate(layouts)]
    assert outputs[0]['source_digest']==outputs[1]['source_digest']
    assert outputs[0]['run_id']==outputs[1]['run_id']
    assert outputs[0]['graph_fingerprint']==outputs[1]['graph_fingerprint']


def test_source_changes_after_scan_are_not_clean(tmp_path, monkeypatch):
    from audit_engine.semantic_audit.ae01 import pipeline
    root = project(tmp_path, {'prod.py':'import stable\n','stable.py':''})
    original = pipeline.inventory
    called = [0]
    def swapped(*args,**kwargs):
        called[0]+=1
        if called[0]==2:
            (root/'stable.py').write_text('AFTER = 1\n')
        return original(*args,**kwargs)
    monkeypatch.setattr(pipeline, 'inventory', swapped)
    report = run(root,tmp_path,{'prod':'production','stable':'stable'})
    assert called[0]==2
    assert 'source_changed_during_audit' in {i['kind'] for i in report['issues']}
    assert not report['verified_compliance']


def test_injected_publication_failure_invalidates_latest_success(tmp_path, monkeypatch):
    from audit_engine.semantic_audit.ae01 import publication
    root = project(tmp_path, {'prod.py':'import stable\n','stable.py':''})
    prior=run(root,tmp_path,{'prod':'production','stable':'stable'})
    (root/'prod.py').write_text('import stable\nNEW = 1\n')
    original = publication._atomic_bytes
    def injected(path, data):
        if path.name == 'graph.json':
            raise OSError('fault injection: artifact write interrupted')
        return original(path,data)
    monkeypatch.setattr(publication,'_atomic_bytes',injected)
    with pytest.raises(OSError,match='fault injection'):
        run(root,tmp_path,{'prod':'production','stable':'stable'})
    status=json.loads((tmp_path/'out'/'LATEST.json').read_text())
    assert status['status']=='failed' and status['generation'] is None
    assert (tmp_path/'out'/'generations'/prior['run_id']/'SEAL.json').exists()
    with pytest.raises(ValueError,match='not completed'):
        verify(tmp_path/'out')


def test_detached_check_detects_source_or_policy_change(tmp_path):
    root=project(tmp_path,{'prod.py':'import stable\n','stable.py':''})
    report=run(root,tmp_path,{'prod':'production','stable':'stable'})
    assert verify(tmp_path/'out',source_root=root,policy_file=POLICY)['generation']==report['run_id']
    (root/'stable.py').write_text('UPDATED=1\n')
    with pytest.raises(ValueError,match='Source changed'):
        verify(tmp_path/'out',source_root=root)
    changed_policy=tmp_path/'policy.yaml'
    changed_policy.write_bytes(POLICY.read_bytes()+b'\n# added comment\n')
    with pytest.raises(ValueError,match='Policy bytes changed'):
        verify(tmp_path/'out',policy_file=changed_policy)


def test_receipt_and_finding_deep_immutability_without_id_drift():
    from audit_engine.semantic_audit.verification.models import VerificationDecision
    from audit_engine.semantic_audit.findings.models import FindingLifecycleStatus
    nested={'tree':[{'items':[1,2]}]}
    receipt=VerificationReceipt('receipt','attempt','obligation','analysis','verifier','1',
                                VerificationDecision.CONFIRMED,VerificationStatus.VALIDATED,
                                ('evidence',),'g','semantic',details=nested)
    finding=AuditFinding('finding','rule','1','receipt','obligation','error','title','message',
                         ('evidence',),'g','semantic',metadata=nested)
    with pytest.raises(TypeError): receipt.details['tree'][0]['items'][0]=42
    with pytest.raises(TypeError): finding.metadata['tree'][0]['items'][0]=42
    nested['tree'][0]['items'].append(3)
    assert receipt.to_dict()['details']==finding.to_dict()['metadata']=={'tree':[{'items':[1,2]}]}


def test_large_synthetic_dependency_corpus_exact_oracle(tmp_path):
    files={'entry.py':'\n'.join(f'import sub_{i:03d}' for i in range(160))+'\n'}
    files.update({f'sub_{i:03d}.py':'X=1\n' for i in range(160)})
    classification={'entry':'production',**{f'sub_{i:03d}':'stable' for i in range(160)}}
    root=project(tmp_path,files)
    report=run(root,tmp_path,classification)
    assert report['counts']['source_files']==161
    assert report['applicable_observations']==160
    assert report['verified_compliance'] is True
    assert report['counts']['verified_findings']==0
    assert verify(tmp_path/'out')['findings']==0
