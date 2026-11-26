"""M7.5.10 durable dossier, restart, gap-reconciliation and tamper tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_engine.semantic_audit.epistemic import (
    AssuranceClaim, AssuranceStore, CoverageDossierStore,
    CoverageObligation, EpistemicStore, GapKind, GapState,
    KnowledgeGap, ObligationDisposition,
    build_and_persist_coverage_dossier, build_rule_derived_coverage_manifest,
    derive_rule_coverage_plan, verify_dossier_against_current_stores,
)
from audit_engine.semantic_audit.epistemic.coverage_dossier import CoverageDossierError


class CoverageDossierTests(unittest.TestCase):
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
            "claim:m7510", "prop:m7510", "repository", "scope:repo",
            "snapshot:m7510", "M7.5.10 test claim",
        )
        self.assurance.record(self.claim)
        self.plan = derive_rule_coverage_plan(
            self.claim, source_snapshot_id="snapshot:m7510",
            graph_snapshot_id="graph:m7510",
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

    def manifest_for(self, gap_id):
        return build_rule_derived_coverage_manifest(
            self.claim, self.plan,
            assessments={
                self.obligation_id: CoverageObligation(
                    self.obligation_id, ObligationDisposition.UNKNOWN,
                    gap_ids=(gap_id,),
                )
            },
        )

    def build(self, dossier_id, gap_id, mapping):
        return build_and_persist_coverage_dossier(
            dossier_id=dossier_id, claim=self.claim, plan=self.plan,
            manifest=self.manifest_for(gap_id),
            gap_to_obligations=mapping,
            captured_at="2026-11-27T12:00:00Z",
            assurance_store=self.assurance, epistemic_store=self.epistemic,
            dossier_store=self.dossiers,
        )

    def test_persisted_dossier_survives_restart_and_recovery(self):
        self.add_gap("gap:assigned")
        dossier = self.build(
            "dossier:restart", "gap:assigned",
            {"gap:assigned": (self.obligation_id,)},
        )
        self.assertTrue(dossier.snapshot_consistent)
        self.assertEqual(dossier.unreconciled_gap_ids, ())
        self.assertTrue(self.dossiers.verify_integrity())
        self.dossiers.close()
        self.dossiers = CoverageDossierStore(self.dossier_path)
        recovered = self.dossiers.get("dossier:restart")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["plan"]["graph_snapshot_id"], "graph:m7510")
        self.assertEqual(recovered["gap_inventory"][0]["gap_id"], "gap:assigned")
        self.assertTrue(self.dossiers.verify_integrity())

    def test_gap_absent_from_manifest_reconciliation_is_not_silently_ignored(self):
        self.add_gap("gap:assigned")
        self.add_gap("gap:orphan")
        dossier = self.build(
            "dossier:orphan", "gap:assigned",
            {"gap:assigned": (self.obligation_id,)},
        )
        self.assertEqual(dossier.unreconciled_gap_ids, ("gap:orphan",))
        self.assertEqual(dossier.overall_status, "incomplete")

    def test_gap_mapping_must_be_reflected_in_assessed_obligation(self):
        self.add_gap("gap:assigned")
        with self.assertRaisesRegex(CoverageDossierError, "not represented"):
            self.build(
                "dossier:bad-map", "gap:assigned",
                {"gap:assigned": (self.plan.expected_obligation_ids[1],)},
            )

    def test_mapping_to_nonexistent_gap_is_rejected(self):
        with self.assertRaisesRegex(CoverageDossierError, "absent persisted gaps"):
            self.build(
                "dossier:missing-gap", "gap:manifest-only",
                {"gap:does-not-exist": (self.obligation_id,)},
            )

    def test_source_ledger_mutation_is_detected_after_capture(self):
        self.add_gap("gap:assigned")
        self.build(
            "dossier:stale", "gap:assigned",
            {"gap:assigned": (self.obligation_id,)},
        )
        self.add_gap("gap:later")
        verified = verify_dossier_against_current_stores(
            "dossier:stale", assurance_store=self.assurance,
            epistemic_store=self.epistemic, dossier_store=self.dossiers,
        )
        self.assertFalse(verified["current_epistemic_snapshot_matches"])
        self.assertTrue(verified["current_assurance_snapshot_matches"])

    def test_assurance_ledger_mutation_is_detected_after_capture(self):
        self.add_gap("gap:assigned")
        self.build(
            "dossier:assurance-stale", "gap:assigned",
            {"gap:assigned": (self.obligation_id,)},
        )
        self.assurance.record(AssuranceClaim(
            "claim:later", "prop:later", "repository", "scope:repo",
            "snapshot:later", "Later claim",
        ))
        verified = verify_dossier_against_current_stores(
            "dossier:assurance-stale", assurance_store=self.assurance,
            epistemic_store=self.epistemic, dossier_store=self.dossiers,
        )
        self.assertTrue(verified["current_epistemic_snapshot_matches"])
        self.assertFalse(verified["current_assurance_snapshot_matches"])

    def test_dossier_ledger_detects_out_of_band_tampering(self):
        self.add_gap("gap:assigned")
        self.build(
            "dossier:tamper", "gap:assigned",
            {"gap:assigned": (self.obligation_id,)},
        )
        self.dossiers.close()
        raw = sqlite3.connect(self.dossier_path)
        raw.execute("DROP TRIGGER coverage_dossier_no_update")
        raw.execute(
            "UPDATE coverage_dossier_events SET payload = '{}' WHERE dossier_id = ?",
            ("dossier:tamper",),
        )
        raw.commit()
        raw.close()
        self.dossiers = CoverageDossierStore(self.dossier_path)
        self.assertFalse(self.dossiers.verify_integrity())
        with self.assertRaisesRegex(CoverageDossierError, "integrity failure"):
            self.dossiers.get("dossier:tamper")

    def test_append_only_trigger_blocks_update_and_delete(self):
        self.add_gap("gap:assigned")
        self.build(
            "dossier:append-only", "gap:assigned",
            {"gap:assigned": (self.obligation_id,)},
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.dossiers._db.execute(
                "UPDATE coverage_dossier_events SET payload = '{}' WHERE dossier_id = ?",
                ("dossier:append-only",),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.dossiers._db.execute(
                "DELETE FROM coverage_dossier_events WHERE dossier_id = ?",
                ("dossier:append-only",),
            )


if __name__ == "__main__":
    unittest.main()
