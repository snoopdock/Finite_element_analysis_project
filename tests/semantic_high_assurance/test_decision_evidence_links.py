def test_decision_evidence_link_contract():
    link={
        "id":"DEC-G3.4.14-001",
        "decision_id":"DEC-G3.4.13-001",
        "evidence_refs":["G3.4.12"],
        "relationship":"supported_by",
        "confidence":"high"
    }
    assert len(link["evidence_refs"]) > 0
