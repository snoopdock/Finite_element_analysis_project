"""Package an independently validated CI evidence directory into an immutable CAS.

Only called by the manual GitHub dispatcher *after* the trusted main-branch
verifier has accepted the report and checkout provenance. Produces a copied
bundle and a receipt in the workflow's uploaded evidence-artifacts folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from audit_engine.semantic_audit.high_assurance.validation_evidence_store import (
    EvidenceBundleStore,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--store-dir", required=True)
    args = parser.parse_args()

    evidence = Path(args.evidence_dir)
    store = EvidenceBundleStore(args.store_dir)
    receipt = store.publish(evidence)
    verified = store.verify(receipt.bundle_sha256)
    if verified.report_sha256 != receipt.report_sha256:
        raise RuntimeError("Published bundle did not verify")

    # Copy only after publication+verification, never directly into the input
    # evidence directory before deriving the manifest / bundle digest.
    destination = evidence / "bundles"
    destination.mkdir(exist_ok=False)
    name = f"{receipt.bundle_sha256}.validation.zip"
    shutil.copyfile(store.root / name, destination / name)
    report = json.loads((evidence / "validation_report.json").read_text(encoding="utf-8"))
    receipt_json = {
        "schema_version": "validation-evidence-cas-receipt/v1",
        "bundle_sha256": receipt.bundle_sha256,
        "report_sha256": receipt.report_sha256,
        "byte_size": receipt.byte_size,
        "source_profile_id": report["profile_id"],
        "source_commit_sha": report["target_commit_sha"],
        "engine_commit_sha": report["engine_commit_sha"],
        "github_run_id": report.get("github_run_id"),
        "github_run_attempt": report.get("github_run_attempt"),
    }
    raw = (json.dumps(receipt_json, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    (evidence / "bundle_receipt.json").write_bytes(raw)
    (evidence / "bundle_receipt.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  bundle_receipt.json\n", encoding="ascii"
    )
    print(f"Verified evidence CAS bundle: {receipt.bundle_sha256}")
    print(f"Source report digest: {receipt.report_sha256}")
    print(f"Published bundle size: {receipt.byte_size} bytes")
    print(f"Evidence bundle path: {destination / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
