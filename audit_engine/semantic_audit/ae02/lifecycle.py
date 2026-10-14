"""Finding lifecycle transitions.

No transition implies correctness. The manager only records evidence-backed
state changes.
"""
from dataclasses import dataclass, field

VALID = {
    "observed": {"verified", "rejected"},
    "verified": {"accepted", "resolved"},
    "accepted": {"resolved", "regression"},
    "resolved": {"regression"},
    "regression": {"verified"},
    "rejected": set(),
}

@dataclass
class FindingLifecycleManager:
    state: dict[str, str] = field(default_factory=dict)
    history: list = field(default_factory=list)

    def transition(self, finding_id, new_state, evidence_id):
        old = self.state.get(finding_id)
        if old and new_state not in VALID.get(old, set()):
            raise ValueError(f"invalid transition {old}->{new_state}")
        self.state[finding_id] = new_state
        self.history.append(
            {"finding": finding_id, "from": old, "to": new_state,
             "evidence": evidence_id}
        )
        return self.state[finding_id]
