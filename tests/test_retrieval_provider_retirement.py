from pathlib import Path

import research.evidence as evidence
from research.evidence import get_retrieval_provider_registry, merge_evidence, retrieve_evidence_parallel


def test_semantic_scholar_is_retired_but_provenance_module_is_retained():
    registry = get_retrieval_provider_registry()
    assert registry["active"] == ["arxiv", "wikipedia"]
    retired = registry["retired"]["semantic_scholar"]
    assert retired["status"] == "retired_from_active_retrieval"
    assert retired["implementation_retained"] is True
    assert retired["historical_provenance_retained"] is True
    module_path = Path(evidence.__file__).resolve().parent / "semantic_scholar.py"
    assert module_path.is_file()


def test_active_retrieval_does_not_call_semantic_scholar(monkeypatch):
    monkeypatch.setattr(evidence, "cleanup_cache", lambda: None)
    monkeypatch.setattr(evidence, "search_arxiv", lambda query, limit: [])
    monkeypatch.setattr(evidence, "search_wikipedia", lambda query, limit: [])
    results = retrieve_evidence_parallel(["finite element method"], max_workers=2)
    report = evidence.get_last_retrieval_report()

    assert results == []
    assert set(report["providers"]) == {"arxiv", "wikipedia"}
    assert "semantic_scholar" not in report["providers"]
    assert report["provider_registry"]["retired"]["semantic_scholar"]["status"] == "retired_from_active_retrieval"


def test_historical_semantic_scholar_evidence_is_preserved_by_merge():
    historical = {
        "source_id": "s2_historical_001",
        "provider": "semantic_scholar",
        "retriever_module": "research.semantic_scholar",
        "title": "Historical paper record",
        "url": "https://www.semanticscholar.org/paper/historical",
        "provenance_record_id": "prov-001",
        "retrieved_at": "2026-10-06T12:00:00Z",
    }
    merged = merge_evidence([historical], [])
    assert merged == [historical]
    assert merged[0]["provider"] == "semantic_scholar"
    assert merged[0]["provenance_record_id"] == "prov-001"


def test_retirement_metadata_does_not_count_as_active_provider_failure(monkeypatch):
    monkeypatch.setattr(evidence, "cleanup_cache", lambda: None)
    monkeypatch.setattr(evidence, "search_arxiv", lambda query, limit: [{"source_id": "arxiv:1", "title": "A paper"}])
    monkeypatch.setattr(evidence, "search_wikipedia", lambda query, limit: [])
    results = retrieve_evidence_parallel(["finite element method"], max_workers=2)
    report = evidence.get_last_retrieval_report()

    assert len(results) == 1
    assert report["providers"]["arxiv"]["status"] == "success"
    assert "semantic_scholar" not in report["providers"]
    assert report["status"] == "success"
