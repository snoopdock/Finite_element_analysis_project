from __future__ import annotations

from pathlib import Path
import pytest

from audit_engine.semantic_audit.high_assurance.proof_publication import AtomicProofPublisher
from audit_engine.semantic_audit.high_assurance.proof_artifact import ProofArtifactError


def test_atomic_publication_is_idempotent(tmp_path: Path):
    publisher = AtomicProofPublisher(tmp_path)
    first = publisher.publish(b"proof")
    second = publisher.publish(b"proof")
    assert first.committed is True
    assert second.committed is False


def test_atomic_publication_rejects_existing_unsafe_object(tmp_path: Path):
    p = AtomicProofPublisher(tmp_path)
    digest = __import__("hashlib").sha256(b"proof").hexdigest()
    (tmp_path / f"{digest}.proof").symlink_to("/tmp")
    with pytest.raises(ProofArtifactError):
        p.publish(b"proof")
