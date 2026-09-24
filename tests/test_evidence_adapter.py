from processing.evidence_adapter import (
    adapt_evidence_item_to_reference,
    adapt_evidence_to_references,
)


def test_rich_evidence_is_reduced_to_reference_contract():
    evidence = {
        "source_id": "paper_1",
        "title": "Finite Element Methods",
        "url": "https://example.com",
        "provider": "semantic_scholar",
        "metadata": {"extra": "value"},
        "ranking": 1,
    }

    result = adapt_evidence_item_to_reference(evidence)

    assert result == {
        "source_id": "paper_1",
        "title": "Finite Element Methods",
        "url": "https://example.com",
        "retriever_module": "semantic_scholar",
        "retrieved_at": "N/A",
    }


def test_multiple_evidence_items_are_adapted():
    result = adapt_evidence_to_references(
        [
            {
                "source_id": "a",
                "title": "A",
            },
            {
                "source_id": "b",
                "title": "B",
            },
        ]
    )

    assert len(result) == 2


def test_missing_source_id_fails():
    try:
        adapt_evidence_item_to_reference(
            {"title": "No source"}
        )
    except ValueError:
        return

    assert False
