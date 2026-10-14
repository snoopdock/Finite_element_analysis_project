from audit_engine.semantic_audit.ae02.snapshots import create_snapshot
from audit_engine.semantic_audit.ae02.delta import compare_snapshots
from audit_engine.semantic_audit.ae02.lifecycle import FindingLifecycleManager

def test_snapshot_delta():
    a=create_snapshot({"a":1},{"g":1},{"f":1})
    b=create_snapshot({"a":2},{"g":1},{"f":2})
    d=compare_snapshots(a,b)
    assert d.source_changed and d.findings_changed

def test_lifecycle():
    m=FindingLifecycleManager()
    m.transition("x","verified","e1")
    m.transition("x","resolved","e2")
    assert m.state["x"]=="resolved"
