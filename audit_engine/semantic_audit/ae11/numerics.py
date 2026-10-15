"""AE-11: deterministic, bounded linear-static FEM numerical evidence audit.

Checks are *necessary* numerical consistency conditions under declared assumptions,
not verification of constitutive models, mesh quality, boundary physics, or convergence
of the unknown true solution. No solver is run and no input artifacts are modified.
"""
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae10.science import _plain_json, _json, _dec, _relative
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType

SPEC_SCHEMA = 'ae11/fem-spec/v1'
REPORT_SCHEMA = 'ae11/fem-evidence/v1'
MAX_DOF = 80
MAX_LEVELS = 64
MAX_SPEC_BYTES = 100_000
MAX_DATA_BYTES = 2_000_000


def _path(value: Path | str) -> Path:
    p = Path(os.path.abspath(value))
    _no_symlink_components(p)
    return p


def _required_keys(value: Any, keys: set[str], title: str):
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('Invalid ' + title + ' fields')


def _number(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError('Scientific quantities must be decimal strings')
    return _dec(value)


def _nonnegative(value: Any) -> Decimal:
    d = _number(value)
    if d < 0:
        raise ValueError('Negative threshold')
    return d


def _read_source(root: Path, path: str) -> bytes:
    rel = _relative(path)
    file = root / rel
    _no_symlink_components(file)
    if not file.is_file() or file.stat().st_size > MAX_DATA_BYTES:
        raise ValueError('Missing/oversized evidence file')
    raw = file.read_bytes()
    if len(raw) > MAX_DATA_BYTES:
        raise ValueError('Changed/oversized evidence file')
    return raw


def _validate_spec(spec: dict):
    _required_keys(spec, {'schema', 'artifact', 'checks'}, 'specification')
    if spec['schema'] != SPEC_SCHEMA:
        raise ValueError('Unexpected FEM specification version')
    artifact = spec['artifact']
    _required_keys(artifact, {'path', 'sha256'}, 'artifact')
    _relative(artifact['path'])
    if not isinstance(artifact['sha256'], str) or len(artifact['sha256']) != 64 or any(c not in '0123456789abcdef' for c in artifact['sha256']):
        raise ValueError('Invalid artifact digest')
    chk = spec['checks']
    _required_keys(chk, {'symmetry_abs', 'residual_abs', 'fixed_abs', 'positive_pivot_min',
                         'energy_abs', 'order_min', 'error_monotonic_abs'}, 'check')
    for value in chk.values():
        _nonnegative(value)


def _parse_model(data: dict):
    _required_keys(data, {'schema', 'model', 'refinements'}, 'FEM data')
    if data['schema'] != 'ae11/fem-data/v1':
        raise ValueError('Unexpected FEM data schema')
    model = data['model']
    _required_keys(model, {'degrees_of_freedom', 'stiffness', 'loads', 'displacements',
                           'fixed_values', 'strain_energy', 'units', 'assumptions'}, 'model')
    n = model['degrees_of_freedom']
    if type(n) is not int or not 2 <= n <= MAX_DOF:
        raise ValueError('Unsupported DOF count')
    assumptions = model['assumptions']
    if assumptions != ['linear_static', 'symmetric_stiffness', 'stable_constrained_system']:
        raise ValueError('Necessary FEM assumptions were not declared')
    units = model['units']
    _required_keys(units, {'force', 'displacement', 'stiffness', 'energy'}, 'units')
    if not all(isinstance(x, str) and 0 < len(x) <= 30 for x in units.values()):
        raise ValueError('Invalid units')
    # No implicit conversions: the declared units must have a coherent, recognized
    # mechanical product dimension in the audited numerical scope.
    allowed = {('N','m','N/m','J'),('kN','m','kN/m','kN*m'),('N','mm','N/mm','N*mm')}
    if (units['force'], units['displacement'], units['stiffness'], units['energy']) not in allowed:
        raise ValueError('Units not explicitly supported')
    K = model['stiffness']
    if not isinstance(K, list) or len(K) != n or any(not isinstance(row, list) or len(row) != n for row in K):
        raise ValueError('Non-square stiffness matrix')
    K = [[_number(x) for x in row] for row in K]
    def vec(name):
        arr = model[name]
        if not isinstance(arr, list) or len(arr) != n:
            raise ValueError('Invalid ' + name + ' vector')
        return [_number(x) for x in arr]
    f, u = vec('loads'), vec('displacements')
    fixed = model['fixed_values']
    if not isinstance(fixed, dict) or not fixed:
        raise ValueError('At least one Dirichlet DOF required')
    constraints = {}
    for i, value in fixed.items():
        if not isinstance(i, str) or not i.isascii() or not i.isdecimal() or str(int(i)) != i or int(i) >= n:
            raise ValueError('Invalid fixed DOF index')
        constraints[int(i)] = _number(value)
    free = [i for i in range(n) if i not in constraints]
    if not free:
        raise ValueError('No free DOFs to assess')
    energy = _number(model['strain_energy'])
    series = data['refinements']
    if not isinstance(series, list) or not 3 <= len(series) <= MAX_LEVELS:
        raise ValueError('At least three refinement levels required')
    hs, errors = [], []
    for row in series:
        _required_keys(row, {'h', 'error'}, 'refinement')
        h, error = _number(row['h']), _number(row['error'])
        if h <= 0 or error <= 0:
            raise ValueError('Positive mesh sizes and nonzero errors required for log rates')
        hs.append(h); errors.append(error)
    if any(hs[i] <= hs[i+1] for i in range(len(hs)-1)):
        raise ValueError('Mesh size must decrease strictly')
    return n,K,f,u,constraints,free,energy,hs,errors,units


def _numeric_analysis(data: dict, thresholds: dict) -> list[dict]:
    n,K,f,u,fixed,free,declared_energy,hs,errors,units = _parse_model(data)
    sym_tol = _number(thresholds['symmetry_abs'])
    res_tol = _number(thresholds['residual_abs'])
    fix_tol = _number(thresholds['fixed_abs'])
    pivot_min = _number(thresholds['positive_pivot_min'])
    energy_tol = _number(thresholds['energy_abs'])
    order_min = _number(thresholds['order_min'])
    monotonic_tol = _number(thresholds['error_monotonic_abs'])
    # High precision, no binary-floating-point conversion in the numerical path.
    with localcontext() as ctx:
        ctx.prec = 240
        max_sym = max(abs(K[i][j]-K[j][i]) for i in range(n) for j in range(i+1,n))
        ku = [sum((K[i][j]*u[j] for j in range(n)), Decimal(0)) for i in range(n)]
        res = [ku[i]-f[i] for i in range(n)]
        free_max = max(abs(res[i]) for i in free)
        fixed_max = max(abs(u[i]-v) for i,v in fixed.items())
        computed_energy = sum((u[i]*ku[i] for i in range(n)),Decimal(0))/2
        # Strict positive definiteness of symmetric *free-free* block, not full
        # unconstrained stiffness (which often contains rigid-body null modes).
        # LDL^T requires no pivoting for SPD matrices. Negative/zero pivots fail.
        lower = [[Decimal(0)]*len(free) for _ in free]
        pivots = []
        stable = True
        for i, ri in enumerate(free):
            d = K[ri][ri] - sum((lower[i][k]*lower[i][k]*pivots[k] for k in range(i)), Decimal(0))
            if d <= pivot_min:
                stable = False
                break
            pivots.append(d)
            for j in range(i+1,len(free)):
                lower[j][i] = (K[free[j]][ri] - sum((lower[j][k]*lower[i][k]*pivots[k] for k in range(i)), Decimal(0)))/d
        orders=[]
        for i in range(len(hs)-1):
            order=(errors[i]/errors[i+1]).ln()/(hs[i]/hs[i+1]).ln()
            orders.append(order)
        monotone=all(errors[i+1] <= errors[i]+monotonic_tol for i in range(len(errors)-1))
        minimum=min(orders)
        def check(name, success, observed, limit, unit):
            return {'id':name, 'status':'consistent' if success else 'inconsistent',
                    'observed':str(observed), 'limit':str(limit),'unit':unit}
        return [
            check('matrix_symmetry',max_sym<=sym_tol,max_sym,sym_tol,units['stiffness']),
            check('free_equilibrium_residual',free_max<=res_tol,free_max,res_tol,units['force']),
            check('dirichlet_displacement',fixed_max<=fix_tol,fixed_max,fix_tol,units['displacement']),
            {'id':'constrained_positive_definiteness','status':'consistent' if stable else 'inconsistent',
             'min_ldlt_pivot':str(min(pivots)) if pivots else None,'pivot_threshold':str(pivot_min),
             'inspected_free_dofs':len(free), 'unit':units['stiffness']},
            check('strain_energy',abs(computed_energy-declared_energy)<=energy_tol,
                  computed_energy,declared_energy,units['energy']) | {'abs_tolerance':str(energy_tol)},
            {'id':'refinement_error_monotonicity','status':'consistent' if monotone else 'inconsistent',
             'errors':[str(x) for x in errors], 'tolerance':str(monotonic_tol)},
            {'id':'observed_refinement_order','status':'consistent' if minimum>=order_min else 'inconsistent',
             'observed_orders':[str(p) for p in orders], 'minimum_observed':str(minimum),
             'required_minimum':str(order_min)},
        ]


def build_report(spec_file: Path|str, artifacts_root: Path|str) -> dict:
    spec_path, root = _path(spec_file), _path(artifacts_root)
    if not root.is_dir() or not spec_path.is_file() or spec_path.stat().st_size > MAX_SPEC_BYTES:
        raise ValueError('Missing or oversized FEM specification')
    raw_spec = spec_path.read_bytes()
    if len(raw_spec)>MAX_SPEC_BYTES:
        raise ValueError('FEM specification size changed')
    spec=_plain_json(raw_spec)
    _validate_spec(spec)
    g=SemanticGraph()
    g.add_node(SemanticNode('model:fem','FEMModel',{'artifact_sha256':spec['artifact']['sha256'],
                                                    'scope':'linear_static'}))
    g.add_node(SemanticNode('artifact:fem','EvidenceArtifact',{'path':spec['artifact']['path'],
                                                             'source_sha256':spec['artifact']['sha256']}))
    g.add_edge(SemanticEdge('model:fem','artifact:fem','EVIDENCED_BY',metadata={'source_sha256':spec['artifact']['sha256']}))
    source_status='available'
    checks=[]
    observed=None
    try:
        source = _read_source(root,spec['artifact']['path'])
        observed=sha(source)
        if observed != spec['artifact']['sha256']:
            source_status='hash_mismatch'
        else:
            data=_json(source)
            checks=_numeric_analysis(data,spec['checks'])
            # Graph represents *observed assessment occurrences*, not a claim of
            # independent validation of scientific reality.
            for row in checks:
                nid='check:'+row['id']
                g.add_node(SemanticNode(nid,'FEMNumericalCheck',{'status':row['status'], 'source_sha256':observed}))
                g.add_edge(SemanticEdge('model:fem',nid,'CHECKED_BY',metadata={'check_id':row['id']}))
    except (OSError, UnicodeError, ValueError, InvalidOperation, TypeError, KeyError, ArithmeticError) as exc:
        source_status='unassessed'
        checks=[]
        source_error=type(exc).__name__
    else:
        source_error=None
    # Reuse G3 graph-analysis contracts: the seven numeric checks must actually
    # appear as source-bound CHECKED_BY observations. Such observations are not
    # independent numerical proof; they make coverage and evidence queryable.
    analysis=SemanticGraphAnalysisService(g).analyze(GraphQuery(
        'ae11:fem-observations',QueryType.STRUCTURAL,['model:fem'],
        {'direction':'outgoing','relation_types':['CHECKED_BY']})).to_dict()
    actual={row['object_id'] for row in analysis['observations']}
    expected={'check:'+row['id'] for row in checks}
    if (analysis['status']!=('completed' if expected else 'no_match') or actual!=expected):
        raise ValueError('G3 graph observation completeness failure')
    all_consistent=bool(checks) and all(c['status']=='consistent' for c in checks)
    verdict=('inconclusive' if source_status!='available' or not checks else
             'inconsistent' if not all_consistent else 'consistent_within_declared_checks')
    record={'schema':REPORT_SCHEMA,'spec_sha256':sha(raw_spec),
            'artifact':{'path':spec['artifact']['path'],'declared_sha256':spec['artifact']['sha256'],
                        'observed_sha256':observed,'status':source_status,'error_type':source_error},
            'checks':checks,'graph':g.to_dict(),'graph_fingerprint':graph_fingerprint(g),
            'g3_graph_analysis':analysis,
            'verdict':verdict,'limitations':[
                'Necessary numerical checks only; no verification of constitutive law, physical loading, or FEM discretization',
                'Positive definiteness applies to the declared constrained free-free stiffness block',
                'Empirical refinement orders are not proof of asymptotic convergence or exact-solution accuracy',
                'Tolerance, units and reference energy are supplied by the audited specification/data',
                'Source integrity is not independent experimental validation']}
    record['record_sha256']=sha(canonical(record))
    return record


def verify_report(report: dict, spec_file: Path|str, artifacts_root: Path|str) -> dict:
    if not isinstance(report,dict) or 'record_sha256' not in report:
        raise ValueError('Invalid FEM report')
    if report['record_sha256']!=sha(canonical({k:v for k,v in report.items() if k!='record_sha256'})):
        raise ValueError('FEM report digest mismatch')
    fresh=build_report(spec_file,artifacts_root)
    if canonical(fresh)!=canonical(report):
        raise ValueError('FEM source, graph or assessment changed')
    return {'record_sha256':report['record_sha256'],'verdict':report['verdict'],
            'checks':len(report['checks'])}
