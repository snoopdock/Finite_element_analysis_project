#!/usr/bin/env python3
"""Read-only controlled-corpus demonstration of AE-01 with detached integrity check."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import verify

BASE = Path(__file__).resolve().parents[1]
POLICY = BASE / 'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
FIXTURES = BASE / 'tests/ae01/fixtures'


def main():
    with tempfile.TemporaryDirectory(prefix='ae01-demo-') as directory:
        for case, expected in (('forbidden', 1), ('permitted', 0)):
            root = FIXTURES / case
            lifecycle = json.loads((root / 'lifecycle.json').read_text(encoding='utf-8'))
            output = Path(directory) / case
            result = audit_repository(root, output, lifecycle=lifecycle, policy_file=POLICY)
            report = result['report']
            independent = verify(output, source_root=root, policy_file=POLICY)
            assert report['counts']['verified_findings'] == expected, case
            assert report['assurance_completeness'] == 'complete_within_declared_scope', case
            assert report['applicable_observations'] >= 1, case
            assert independent['findings'] == expected, case
            assert report['verified_compliance'] is (expected == 0), case
            print(json.dumps({'case': case, 'run_id': report['run_id'], 'verified_findings': expected,
                              'applicable_observations': report['applicable_observations'],
                              'detached_verification': 'passed'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
