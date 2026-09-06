import copy

import main


def proposal():
    return {
        "attention_id": "ATT-1",
        "policy_version": "r7b-v1",
        "query_scope": "weak_form_galerkin_fem",
        "provider": "semantic_scholar",
        "attention_reason": "Repeated operational retrieval issue.",
        "observed_condition": "provider_unavailable",
        "lifecycle_status": "open",
        "supporting_event_ids": ["EV-1"],
        "recommended_acquisition_action": "retry_or_alternative_provider",
    }


def test_main_boundary_does_not_invoke_planning_without_proposals(monkeypatch):
    state = {main.RESEARCH_PLANNING_RESULT_FIELD: [{"old": True}]}
    calls = []

    def fake_prepare(*args, **kwargs):
        calls.append((args, kwargs))
        return [{"unexpected": True}]

    monkeypatch.setattr(main, "prepare_research_acquisition_flow", fake_prepare)

    result = main._integrate_research_planning(
        state,
        {},
        {"attention_proposals": []},
    )

    assert result is None
    assert calls == []
    assert main.RESEARCH_PLANNING_RESULT_FIELD not in state


def test_main_boundary_preserves_coordinator_result(monkeypatch):
    source_proposals = [proposal()]
    composed = [
        {
            "attention_proposal": source_proposals[0],
            "research_planning_signal": {"source_attention_id": "ATT-1"},
            "research_planning_decision": {"decision_type": "formulate_acquisition_request"},
        }
    ]
    expected = copy.deepcopy(composed)
    calls = []

    def fake_prepare(proposals, *, planning_context=None, operational_constraints=None):
        calls.append((proposals, planning_context, operational_constraints))
        return composed

    monkeypatch.setattr(main, "prepare_research_acquisition_flow", fake_prepare)

    state = {}
    config = {
        "research_planning": {
            "planning_context": {"alternative_providers": ["arxiv"]},
            "operational_constraints": {"execution_limits": {"max_attempts": 2}},
        }
    }

    result = main._integrate_research_planning(
        state,
        config,
        {"attention_proposals": source_proposals},
    )

    assert result == expected
    assert state[main.RESEARCH_PLANNING_RESULT_FIELD] == expected
    assert calls == [
        (
            source_proposals,
            {"alternative_providers": ["arxiv"]},
            {"execution_limits": {"max_attempts": 2}},
        )
    ]


def test_main_boundary_propagates_planning_failure(monkeypatch):
    def fake_prepare(*args, **kwargs):
        raise ValueError("planning failure")

    monkeypatch.setattr(main, "prepare_research_acquisition_flow", fake_prepare)

    state = {}

    try:
        main._integrate_research_planning(
            state,
            {},
            {"attention_proposals": [proposal()]},
        )
    except ValueError as exc:
        assert str(exc) == "planning failure"
    else:
        raise AssertionError("planning failure was not propagated")

    assert main.RESEARCH_PLANNING_RESULT_FIELD not in state
