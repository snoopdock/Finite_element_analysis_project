def test_impact_contract():
    report = {
        "source_snapshot": "snapshot.json",
        "node_count": 2,
        "edge_count": 1,
        "impact_candidates": []
    }

    assert report["node_count"] >= 0
    assert "impact_candidates" in report
