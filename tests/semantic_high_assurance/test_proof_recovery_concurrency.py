from pathlib import Path
import pytest
from audit_engine.semantic_audit.high_assurance.proof_publication import AtomicProofPublisher
from audit_engine.semantic_audit.high_assurance.proof_artifact import ProofArtifactError

def test_stale_temp_recovery(tmp_path: Path):
    stale = tmp_path / ".proof-old"
    stale.write_bytes(b"partial")
    publisher = AtomicProofPublisher(tmp_path)
    publisher.recover_stale_temporary_files(max_age_seconds=0)
    assert not stale.exists()

def test_lock_blocks_second_writer(tmp_path: Path):
    publisher = AtomicProofPublisher(tmp_path)
    publisher.lock.write_text("busy")
    with pytest.raises(ProofArtifactError):
        publisher.publish(b"proof")
