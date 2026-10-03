import json

from core.state_manager import initialize_state, save_state


def test_v5_state_migrates_to_v6_without_promoting_legacy_equations(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "topic": "FEM",
                "objective": "Guide",
                "knowledge_base": {
                    "equations": [
                        {
                            "name": "Weak form",
                            "latex": "A",
                            "source_ids": ["s1"],
                        }
                    ]
                },
                "sections": [],
            }
        ),
        encoding="utf-8",
    )

    state = initialize_state({"state": state_path}, {"topic": "FEM", "objective": "Guide"})

    assert state["schema_version"] == 6
    assert state["domain_semantic_model"]["equation_candidates"] == {}
    assert state["domain_semantic_model"]["equations"] == {}


def test_state_round_trip_preserves_domain_semantic_model(tmp_path):
    state_path = tmp_path / "state.json"
    paths = {"state": state_path}
    state = initialize_state(paths, {"topic": "FEM", "objective": "Guide"})
    state["domain_semantic_model"]["equation_candidates"]["EQC-test"] = {
        "candidate_id": "EQC-test",
        "fingerprint": "test",
        "name": "Equation",
        "expression": "A=B",
        "meaning": "Test",
        "source_ids": ["s1"],
        "status": "candidate",
    }

    save_state(paths, state)
    loaded = initialize_state(paths, {"topic": "FEM", "objective": "Guide"})

    assert loaded["domain_semantic_model"] == state["domain_semantic_model"]
