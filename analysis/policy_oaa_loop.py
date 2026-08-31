#!/usr/bin/env python3
"""Policy-aware OAA loop adapter."""

from __future__ import annotations

from typing import Dict, List, Optional

from analysis.oaa_loop import OAALoop
from analysis.oaa_policy import OAAActionPolicy


class PolicyAwareOAALoop(OAALoop):
    """OAALoop with explicit anomaly/action prioritization."""

    def __init__(
        self,
        config: Dict,
        section_splitter,
        section_merger,
    ) -> None:
        super().__init__(
            config,
            section_splitter,
            section_merger,
        )

        writing = config.get(
            "writing",
            {},
        )
        oaa_config = config.get(
            "oaa",
            {},
        )
        oaa_policy = writing.get(
            "oaa_action_policy",
            oaa_config.get("action_policy", {}),
        )
        if not isinstance(oaa_policy, dict):
            oaa_policy = {}

        self.action_policy = OAAActionPolicy(
            severity_weights=oaa_policy.get(
                "severity_weights",
                oaa_config.get("severity_weights"),
            ),
            cost_weights=oaa_policy.get(
                "cost_weights",
                oaa_config.get("cost_weights"),
            ),
            persistence_weight=oaa_policy.get(
                "persistence_weight",
                oaa_config.get("persistence_weight", 0.35),
            ),
            severity_weight=oaa_policy.get(
                "severity_weight",
                oaa_config.get("severity_weight", 0.50),
            ),
            cost_weight=oaa_policy.get(
                "cost_weight",
                oaa_config.get("cost_weight", 0.15),
            ),
        )

    def adjust(
        self,
        actionable_anomalies: List[Dict],
    ) -> Optional[Dict]:
        decision = self.action_policy.choose(
            actionable_anomalies,
            self.anomaly_counts,
        )
        if decision is None:
            return None

        adjustment = super().adjust(
            [
                anomaly
                for anomaly in actionable_anomalies
                if isinstance(anomaly, dict)
                and str(anomaly.get("key", "")) == decision.key
            ][:1]
        )

        if adjustment is None:
            return None

        adjustment["adjustment_score"] = decision.to_dict()["score"]
        adjustment["decision_record"] = decision.to_dict()
        return adjustment
