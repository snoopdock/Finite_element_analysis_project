"""AE-19: source-pinned, manually labeled historical *run-outcome* concordance.

This DOES NOT authenticate uploaded log archives to GitHub, adjudicate causal
root causes, or prove accuracy on unrelated real-world repositories. It reuses
AE-16 to evaluate the structured *declaration inferred from supplied step logs*.
No retrieved code, tests, or commands are executed here.
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae16.operations import build_report

SCHEMA = 'ae19/historical_run_effectiveness/v1'
MANIFEST = 'ae19/historical_manifest/v1'
LABELS = 'ae19/manual_run_outcome_labels/v1'
AUTHORIZED_LABEL = 'human_review_of_supplied_step_logs_not_github_api_attestation'
FILES = ('step7.txt', 'step8.txt', 'step9.txt', 'step11.txt')
STATUSES = frozenset({'passed', 'failed', 'unknown'})
HEXDIGEST = re.compile(r'^[a-f0-9]{64}$')
CASE = re.compile(r'^H[0-9]{2}_[a-z0-9_]{3,64}$')
MAX_CASES = 24
MAX_MEMBER = 500_000
MAX_TOTAL = 3_000_000


def _strict_json(path: Path) -> dict:
    _no_symlink_components(path)
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > MAX_MEMBER:
        raise ValueError('Missing or unsupported reference JSON document')
    def pairs(values):
        result = {}
        for k,v in values:
            if k in result:
                raise ValueError('Duplicate JSON property in reference')
            result[k] = v
        return result
    data = path.read_bytes()
    obj = json.loads(data, object_pairs_hook=pairs)
    if not isinstance(obj,dict) or data != canonical(obj):
        raise ValueError('Reference document must be canonical JSON object')
    return obj


def admit(root: Path | str) -> tuple[dict,dict]:
    """Exact membership and byte-identity validation, including nonregular files."""
    root = Path(os.path.abspath(root))
    _no_symlink_components(root)
    if not root.is_dir():
        raise ValueError('Historical casebook directory absent')
    manifest = _strict_json(root/'MANIFEST.json')
    if set(manifest) != {'schema','cases','sha256','archive_sha256'} or manifest['schema'] != MANIFEST:
        raise ValueError('Invalid history manifest schema')
    cases = manifest['cases']
    if (not isinstance(cases,list) or not 1 <= len(cases) <= MAX_CASES or
        cases != sorted(set(cases)) or any(not isinstance(x,str) or not CASE.fullmatch(x) for x in cases)):
        raise ValueError('Invalid historical case IDs')
    inventory = manifest['sha256']
    if not isinstance(inventory,dict) or len(inventory) != 1 + len(cases)*len(FILES):
        raise ValueError('Historical inventory size mismatch')
    archive = manifest['archive_sha256']
    if (not isinstance(archive,dict) or set(archive) != set(cases) or
        any(not isinstance(v,str) or not HEXDIGEST.fullmatch(v) for v in archive.values())):
        raise ValueError('Original archive provenance declaration invalid')
    expected = {'labels.json'} | {f'cases/{c}/{f}' for c in cases for f in FILES}
    if set(inventory) != expected:
        raise ValueError('Historical exact-member inventory mismatch')
    actual=set();total=0
    for entry in root.rglob('*'):
        if entry.is_symlink():
            raise ValueError('Symlink in historical evidence corpus')
        kind=entry.lstat().st_mode
        if stat.S_ISDIR(kind):continue
        if not stat.S_ISREG(kind):raise ValueError('Unsupported special file in historical corpus')
        name=entry.relative_to(root).as_posix()
        actual.add(name);size=entry.stat().st_size;total+=size
        if size > MAX_MEMBER or total > MAX_TOTAL:
            raise ValueError('Historical input byte budget exceeded')
    if actual != expected | {'MANIFEST.json'}:
        raise ValueError('Historical corpus contains missing or unlisted files')
    for name,digest in inventory.items():
        if (not isinstance(name,str) or name.startswith('/') or '\\' in name or
            any(t in ('','.','..') for t in name.split('/')) or
            not isinstance(digest,str) or not HEXDIGEST.fullmatch(digest)):
            raise ValueError('Invalid historical file digest declaration')
        if sha((root/name).read_bytes()) != digest:
            raise ValueError('Historical casebook source or labels changed')
    labels = _strict_json(root/'labels.json')
    if set(labels) != {'schema','oracle_authority','cases'} or labels['schema'] != LABELS or labels['oracle_authority'] != AUTHORIZED_LABEL:
        raise ValueError('Historical label authority is not declared correctly')
    if set(labels['cases']) != set(cases):
        raise ValueError('Historical labels missing or unexpected')
    for key, row in labels['cases'].items():
        if set(row) != {'profile','targeted','regression','final','detached','published','catalog_verified','rationale'}:
            raise ValueError('Invalid historical manual label shape')
        if any(row[x] not in STATUSES for x in ('targeted','regression','final','detached')):
            raise ValueError('Unsupported historical reference status')
        if (type(row['published']) is not bool or type(row['catalog_verified']) is not bool or
            not isinstance(row['profile'],str) or not re.fullmatch(r'G[0-9]+\.[0-9]+',row['profile']) or
            not isinstance(row['rationale'],str) or not row['rationale'].strip()):
            raise ValueError('Invalid historical manual reference')
    return manifest, labels


def _unique(pattern: str, text: str, *, groups: int = 1) -> tuple[str,...] | None:
    matches = re.findall(pattern,text,flags=re.MULTILINE)
    if len(matches) > 1:
        raise ValueError('Ambiguous repeated historical outcome marker')
    if not matches:return None
    row = matches[0]
    if groups == 1:
        return (row if isinstance(row,str) else row[0],)
    if not isinstance(row,tuple) or len(row) != groups:
        raise ValueError('Historical parsing mismatch')
    return row


def interpret_step_logs(root: Path, case_id: str) -> dict:
    folder = root/'cases'/case_id
    text = {}
    for f in FILES:
        raw=(folder/f).read_bytes()
        if b'\x00' in raw:raise ValueError('Binary historical step log not supported')
        text[f]=raw.decode('utf-8',errors='strict')
    # Keep observations scoped to the *actual validation step*. In particular,
    # deliberately failed fixtures in the validation-engine unit-test step are excluded.
    selected = _unique(r'Selected profile: (G[0-9]+\.[0-9]+) \(', text['step7.txt'])
    target = _unique(r'\btargeted: (passed|failed) \(exit=(-?\d+)\)',text['step7.txt'],groups=2)
    regression = _unique(r'\bregression: (passed|failed) \(exit=(-?\d+)\)',text['step7.txt'],groups=2)
    final = _unique(r'\bFinal validation status: (passed|failed)',text['step7.txt'])
    detached = _unique(r'Evidence verified \(integrity \+ outcomes\): (passed|failed), profile=(G[0-9]+\.[0-9]+)',text['step8.txt'],groups=2)
    published = _unique(r'Verified evidence CAS bundle: ([a-f0-9]{64})',text['step9.txt'])
    catalog = _unique(r'Catalog verified: ([a-f0-9]{64})',text['step11.txt'])
    for item in (target,regression):
        if item and (item[0]=='passed') != (int(item[1]) == 0):
            raise ValueError('Historical test status and exit code conflict')
    if detached and selected and detached[1] != selected[0]:
        raise ValueError('Historical detached profile differs from tested profile')
    if catalog and published and catalog[0] != published[0]:
        raise ValueError('Historical catalog and bundle identities differ')
    return {
        'profile':selected[0] if selected else None,
        'targeted':target[0] if target else 'unknown',
        'regression':regression[0] if regression else 'unknown',
        'final':final[0] if final else 'unknown',
        'detached':detached[0] if detached else 'unknown',
        'published':published is not None,
        'catalog_verified':catalog is not None,
        'bundle_sha256':published[0] if published else None,
        'source_shas':{f:sha((folder/f).read_bytes()) for f in FILES},
    }


def _as_ae16(root: Path, case_id: str, obs: dict) -> tuple[str,list[dict]]:
    """Reconstruct a limited AE-16 declaration, not an authenticated GitHub event."""
    with tempfile.TemporaryDirectory(prefix='ae19-source-replay-') as where:
        base=Path(where)
        evidence=base/'evidence'; evidence.mkdir()
        (evidence/'step7.txt').write_bytes((root/'cases'/case_id/'step7.txt').read_bytes())
        steps=[]; req=[]
        for stage in ('targeted','regression'):
            state=obs[stage]
            step_state={'passed':'success','failed':'failure','unknown':'unknown'}[state]
            observed={'passed':'passed','failed':'failed','unknown':'skipped'}[state]
            steps.append({'id':stage,'status':step_state,
                'exit_code':0 if state=='passed' else 1 if state=='failed' else None,
                'log':'step7.txt','checks':[{'id':'suite','status':state if state in ('passed','failed') else 'unknown',
                'tests':[{'id':'pytest_result','expected':'passed','observed':observed}]}],
                'produces':[],'consumes':[]})
            req.append({'id':'required-'+stage,'job':'validation','step':stage,'check':'suite'})
        status={'passed':'success','failed':'failure','unknown':'unknown'}[obs['final']]
        declaration={'schema':'ae16/declared_execution/v1','run_id':case_id.replace('_','-'),
            'reported_status':status,
            'jobs':[{'id':'validation','needs':[],'status':status,'steps':steps}],
            'requirements':req}
        file=base/'declaration.json';file.write_bytes(canonical(declaration))
        report,_=build_report(file,evidence)
        if report['verified_findings'] or report['source_authority']!='untrusted_execution_declaration_not_github_authenticated':
            raise ValueError('AE-16 promoted historical log reconstruction into verified authority')
        return report['assurance'],report['issues']


def evaluate_casebook(casebook_root: Path | str) -> dict:
    root = Path(os.path.abspath(casebook_root))
    manifest,labels = admit(root)
    evaluated=[]
    for cid in manifest['cases']:
        observed=interpret_step_logs(root,cid)
        expected=labels['cases'][cid]
        compared={k:observed[k]==expected[k] for k in expected if k!='rationale'}
        # We require the reconstructed existing AE-16 machinery to refuse false clean.
        assurance,issues=_as_ae16(root,cid,observed)
        necessarily_incomplete=any(observed[k]!='passed' for k in ('targeted','regression','final'))
        guarded=(assurance=='incomplete_or_inconsistent') if necessarily_incomplete else (assurance=='consistent_declared_observations_unattested')
        # Missing independent verification and absent catalog evidence cannot count as a pass.
        complete=(all(observed[k]=='passed' for k in ('targeted','regression','final','detached'))
                  and observed['published'] and observed['catalog_verified'])
        evaluated.append({'id':cid,'expected_run_outcome':expected['final'],
            'observed':observed,'exact_manual_label_match':all(compared.values()),
            'comparison':compared,'ae16_assurance':assurance,'ae16_issue_count':len(issues),
            'ae16_preserves_incompleteness':guarded,
            'is_complete_successful_supplied_record':complete,
            'external_run_authenticated':False,'verified_root_causes':[]})
    exact=sum(c['exact_manual_label_match'] for c in evaluated)
    guarded=sum(c['ae16_preserves_incompleteness'] for c in evaluated)
    gate=exact==len(evaluated) and guarded==len(evaluated)
    return {'schema':SCHEMA,
        'scope':'source_pinned_user_supplied_historical_github_validation_step_logs',
        'source_authority':'user_supplied_logs_not_authenticated_github_api_or_commit',
        'oracle_authority':AUTHORIZED_LABEL,
        'candidate_gate':'pass_historical_run_outcome_concordance_only' if gate else 'fail_historical_reference',
        'case_count':len(evaluated),'exact_manual_case_matches':exact,
        'ae16_assurance_preserved_count':guarded,
        'false_clean_cases':sum(c['expected_run_outcome']=='failed' and c['is_complete_successful_supplied_record'] for c in evaluated),
        'verified_findings':[],'verified_root_causes':[],
        'limitations':['Manual labels derived from uploaded step-log excerpts, not independent external case adjudication',
            'Source archive SHA-256 is descriptive; source archive is not packaged or GitHub API authenticated',
            'Passing the historical concordance does not demonstrate defect or root-cause detection accuracy',
            'Status reconstruction is not execution telemetry; no code or log-provided command is executed'],
        'cases':evaluated}
