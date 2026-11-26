"""M7.5.11 independent dossier semantic-verification and replay tests."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, AssuranceStore, CoverageDossierStore,
    CoverageObligation, EpistemicStore, GapKind, GapState,
    KnowledgeGap, ObligationDisposition,
    build_and_persist_coverage_dossier, build_rule_derived_coverage_manifest,
    derive_rule_coverage_plan, verify_coverage_dossier_replay,
)
from audit_engine.semantic_audit.epistemic.coverage_dossier import CoverageDossierError


class DossierVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.epistemic_path = root / "epistemic.sqlite"
        self.assurance_path = root / "assurance.sqlite"
        self.dossier_path = root / "dossiers.sqlite"
        self.epistemic = EpistemicStore(self.epistemic_path)
        self.assurance = AssuranceStore(self.assurance_path)
        self.dossiers = CoverageDossierStore(self.dossier_path)
        self.claim = AssuranceClaim(
            "claim:m7511", "prop:m7511", "repository", "scope:repo",
            "snapshot:m7511", "M7.5.11 verifier test claim",
        )
        self.assurance.record(self.claim)
        self.plan = derive_rule_coverage_plan(
            self.claim, source_snapshot_id="snapshot:m7511",
            graph_snapshot_id="graph:m7511",
            rule_ids=("AE32A-AE28-EXTERNAL-MODEL-INPUT",),
        )
        self.obligation_id = self.plan.expected_obligation_ids[0]

    def tearDown(self):
        self.dossiers.close()
        self.assurance.close()
        self.epistemic.close()
        self.temp.cleanup()

    def add_gap(self, gap_id):
        self.epistemic.record_gap(KnowledgeGap(
            gap_id, "source:unit-1", GapKind.PARTIAL_EXTRACTION,
            GapState.OPEN, "scope:repo", "inventory:v1",
            "The source unit has not been fully inspected",
        ))

    def build(self):
        self.add_gap("gap:assigned")
        manifest = build_rule_derived_coverage_manifest(
            self.claim, self.plan,
            assessments={
                self.obligation_id: CoverageObligation(
                    self.obligation_id, ObligationDisposition.UNKNOWN,
                    gap_ids=("gap:assigned",),
                )
            },
        )
        return build_and_persist_coverage_dossier(
            dossier_id="dossier:m7511", claim=self.claim, plan=self.plan,
            manifest=manifest,
            gap_to_obligations={"gap:assigned": (self.obligation_id,)},
            captured_at="2026-11-27T00:00:00Z",
            assurance_store=self.assurance, epistemic_store=self.epistemic,
            dossier_store=self.dossiers,
        )

    def verify(self):
        return verify_coverage_dossier_replay(
            "dossier:m7511", assurance_store=self.assurance,
            epistemic_store=self.epistemic, dossier_store=self.dossiers,
        )

    def test_unchanged_dossier_passes_semantic_check_and_exact_replay(self):
        self.build()
        result = self.verify()
        self.assertTrue(result["dossier_ledger_integrity"])
        self.assertTrue(result["semantic_integrity"])
        self.assertTrue(result["source_snapshots_match"])
        self.assertTrue(result["captured_gap_inventory_matches"])
        self.assertTrue(result["replay_performed"])
        self.assertTrue(result["replay_matches"])

    def test_source_drift_preserves_historical_semantics_but_prevents_replay(self):
        self.build()
        self.add_gap("gap:later")
        result = self.verify()
        self.assertTrue(result["semantic_integrity"])
        self.assertFalse(result["source_snapshots_match"])
        self.assertFalse(result["replay_performed"])
        self.assertIsNone(result["replay_matches"])

    def test_rehashed_manifest_tampering_is_rejected_semantically(self):
        self.build()
        self.dossiers.close()
        raw = sqlite3.connect(self.dossier_path)
        raw.execute("DROP TRIGGER coverage_dossier_no_update")
        row = raw.execute(
            "SELECT sequence, dossier_id, payload, previous_hash FROM coverage_dossier_events"
        ).fetchone()
        sequence, dossier_id, payload, previous_hash = row
        decoded = json.loads(payload)
        decoded["manifest"]["expected_obligation_ids"] = decoded["manifest"]["expected_obligation_ids"][:-1]
        replacement = json.dumps(decoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload_hash = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
        event_material = f"{sequence}\n{dossier_id}\n{payload_hash}\n{previous_hash}"
        event_hash = hashlib.sha256(event_material.encode("utf-8")).hexdigest()
        raw.execute(
            "UPDATE coverage_dossier_events SET payload=?, payload_sha256=?, event_hash=? WHERE dossier_id=?",
            (replacement, payload_hash, event_hash, dossier_id),
        )
        raw.commit()
        raw.close()
        self.dossiers = CoverageDossierStore(self.dossier_path)
        with self.assertRaisesRegex(CoverageDossierError, "derived_obligation_universe_mismatch"):
            self.verify()

    def test_rehashed_status_tampering_is_rejected(self):
        self.build()
        self.dossiers.close()
        raw = sqlite3.connect(self.dossier_path)
        raw.execute("DROP TRIGGER coverage_dossier_no_update")
        sequence, dossier_id, payload, previous_hash = raw.execute(
            "SELECT sequence, dossier_id, payload, previous_hash FROM coverage_dossier_events"
        ).fetchone()
        decoded = json.loads(payload)
        decoded["overall_status"] = "evidence_complete_within_declared_manifest"
        replacement = json.dumps(decoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload_hash = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
        event_hash = hashlib.sha256(
            f"{sequence}\n{dossier_id}\n{payload_hash}\n{previous_hash}".encode("utf-8")
        ).hexdigest()
        raw.execute(
            "UPDATE coverage_dossier_events SET payload=?, payload_sha256=?, event_hash=? WHERE dossier_id=?",
            (replacement, payload_hash, event_hash, dossier_id),
        )
        raw.commit()
        raw.close()
        self.dossiers = CoverageDossierStore(self.dossier_path)
        with self.assertRaisesRegex(CoverageDossierError, "overall status violates"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
