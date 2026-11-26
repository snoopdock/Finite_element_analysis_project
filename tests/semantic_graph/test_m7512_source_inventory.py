"""M7.5.12 source/extractor inventory reconciliation tests."""
from __future__ import annotations

import hashlib
import json
import unittest

from audit_engine.semantic_audit.epistemic.source_inventory import (
    SourceExtractorInventoryError,
    build_source_extractor_inventory,
    extractor_candidate_registry,
    verify_source_extractor_inventory,
)


def _seal(value):
    return hashlib.sha256(
        (json.dumps(value, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    ).hexdigest()


def _source_manifest(entries):
    ordered = sorted(entries, key=lambda row: row["path"].encode("utf-8"))
    inventory = {
        "schema": "ae32c/source-inventory/v1",
        "entry_count": len(ordered),
        "entries": ordered,
        "sha256": _seal(ordered),
    }
    manifest = {
        "manifest_schema": "ae32c/source-snapshot-manifest/v1",
        "status": "VERIFIED",
        "source_snapshot_id": "snapshot:fixture",
        "source": {"commit_oid": "a" * 40},
        "source_inventory": inventory,
        "verification": {"status": "VERIFIED"},
        "authority": {"atomic_repository_snapshot_established": False},
    }
    manifest["manifest_sha256"] = _seal(manifest)
    return manifest


class SourceExtractorInventoryTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _source_manifest([
            {"path": "src/module.py", "mode": "100644", "object_type": "blob",
             "content_sha256": "1" * 64},
            {"path": ".github/workflows/check.yml", "mode": "100644", "object_type": "blob",
             "content_sha256": "2" * 64},
            {"path": "docs/readme.md", "mode": "100644", "object_type": "blob",
             "content_sha256": "3" * 64},
            {"path": "vendor/submodule", "mode": "160000", "object_type": "commit",
             "content_sha256": None},
        ])

    def test_registry_is_versioned_and_digest_sealed(self):
        registry = extractor_candidate_registry()
        payload = {key: value for key, value in registry.items() if key != "registry_sha256"}
        self.assertEqual(registry["registry_sha256"], _seal(payload))
        self.assertEqual(registry["version"], "1.0.0")

    def test_every_source_entry_is_classified_and_candidates_are_derived(self):
        inventory = build_source_extractor_inventory(self.manifest)
        self.assertEqual(inventory["counts"]["source_unit_count"], 4)
        self.assertEqual(inventory["counts"]["extractor_candidate_count"], 2)
        self.assertEqual(
            [(item["source_path"], item["extractor_id"])
             for item in inventory["extractor_candidates"]],
            [(".github/workflows/check.yml", "workflow_static_scan"),
             ("src/module.py", "python_ast")],
        )
        self.assertEqual(inventory["unsupported_source_paths"], ["docs/readme.md"])
        self.assertEqual(inventory["gitlink_submodule_paths"], ["vendor/submodule"])
        self.assertTrue(inventory["reconciliation"]["all_source_entries_classified"])

    def test_candidate_inventory_does_not_claim_extractor_execution(self):
        inventory = build_source_extractor_inventory(self.manifest)
        self.assertEqual(
            {item["status"] for item in inventory["extractor_candidates"]},
            {"CANDIDATE_NOT_EXECUTED"},
        )
        self.assertFalse(inventory["authority"]["extractors_executed"])

    def test_declared_exclusion_remains_visible_in_source_and_candidate_records(self):
        inventory = build_source_extractor_inventory(
            self.manifest, scope_exclusions={"src/module.py": "outside declared audit scope"}
        )
        unit = next(item for item in inventory["source_units"] if item["path"] == "src/module.py")
        candidate = next(item for item in inventory["extractor_candidates"]
                         if item["source_path"] == "src/module.py")
        self.assertEqual(unit["classification"], "DECLARED_EXCLUDED")
        self.assertEqual(candidate["status"], "DECLARED_EXCLUDED")
        self.assertEqual(candidate["exclusion_reason"], "outside declared audit scope")
        self.assertEqual(inventory["counts"]["declared_excluded_source_count"], 1)

    def test_unknown_exclusion_path_is_rejected(self):
        with self.assertRaisesRegex(SourceExtractorInventoryError, "unknown_source"):
            build_source_extractor_inventory(
                self.manifest, scope_exclusions={"missing.py": "not present"}
            )

    def test_missing_exclusion_reason_is_rejected(self):
        with self.assertRaisesRegex(SourceExtractorInventoryError, "nonempty_reason"):
            build_source_extractor_inventory(
                self.manifest, scope_exclusions={"src/module.py": " "}
            )

    def test_source_manifest_must_be_postflight_verified(self):
        bad = dict(self.manifest)
        bad["status"] = "CAPTURED_PENDING_POSTFLIGHT"
        bad.pop("manifest_sha256")
        bad["manifest_sha256"] = _seal(bad)
        with self.assertRaisesRegex(SourceExtractorInventoryError, "not_postflight_verified"):
            build_source_extractor_inventory(bad)

    def test_source_manifest_digest_and_inventory_digest_are_checked(self):
        bad = dict(self.manifest)
        bad["source_inventory"] = dict(bad["source_inventory"])
        bad["source_inventory"]["entries"] = list(bad["source_inventory"]["entries"])
        bad["source_inventory"]["entries"][0] = dict(bad["source_inventory"]["entries"][0])
        bad["source_inventory"]["entries"][0]["path"] = "tampered.py"
        bad.pop("manifest_sha256")
        bad["manifest_sha256"] = _seal(bad)
        with self.assertRaisesRegex(SourceExtractorInventoryError, "inventory_digest_mismatch"):
            build_source_extractor_inventory(bad)

    def test_duplicate_source_paths_are_rejected(self):
        entries = list(self.manifest["source_inventory"]["entries"])
        entries.append(dict(entries[0]))
        bad = _source_manifest(entries)
        with self.assertRaisesRegex(SourceExtractorInventoryError, "path_invalid_or_duplicate"):
            build_source_extractor_inventory(bad)

    def test_semantic_verifier_rederives_inventory_not_just_its_hash(self):
        inventory = build_source_extractor_inventory(self.manifest)
        forged = dict(inventory)
        forged["unsupported_source_paths"] = []
        forged.pop("inventory_sha256")
        forged["inventory_sha256"] = _seal(forged)
        with self.assertRaisesRegex(SourceExtractorInventoryError, "semantic_reconciliation_mismatch"):
            verify_source_extractor_inventory(self.manifest, forged)

    def test_valid_inventory_passes_independent_verification(self):
        inventory = build_source_extractor_inventory(self.manifest)
        result = verify_source_extractor_inventory(self.manifest, inventory)
        self.assertTrue(result["semantic_integrity"])
        self.assertEqual(result["source_unit_count"], 4)
        self.assertEqual(result["extractor_candidate_count"], 2)
        self.assertFalse(result["universal_exhaustiveness_established"])

    def test_malformed_source_paths_fail_closed(self):
        bad = _source_manifest([
            {"path": "../escape.py", "mode": "100644", "object_type": "blob",
             "content_sha256": "1" * 64},
        ])
        with self.assertRaisesRegex(SourceExtractorInventoryError, "path_invalid_or_duplicate"):
            build_source_extractor_inventory(bad)


if __name__ == "__main__":
    unittest.main()
