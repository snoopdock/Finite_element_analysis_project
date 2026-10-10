"""Recovery and concurrency hardening for proof artifact publication.

G3.4.7 extends G3.4.6 atomic publication with:
- advisory writer locking
- stale temporary artifact handling
- recovery inspection
- safer publication boundaries
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
import time

from .proof_artifact import ProofArtifactError


@dataclass(frozen=True)
class PublicationReceipt:
    digest: str
    byte_size: int
    committed: bool


class AtomicProofPublisher:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = self.root / ".publication.lock"

    def _acquire_lock(self):
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            return fd
        except FileExistsError:
            raise ProofArtifactError("publication already in progress")

    def _release_lock(self, fd):
        os.close(fd)
        try:
            self.lock.unlink()
        except FileNotFoundError:
            pass

    def recover_stale_temporary_files(self, max_age_seconds: int = 3600):
        now = time.time()
        for item in self.root.glob(".proof-*"):
            if item.is_file() and now - item.stat().st_mtime > max_age_seconds:
                item.unlink()

    def publish(self, data: bytes) -> PublicationReceipt:
        if not data:
            raise ValueError("cannot publish empty proof artifact")

        self.recover_stale_temporary_files()

        digest = hashlib.sha256(data).hexdigest()
        target = self.root / f"{digest}.proof"

        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise ProofArtifactError("existing artifact is unsafe")
            if target.read_bytes() != data:
                raise ProofArtifactError("digest collision or corrupted artifact")
            return PublicationReceipt(digest, len(data), False)

        fd_lock = self._acquire_lock()
        try:
            if target.exists():
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
        finally:
            self._release_lock(fd_lock)

        return PublicationReceipt(digest, len(data), True)
