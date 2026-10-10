"""Atomic publication primitives for detached proof artifacts.

G3.4.6 hardens the transition from temporary bytes to trusted content-addressed
artifacts. Publication is explicit, atomic, and never exposes a partially
written artifact to readers.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile

from .proof_artifact import ProofArtifactError, ProofArtifactReference


@dataclass(frozen=True)
class PublicationReceipt:
    digest: str
    byte_size: int
    committed: bool


class AtomicProofPublisher:
    """Publish already verified proof bytes into a CAS root.

    The publisher writes only to an exclusive temporary file, fsyncs content,
    atomically renames it, and rejects replacement of an existing mismatching
    object.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def publish(self, data: bytes) -> PublicationReceipt:
        if not data:
            raise ValueError("cannot publish empty proof artifact")
        digest = hashlib.sha256(data).hexdigest()
        target = self.root / f"{digest}.proof"

        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise ProofArtifactError("existing artifact is unsafe")
            if target.read_bytes() != data:
                raise ProofArtifactError("digest collision or corrupted artifact")
            return PublicationReceipt(digest, len(data), False)

        fd, name = tempfile.mkstemp(prefix=".proof-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, target)
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass
        return PublicationReceipt(digest, len(data), True)
