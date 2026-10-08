from pathlib import Path


def test_g322_contracts_present():
    required = [
        "specs/contracts/semantic_reverification_execution_contract.yaml",
        "specs/contracts/semantic_artifact_reconciliation_contract.yaml",
        "specs/contracts/semantic_replay_contract.yaml",
        "specs/contracts/semantic_reverification_execution_memory_contract.yaml",
        "specs/schemas/semantic_reverification_execution.schema.json",
        "specs/schemas/semantic_artifact_reconciliation.schema.json",
        "docs/decisions/ADR-049-reverification-replay-and-execution-boundary.md",
        "docs/decisions/ADR-050-result-reconciliation-is-not-finding-lifecycle.md",
        "docs/decisions/ADR-051-explicit-reverification-memory-commit.md",
    ]
    missing = [value for value in required if not Path(value).is_file()]
    assert not missing


def test_execution_contract_forbids_implicit_memory_persistence():
    text = Path("specs/contracts/semantic_reverification_execution_contract.yaml").read_text()
    assert "implicit_memory_persistence: forbidden" in text


def test_reconciliation_contract_keeps_history_append_only():
    text = Path("specs/contracts/semantic_artifact_reconciliation_contract.yaml").read_text()
    assert "historical_lifecycle_mutation: false" in text
    assert "silently_marking_historical_findings_resolved" in text


def test_replay_contract_requires_explicit_selection_mode():
    text = Path("specs/contracts/semantic_replay_contract.yaml").read_text()
    assert "explicit_selection_mode: true" in text
    assert "hidden_scope_inference: false" in text
