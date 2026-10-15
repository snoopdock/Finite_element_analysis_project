"""AE-19 static release contract; executed under manual GitHub G9.21 profile."""
from pathlib import Path
import yaml
from audit_engine.semantic_audit.ae19.evaluate import SCHEMA,MANIFEST,LABELS
from audit_engine.semantic_audit.ae19 import admit

ROOT=Path(__file__).resolve().parents[2]

def test_historical_reference_membership_and_schema():
    manifest,labels=admit(ROOT/'tests/semantic_audit/fixtures/ae19_history')
    assert manifest['schema']==MANIFEST and labels['schema']==LABELS
    assert SCHEMA=='ae19/historical_run_effectiveness/v1'

def test_profile_manual_declared_complete_regression():
    profile=yaml.safe_load((ROOT/'validation/profiles/G9.21.yaml').read_text())
    assert profile['id']=='G9.21'
    assert profile['regression']=={'enabled':True,'path':'tests/'}
    assert 'tests/semantic_audit/test_ae19_history.py' in profile['target_tests']
    assert all((ROOT/name).is_file() for name in profile['target_tests'])
