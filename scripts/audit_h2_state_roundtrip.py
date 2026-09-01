#!/usr/bin/env python3
"""Audit JSON round-trip preservation for the hardened scientific state layers."""

from __future__ import annotations

import copy
import json

from core.epistemic_state_store import record_epistemic_state
from core.validity_state import record_validity_scope
from core.scientific_attention_state import record_scientific_attention


def main() -> int:
    state = {
        "knowledge_graph": {
            "propositions": {
                "p-001": {
                    "proposition_id": "p-001",
                    "statement": "Method A converges under coercivity.",
                    "source_ids": ["s-001"],
                }
            },
            "evidence_relations": {
                "er-001": {
                    "evidence_relation_id": "er-001",
                    "source_id": "s-001",
                    "proposition_id": "p-001",
                    "relationship": "supports",
                    "passage_ids": ["passage-001"],
                    "status": "active",
                }
            },
        }
    }

    validity = {
        "validity_id": "v-001",
        "proposition_id": "p-001",
        "type": "conditional",
        "framework": "Galerkin FEM",
        "conditions": ["coercive operator"],
        "evidence_relation_ids": ["er-001"],
        "status": "proposed",
    }
    assert record_validity_scope(state, validity)

    epistemic = {
        "status": "conditional",
        "evidence_strength": "moderate",
        "literature_agreement": "mixed",
        "model_confidence": 0.82,
    }
    assert record_epistemic_state(
        state,
        "p-001",
        epistemic,
        entity_type="proposition",
    )

    attention = {
        "evidence_gap": 0.6,
        "disagreement": 0.5,
        "contextual_complexity": 0.3,
        "verification_need": 0.8,
        "importance": 0.7,
        "decision_consequence": 0.9,
    }
    assert record_scientific_attention(
        state,
        "p-001",
        attention,
        entity_type="proposition",
    )

    before = copy.deepcopy(state)
    encoded = json.dumps(state, sort_keys=True, ensure_ascii=False)
    after = json.loads(encoded)

    assert after == before
    assert after["knowledge_graph"]["propositions"]["p-001"]["proposition_id"] == "p-001"
    assert after["knowledge_graph"]["evidence_relations"]["er-001"]["passage_ids"] == ["passage-001"]
    assert after["knowledge_graph"]["validity_scopes"]["v-001"]["evidence_relation_ids"] == ["er-001"]
    assert after["knowledge_graph"]["epistemic_states"]["proposition:p-001"]["model_confidence"] == 0.82
    assert after["knowledge_graph"]["scientific_attention"]["proposition:p-001"]["signals"]["decision_consequence"] == 0.9

    print("H2 state round-trip audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
