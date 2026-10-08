import ast
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EVOLUTION = ROOT / 'audit_engine' / 'semantic_audit' / 'evolution'


def _imports(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            values.append(node.module or '')
    return values


def test_evolution_layer_does_not_import_networkx_scipy_or_graph_backends():
    forbidden = ('networkx', 'scipy', 'audit_engine.semantic_audit.graph.backend')
    for path in EVOLUTION.glob('*.py'):
        for imported in _imports(path):
            assert not imported.startswith(forbidden), (path.name, imported)


def test_topology_layer_does_not_import_findings_or_rules():
    imports = _imports(EVOLUTION / 'topology.py')
    assert not any('findings' in value or '.rules' in value for value in imports)


def test_snapshot_and_delta_layers_do_not_import_verification_findings_or_rules():
    for name in ('snapshots.py', 'delta.py'):
        imports = _imports(EVOLUTION / name)
        assert not any(
            token in value
            for value in imports
            for token in ('verification', 'findings', '.rules')
        )


def test_g320_yaml_contracts_are_parseable():
    names = (
        'semantic_graph_snapshot_contract.yaml',
        'semantic_graph_evolution_contract.yaml',
        'semantic_audit_invalidation_contract.yaml',
        'audit_long_term_memory_contract.yaml',
    )
    for name in names:
        payload = yaml.safe_load((ROOT / 'specs' / 'contracts' / name).read_text(encoding='utf-8'))
        assert payload['schema_version']


def test_g320_json_schemas_are_parseable():
    names = (
        'semantic_graph_snapshot.schema.json',
        'semantic_graph_delta.schema.json',
        'semantic_audit_memory.schema.json',
    )
    for name in names:
        payload = json.loads((ROOT / 'specs' / 'schemas' / name).read_text(encoding='utf-8'))
        assert payload['$schema']
