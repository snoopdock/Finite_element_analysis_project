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


def test_g321_yaml_contracts_are_parseable():
    names = (
        'semantic_impact_propagation_contract.yaml',
        'semantic_reverification_plan_contract.yaml',
        'audit_memory_query_contract.yaml',
        'incremental_reverification_contract.yaml',
    )
    for name in names:
        payload = yaml.safe_load((ROOT / 'specs' / 'contracts' / name).read_text(encoding='utf-8'))
        assert payload['schema_version']
        assert payload['contract']['purpose']


def test_g321_json_schemas_are_parseable():
    names = (
        'semantic_impact_propagation.schema.json',
        'semantic_reverification_plan.schema.json',
        'semantic_audit_memory_query.schema.json',
    )
    for name in names:
        payload = json.loads((ROOT / 'specs' / 'schemas' / name).read_text(encoding='utf-8'))
        assert payload['$schema']
        assert payload['type'] == 'object'


def test_reverification_planner_does_not_import_verification_service_or_rule_execution():
    imports = _imports(EVOLUTION / 'reverification.py')
    forbidden = (
        'audit_engine.semantic_audit.verification.service',
        'audit_engine.semantic_audit.rules.execution',
        'audit_engine.semantic_audit.findings.factory',
    )
    assert not any(value.startswith(forbidden) for value in imports)


def test_incremental_facade_does_not_import_rule_executor_or_finding_factory():
    imports = _imports(EVOLUTION / 'incremental.py')
    assert not any('.rules.execution' in value or '.findings.factory' in value for value in imports)


def test_memory_query_layer_does_not_import_graph_or_verification_mutators():
    imports = _imports(EVOLUTION / 'memory_queries.py')
    forbidden_tokens = ('.promotion', '.verification.service', '.rules.execution', '.findings.factory')
    assert not any(token in value for value in imports for token in forbidden_tokens)
