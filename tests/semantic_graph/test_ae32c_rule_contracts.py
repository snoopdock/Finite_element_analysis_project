import unittest

from audit_engine.semantic_audit.ae32c.rule_contracts import (
    RuleContractError,
    build_finding_ledger,
    digest,
    rule_registry,
    verify_finding_ledger,
)


def source_manifest():
    return {
        "source_snapshot_id": "a" * 64,
        "source_inventory": {"entries": [
            {"path": "src/a.py", "content_sha256": "b" * 64},
        ]},
    }


def graph_manifest(status="COMPLETE_WITH_DECLARED_EXCLUSIONS"):
    return {
        "graph_snapshot_id": "c" * 64,
        "source_snapshot_id": "a" * 64,
        "coverage": {
            "status": status,
            "unaccounted_count": 0,
            "source_units": [{
                "path": "src/a.py", "status": "represented",
                "source_content_sha256": "b" * 64,
            }],
        },
    }


def graph():
    return {"nodes": [{"id": "file:src/a.py", "type": "PythonSourceFile"}], "edges": []}


class RuleContractTests(unittest.TestCase):
    def _ledger(self, findings, coverage_status="COMPLETE_WITH_DECLARED_EXCLUSIONS"):
        return build_finding_ledger(
            findings, source_manifest(), graph_manifest(coverage_status), graph(), rule_registry()
        )

    def test_positive_finding_is_bound_to_source_graph_and_rule(self):
        ledger = self._ledger([{
            "id": "AE32A-AE28-EXTERNAL-MODEL-INPUT",
            "severity": "medium",
            "title": "External model input",
            "statement": "An external response intake path exists.",
            "limitation": "Static source observation.",
            "evidence": [{"path": "src/a.py", "line": 12, "kind": "external_model_response_intake",
                         "detail": "validated response intake"}],
        }])
        finding = ledger["findings"][0]
        self.assertEqual(finding["claim_status"], "EVIDENCE_BOUND")
        self.assertEqual(finding["source_snapshot_id"], "a" * 64)
        self.assertEqual(finding["graph_snapshot_id"], "c" * 64)
        self.assertEqual(finding["evidence"][0]["graph_node_id"], "file:src/a.py")
        verify_finding_ledger(ledger)

    def test_absence_finding_abstains_without_closed_world_contract(self):
        ledger = self._ledger([{
            "id": "AE32A-NO-TOOL-LOOP",
            "severity": "high",
            "title": "No tool loop observed",
            "statement": "No explicit tool loop was detected.",
            "limitation": "Heuristic static scan.",
            "evidence": [],
        }])
        finding = ledger["findings"][0]
        self.assertEqual(finding["claim_status"], "ABSTAIN")
        self.assertEqual(finding["status_reason"], "closed_world_contract_not_defined")
        self.assertFalse(ledger["authority"]["absence_claims_authorized"])

    def test_incomplete_coverage_prevents_supported_positive_claim(self):
        ledger = self._ledger([{
            "id": "AE32A-AE28-EXTERNAL-MODEL-INPUT",
            "severity": "medium", "title": "External input", "statement": "Observed.",
            "limitation": "Static.", "evidence": [
                {"path": "src/a.py", "line": 1, "kind": "external_model_response_intake", "detail": "x"}
            ],
        }], "INCOMPLETE")
        self.assertEqual(ledger["findings"][0]["claim_status"], "ABSTAIN")

    def test_evidence_outside_snapshot_is_not_accepted(self):
        ledger = self._ledger([{
            "id": "AE32A-AE28-EXTERNAL-MODEL-INPUT",
            "severity": "medium", "title": "External input", "statement": "Observed.",
            "limitation": "Static.", "evidence": [
                {"path": "missing.py", "line": 1, "kind": "external_model_response_intake", "detail": "x"}
            ],
        }])
        self.assertEqual(ledger["findings"][0]["claim_status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("evidence_source_not_in_snapshot", ledger["findings"][0]["evidence_issues"])

    def test_unknown_rule_fails_closed(self):
        with self.assertRaisesRegex(RuleContractError, "unknown_or_ambiguous_rule"):
            self._ledger([{"id": "UNREGISTERED", "evidence": []}])

    def test_ledger_tampering_is_rejected(self):
        ledger = self._ledger([{
            "id": "AE32A-NO-TOOL-LOOP", "severity": "high", "title": "No loop",
            "statement": "No loop observed.", "limitation": "Static.", "evidence": [],
        }])
        ledger["findings"][0]["statement"] = "Tampered"
        with self.assertRaisesRegex(RuleContractError, "finding_ledger_digest_mismatch"):
            verify_finding_ledger(ledger)

    def test_registry_tampering_is_rejected(self):
        registry = rule_registry()
        registry["rules"][0]["claim_polarity"] = "positive"
        with self.assertRaisesRegex(RuleContractError, "rule_registry_digest_mismatch"):
            build_finding_ledger([], source_manifest(), graph_manifest(), graph(), registry)

    def test_finding_identity_changes_with_graph_snapshot(self):
        first = self._ledger([{
            "id": "AE32A-NO-TOOL-LOOP", "severity": "high", "title": "No loop",
            "statement": "No loop observed.", "limitation": "Static.", "evidence": [],
        }])
        other_graph = graph_manifest()
        other_graph["graph_snapshot_id"] = "d" * 64
        second = build_finding_ledger([{
            "id": "AE32A-NO-TOOL-LOOP", "severity": "high", "title": "No loop",
            "statement": "No loop observed.", "limitation": "Static.", "evidence": [],
        }], source_manifest(), other_graph, graph(), rule_registry())
        self.assertNotEqual(first["findings"][0]["finding_id"], second["findings"][0]["finding_id"])


if __name__ == "__main__":
    unittest.main()
