from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.high_assurance import (
    DRAT_PROOF_FORMAT,
    DETACHED_UNSAT_PROOF_KIND,
    LocalContentAddressedProofStore,
    PROOF_ARTIFACT_FORMAT,
    PROOF_ARTIFACT_MEDIA_TYPE,
    ProofArtifactError,
    ProofArtifactReference,
    ProofArtifactStoreRegistry,
    RUP_PROOF_FORMAT,
)


def _artifact_bytes(proof_format: str, cnf_digest: str, steps) -> bytes:
    lines = [
        {
            "artifact_format": PROOF_ARTIFACT_FORMAT,
            "proof_format": proof_format,
            "cnf_digest": cnf_digest,
        },
        *steps,
    ]
    return b"".join(
        (json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for line in lines
    )


def test_reference_contains_identity_not_location():
    payload = {
        "kind": DETACHED_UNSAT_PROOF_KIND,
        "store_id": "proofs",
        "artifact_sha256": "a" * 64,
        "byte_size": 12,
        "proof_format": RUP_PROOF_FORMAT,
        "cnf_digest": "b" * 64,
        "artifact_format": PROOF_ARTIFACT_FORMAT,
        "media_type": PROOF_ARTIFACT_MEDIA_TYPE,
    }
    reference = ProofArtifactReference.from_mapping(payload)
    assert reference.to_dict()["store_id"] == "proofs"
    assert "path" not in reference.to_dict()
    assert "url" not in reference.to_dict()


def test_reference_rejects_solver_supplied_path_or_url():
    base = {
        "kind": DETACHED_UNSAT_PROOF_KIND,
        "store_id": "proofs",
        "artifact_sha256": "a" * 64,
        "byte_size": 12,
        "proof_format": RUP_PROOF_FORMAT,
        "cnf_digest": "b" * 64,
        "artifact_format": PROOF_ARTIFACT_FORMAT,
        "media_type": PROOF_ARTIFACT_MEDIA_TYPE,
    }
    with pytest.raises(ValueError, match="unknown fields"):
        ProofArtifactReference.from_mapping({**base, "path": "/tmp/proof"})
    with pytest.raises(ValueError, match="unknown fields"):
        ProofArtifactReference.from_mapping({**base, "url": "https://example.invalid/proof"})


def test_content_addressed_store_put_and_verified_open(tmp_path: Path):
    digest = "b" * 64
    data = _artifact_bytes(RUP_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    store = LocalContentAddressedProofStore(tmp_path, store_id="proofs")
    reference = store.put_bytes(data, proof_format=RUP_PROOF_FORMAT, cnf_digest=digest)
    assert reference.artifact_sha256 == hashlib.sha256(data).hexdigest()
    with store.open_verified(reference, max_bytes=len(data)) as handle:
        assert handle.read() == data


def test_content_store_rejects_tampered_bytes(tmp_path: Path):
    digest = "b" * 64
    data = _artifact_bytes(RUP_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    store = LocalContentAddressedProofStore(tmp_path, store_id="proofs")
    reference = store.put_bytes(data, proof_format=RUP_PROOF_FORMAT, cnf_digest=digest)
    path = tmp_path / f"{reference.artifact_sha256}.proof"
    tampered = bytearray(data)
    tampered[-2] = ord(" ")
    path.write_bytes(bytes(tampered))
    with pytest.raises(ProofArtifactError, match="SHA-256 mismatch"):
        with store.open_verified(reference, max_bytes=len(data)):
            pass


def test_content_store_rejects_size_mismatch(tmp_path: Path):
    digest = "b" * 64
    data = _artifact_bytes(DRAT_PROOF_FORMAT, digest, [{"op": "add", "clause": []}])
    store = LocalContentAddressedProofStore(tmp_path, store_id="proofs")
    reference = store.put_bytes(data, proof_format=DRAT_PROOF_FORMAT, cnf_digest=digest)
    wrong = ProofArtifactReference(
        store_id=reference.store_id,
        artifact_sha256=reference.artifact_sha256,
        byte_size=reference.byte_size + 1,
        proof_format=reference.proof_format,
        cnf_digest=reference.cnf_digest,
    )
    with pytest.raises(ProofArtifactError, match="byte_size mismatch"):
        with store.open_verified(wrong, max_bytes=wrong.byte_size):
            pass


def test_store_registry_is_explicit_and_rejects_duplicates(tmp_path: Path):
    registry = ProofArtifactStoreRegistry()
    first = LocalContentAddressedProofStore(tmp_path / "a", store_id="proofs")
    registry.register(first)
    assert registry.ids() == ("proofs",)
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(LocalContentAddressedProofStore(tmp_path / "b", store_id="proofs"))
