from processing.quality_snapshot import QualitySnapshot
from processing.quality_regression import compare_snapshots


def test_detects_new_errors():
    old = QualitySnapshot("1","valid",0,0)
    new = QualitySnapshot("2","error",2,0)

    result = compare_snapshots(old,new)

    assert result["new_errors"] == 2
    assert result["status_changed"] is True


def test_identical_runs_are_stable():
    a = QualitySnapshot("1","valid",0,0)
    b = QualitySnapshot("2","valid",0,0)

    assert compare_snapshots(a,b)["new_errors"] == 0
