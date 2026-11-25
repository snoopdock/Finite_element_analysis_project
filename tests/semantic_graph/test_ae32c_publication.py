from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from audit_engine.semantic_audit.ae32c.publication import (
    PublicationError, build_run_record, publish_result, verify_run_record,
)

def make_record(number=1, attempt=1, revision="a"*40, outcome="SUCCEEDED", run_id=None):
    return build_run_record(
        repository="snoopdock/Finite_element_analysis_project", source_revision=revision,
        source_snapshot_id="b"*64, graph_snapshot_id="c"*64,
        rule_registry_sha256="d"*64, finding_ledger_sha256="e"*64,
        configuration_sha256="f"*64, workflow_run_id=run_id or number,
        run_number=number, run_attempt=attempt, outcome=outcome,
    )

class PublicationTests(unittest.TestCase):
    def test_fresh_success_publishes_and_binds_all_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            result=publish_result(path,make_record(),authorized_source_revision="a"*40)
            self.assertEqual(result["decision"],"PUBLISHED")
            state=json.loads(path.read_text())
            self.assertEqual(state["current"]["source_snapshot_id"],"b"*64)
            self.assertEqual(state["current"]["finding_ledger_sha256"],"e"*64)

    def test_superseded_source_is_history_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            publish_result(path,make_record(),authorized_source_revision="a"*40)
            result=publish_result(path,make_record(2,revision="2"*40),authorized_source_revision="3"*40)
            state=json.loads(path.read_text())
            self.assertEqual(result["decision"],"HISTORICAL_ONLY")
            self.assertEqual(state["current"]["generation"],[1,1])
            self.assertEqual(len(state["history"]),2)

    def test_late_older_completion_cannot_replace_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            publish_result(path,make_record(9),authorized_source_revision="a"*40)
            result=publish_result(path,make_record(8),authorized_source_revision="a"*40)
            self.assertEqual(result["decision"],"REJECTED")
            self.assertEqual(json.loads(path.read_text())["current"]["generation"],[9,1])

    def test_equal_generation_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            publish_result(path,make_record(4),authorized_source_revision="a"*40)
            result=publish_result(path,make_record(4,run_id=444),authorized_source_revision="a"*40)
            self.assertEqual(result["decision"],"REJECTED")

    def test_cancelled_failed_and_incomplete_are_history_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            publish_result(path,make_record(),authorized_source_revision="a"*40)
            for n,outcome in enumerate(("CANCELLED","FAILED","INCOMPLETE"),2):
                result=publish_result(path,make_record(n,outcome=outcome),authorized_source_revision="a"*40)
                self.assertEqual(result["decision"],"HISTORICAL_ONLY")
            state=json.loads(path.read_text())
            self.assertEqual(state["current"]["generation"],[1,1])
            self.assertEqual(len(state["history"]),4)

    def test_non_push_event_is_history_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=publish_result(Path(tmp)/"state.json",make_record(),
                authorized_source_revision="a"*40,event_name="pull_request")
            self.assertEqual(result["decision"],"HISTORICAL_ONLY")

    def test_tampered_record_is_rejected(self):
        item=make_record()
        item["finding_ledger_sha256"]="0"*64
        with self.assertRaisesRegex(PublicationError,"run_record_integrity_invalid"):
            verify_run_record(item)

    def test_concurrent_writers_preserve_history_and_highest_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            records=[make_record(n) for n in range(1,9)]
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda r:publish_result(path,r,authorized_source_revision="a"*40),records))
            state=json.loads(path.read_text())
            self.assertEqual(len(state["history"]),8)
            self.assertEqual(state["current"]["generation"],[8,1])

if __name__=="__main__":
    unittest.main()
