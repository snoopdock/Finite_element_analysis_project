"""Tests for machine-verification ledger invariants."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.ae32d_validate_benchmark import check_case_gate


class MachineLedgerContractTests(unittest.TestCase):
    def test_ledger_records_are_not_primary_gold(self):
        path = Path("evaluation/ae32d/machine-verification-ledger.json")
        ledger = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["status"], "evidence_only_not_gold_adjudication")
        self.assertEqual(len(ledger["records"]), 6)
        self.assertTrue(all(r["primary_benchmark_eligible"] is False for r in ledger["records"]))
        self.assertTrue(all(r["human_independent_adjudication"] == "not_performed" for r in ledger["records"]))

    def test_case_source_identity_is_recorded_for_every_manifest_case(self):
        manifest = json.loads(Path("evaluation/ae32d/manifest.json").read_text(encoding="utf-8"))
        ledger = json.loads(Path("evaluation/ae32d/machine-verification-ledger.json").read_text(encoding="utf-8"))
        cases = {e["case_id"] for e in manifest["cases"]}
        records = {e["case_id"] for e in ledger["records"]}
        self.assertEqual(records, cases)
        self.assertEqual(len(records), len(ledger["records"]))


if __name__ == "__main__":
    unittest.main()
