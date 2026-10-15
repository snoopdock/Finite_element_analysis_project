"""AE-08: reproducible, independently labeled *bounded* architecture evaluation.

No prediction ground truth is inferred from the analyzer under evaluation. A
closed-world manually labeled fixture is required for effectiveness metrics.
Unlabeled repository surveys report coverage and limits, never accuracy.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components, _atomic_bytes
from audit_engine.semantic_audit.ae01.source import extract, inventory
from audit_engine.semantic_audit.ae02.snapshots import load_generation
from audit_engine.semantic_audit.verification.immutable_payload import thaw

SCHEMA = 'ae08/benchmark/v1'
GOLD_SCHEMA = 'ae08/gold_corpus/v1'
IMPORT_KEYS = ('file', 'line', 'column', 'form', 'module', 'symbol', 'alias', 'context', 'status', 'target')
FINDING_KEYS = ('file', 'line', 'column', 'target')


def _safe_name(name: str) -> bool:
    return (isinstance(name, str) and name.endswith('.py') and
            not name.startswith('/') and '\\' not in name and
            not any(p in ('', '.', '..') for p in PurePosixPath(name).parts) and ':' not in name)


def read_gold(root: Path, gold_file: Path) -> dict:
    """Strict manual contract: labels must cover *every* Python source in corpus."""
    root, gold_file = Path(root).absolute(), Path(gold_file).absolute()
    _no_symlink_components(root)
    _no_symlink_components(gold_file)
    if not root.is_dir() or gold_file == root or not gold_file.is_file():
        raise ValueError('Invalid evaluation root or missing gold file')
    # Do not let a symlinked directory hide additional unlabeled Python files.
    for current, folders, names in os.walk(root, followlinks=False):
        if any((Path(current) / name).is_symlink() for name in folders + names):
            raise ValueError('Symlink in closed gold corpus is forbidden')
    gold = json.loads(gold_file.read_bytes())
    if not isinstance(gold, dict) or set(gold) != {'schema', 'files', 'lifecycle', 'imports', 'violations', 'rationale'} or gold['schema'] != GOLD_SCHEMA:
        raise ValueError('Unsupported or incomplete gold corpus contract')
    files = gold['files']
    if not isinstance(files, dict) or not files:
        raise ValueError('Gold file manifest missing')
    if not isinstance(gold['rationale'], str) or len(gold['rationale']) < 40:
        raise ValueError('Independent labeling rationale is required')
    for name, expected in files.items():
        if not _safe_name(name) or not isinstance(expected, str) or len(expected) != 64:
            raise ValueError('Unsafe or invalid labeled source entry')
        p = root / name
        _no_symlink_components(p)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError('Gold corpus source hash mismatch: ' + name)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*.py')}
    if actual != set(files):
        raise ValueError('Gold corpus does not account for exactly all Python files')
    if not isinstance(gold['lifecycle'], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in gold['lifecycle'].items()):
        raise ValueError('Invalid lifecycle labeling')
    if not isinstance(gold['imports'], list) or not isinstance(gold['violations'], list):
        raise ValueError('Gold import and finding annotations must be lists')
    for row in gold['imports']:
        if not isinstance(row, dict) or set(row) != set(IMPORT_KEYS) or row['file'] not in files or not isinstance(row['context'], list):
            raise ValueError('Invalid independent import annotation')
        if type(row['line']) is not int or type(row['column']) is not int or row['line'] < 1 or row['column'] < 0:
            raise ValueError('Invalid import source span')
    for row in gold['violations']:
        if not isinstance(row, dict) or set(row) != set(FINDING_KEYS) or row['file'] not in files:
            raise ValueError('Invalid independent violation annotation')
    if len({canonical(x) for x in gold['imports']}) != len(gold['imports']) or len({canonical(x) for x in gold['violations']}) != len(gold['violations']):
        raise ValueError('Gold corpus contains duplicate, indistinguishable annotations')
    return gold


def _observed_imports(generation) -> list[dict]:
    return sorted(({k: thaw(row[k]) for k in IMPORT_KEYS} for row in generation.facts['imports']), key=canonical)


def _observed_findings(generation) -> list[dict]:
    by_id = {row['id']: row for row in generation.facts['imports']}
    found = []
    for item in generation.report['findings']:
        w = item['witness']
        ref = by_id[w['occurrence_id']]
        found.append({'file': w['source_id'], 'line': w['line'], 'column': w['column'], 'target': ref['target']})
    return sorted(found, key=canonical)


def _compare(expected: list[dict], observed: list[dict]) -> dict:
    e = Counter(canonical(row).decode('utf-8').strip() for row in expected)
    o = Counter(canonical(row).decode('utf-8').strip() for row in observed)
    matches = sum((e & o).values())
    misses, extras = sum((e - o).values()), sum((o - e).values())
    # Unlabeled examples must never enter these denominators.
    return {'expected': sum(e.values()), 'observed': sum(o.values()),
            'exact_matches': matches, 'missing': misses, 'unexpected': extras,
            'recall': matches / sum(e.values()) if e else None,
            'precision': matches / sum(o.values()) if o else None,
            'missing_rows': [json.loads(v) for v in sorted((e - o).elements())],
            'unexpected_rows': [json.loads(v) for v in sorted((o - e).elements())]}


def score_generation(generation, gold: dict) -> dict:
    manifest = thaw(generation.manifest)
    files = {r['path']: r for r in manifest['files'] if r['status'] == 'included'}
    for p, digest in gold['files'].items():
        if p not in files or files[p]['sha256'] != digest:
            raise ValueError('Sealed generation source disagrees with gold file hashes')
    if set(files) != set(gold['files']):
        raise ValueError('Evaluated source scope differs from the closed gold corpus')
    if thaw(generation.policy)['configuration']['lifecycle'] != gold['lifecycle']:
        raise ValueError('Evaluated lifecycle classifications differ from gold contract')
    imports = _compare(gold['imports'], _observed_imports(generation))
    findings = _compare(gold['violations'], _observed_findings(generation))
    issues = thaw(generation.report['issues'])
    # A passing accuracy contract does not override AE-01 incomplete coverage.
    accurate = imports['missing'] == imports['unexpected'] == findings['missing'] == findings['unexpected'] == 0
    complete = generation.report['assurance_completeness'] == 'complete_within_declared_scope'
    return {'schema': SCHEMA, 'generation_id': generation.snapshot.generation_id,
            'source_manifest_sha256': generation.snapshot.source_manifest_hash,
            'source_digest': generation.snapshot.source_digest,
            'policy_sha256': generation.snapshot.policy_hash,
            'publication_seal_sha256': generation.snapshot.publication_seal_hash,
            'gold_sha256': sha(canonical(gold)),
            'gold_files': len(gold['files']), 'source_scope_verified': True,
            'imports': imports, 'architecture_findings': findings,
            'engine_assurance_status': generation.snapshot.assurance_completeness,
            'engine_issue_kinds': sorted({row['kind'] for row in issues}),
            'all_gold_annotations_matched': accurate,
            'interpretation': ('fixture_agreement_with_incomplete_assurance' if accurate and not complete
                               else 'fixture_agreement_bounded' if accurate else 'gold_disagreement'),
            'claim_limits': [
                'Agreement rates apply only to this pre-labeled closed corpus, not the real repository.',
                'Exact semantic observation matching is not proof of runtime Python semantics.',
                'Mutually similar test fixtures are not an unbiased population sample.',
                'Audit completeness is determined by AE-01; gold agreement never promotes inconclusive to clean.',
            ]}


def evaluate(root: Path, gold_file: Path, policy_file: Path, audit_output: Path) -> dict:
    gold = read_gold(root, gold_file)
    audit_repository(root, audit_output, lifecycle=gold['lifecycle'], policy_file=policy_file)
    # Independent AE-02 verification; recheck live source/policy files too.
    generation = load_generation(audit_output, source_root=Path(root), policy_file=Path(policy_file))
    result = score_generation(generation, gold)
    result['report_sha256'] = sha(canonical(result))
    return result


def verify_result(report: dict, root: Path, gold_file: Path, policy_file: Path, audit_output: Path) -> dict:
    if not isinstance(report, dict) or report.get('schema') != SCHEMA:
        raise ValueError('Invalid evaluation report')
    supplied_digest = report.get('report_sha256')
    if sha(canonical({k:v for k,v in report.items() if k!='report_sha256'})) != supplied_digest:
        raise ValueError('Evaluation report checksum mismatch')
    gold = read_gold(root, gold_file)
    gen = load_generation(audit_output, source_root=Path(root), policy_file=Path(policy_file))
    independent = score_generation(gen, gold)
    independent['report_sha256'] = sha(canonical(independent))
    if canonical(independent) != canonical(report):
        raise ValueError('Evaluation report does not match verified source and independent labels')
    return {'verified': True, 'generation_id': gen.snapshot.generation_id,
            'gold_agreement': independent['all_gold_annotations_matched'],
            'engine_assurance_status': independent['engine_assurance_status']}


def survey(root: Path, *, excludes: tuple[str, ...] = ()) -> dict:
    """Unlabeled real-source survey: intentionally returns no accuracy metrics."""
    manifest, sources = inventory(Path(root), excludes=excludes)
    imports, calls, funcs, issues = extract(sources, manifest, {})
    second, second_sources = inventory(Path(root), excludes=excludes)
    if second != manifest or second_sources != sources:
        issues.append({'kind': 'source_changed_during_survey'})
    counts = dict(Counter(x['status'] for x in imports))
    status = ('incomplete' if manifest['summary']['error'] or
              any(x['kind']=='source_changed_during_survey' for x in issues) else 'descriptive_only')
    return {'schema': 'ae08/survey/v1', 'manifest_sha256': sha(canonical(manifest)),
            'source_files': len(sources), 'file_status_counts': manifest['summary'],
            'import_status_counts': {k:counts[k] for k in sorted(counts)},
            'calls': len(calls), 'functions': len(funcs),
            'explicit_issue_counts': dict(sorted(Counter(i['kind'] for i in issues).items())),
            'survey_status': status, 'precision': None, 'recall': None,
            'verified_compliance': False,
            'interpretation': 'Unlabeled source observations; no defect-detection accuracy or policy compliance claim.'}


def write_report(path: Path, report: dict) -> None:
    path = Path(path).absolute()
    _no_symlink_components(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _no_symlink_components(path)
    _atomic_bytes(path, canonical(report))
