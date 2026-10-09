"""Detached, content-addressed proof artifacts for G3.4.5.

Large UNSAT proof certificates must not be trusted merely because an external
solver names a file or URL.  This module defines a narrow repository-owned
artifact reference and explicit store registry:

* proof references contain identity/size/format metadata only -- never a path or URL,
* store locations are registered by trusted application code,
* local content-addressed stores bind a digest to a file under a trusted root,
* the exact open file is size/digest checked before proof parsing begins,
* callers can stream the verified file without loading the proof into memory.

The store proves artifact identity/integrity, not logical correctness.  Logical
proof checking remains the responsibility of repository-owned proof checkers.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import BinaryIO, Iterator, Mapping, Protocol


DETACHED_UNSAT_PROOF_KIND = "unsat_proof_ref"
PROOF_ARTIFACT_FORMAT = "semantic_cnf_proof_jsonl/v1"
PROOF_ARTIFACT_MEDIA_TYPE = "application/x-semantic-cnf-proof+jsonl"
PROOF_ARTIFACT_REFERENCE_SCHEMA_VERSION = "semantic_proof_artifact_reference/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProofArtifactError(RuntimeError):
    """A detached proof artifact could not be resolved or verified safely."""


@dataclass(frozen=True)
class ProofArtifactReference:
    """Content-addressed reference to one detached proof artifact.

    ``store_id`` selects only from stores registered by trusted repository code.
    The untrusted solver response cannot supply a path, URI, command, or import
    location.
    """

    store_id: str
    artifact_sha256: str
    byte_size: int
    proof_format: str
    cnf_digest: str
    artifact_format: str = PROOF_ARTIFACT_FORMAT
    media_type: str = PROOF_ARTIFACT_MEDIA_TYPE
    kind: str = DETACHED_UNSAT_PROOF_KIND
    schema_version: str = PROOF_ARTIFACT_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.kind != DETACHED_UNSAT_PROOF_KIND:
            raise ValueError("detached proof reference kind mismatch")
        if not self.store_id.strip():
            raise ValueError("proof artifact store_id must be non-empty")
        digest = self.artifact_sha256.lower()
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("artifact_sha256 must be a 64-character hexadecimal SHA-256 digest")
        cnf_digest = self.cnf_digest.lower()
        if not _SHA256_RE.fullmatch(cnf_digest):
            raise ValueError("cnf_digest must be a 64-character hexadecimal SHA-256 digest")
        if self.byte_size < 1:
            raise ValueError("proof artifact byte_size must be positive")
        if not self.proof_format.strip():
            raise ValueError("proof_format must be non-empty")
        if self.artifact_format != PROOF_ARTIFACT_FORMAT:
            raise ValueError("unsupported proof artifact format")
        if self.media_type != PROOF_ARTIFACT_MEDIA_TYPE:
            raise ValueError("unsupported proof artifact media type")
        object.__setattr__(self, "artifact_sha256", digest)
        object.__setattr__(self, "cnf_digest", cnf_digest)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ProofArtifactReference":
        allowed = {
            "kind",
            "schema_version",
            "store_id",
            "artifact_sha256",
            "byte_size",
            "proof_format",
            "cnf_digest",
            "artifact_format",
            "media_type",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"detached proof reference has unknown fields: {sorted(unknown)}")
        required = {
            "kind",
            "store_id",
            "artifact_sha256",
            "byte_size",
            "proof_format",
            "cnf_digest",
            "artifact_format",
            "media_type",
        }
        missing = required - set(payload)
        if missing:
            raise ValueError(f"detached proof reference missing fields: {sorted(missing)}")
        byte_size = payload["byte_size"]
        if isinstance(byte_size, bool) or not isinstance(byte_size, int):
            raise ValueError("detached proof byte_size must be an integer")
        schema_version = payload.get("schema_version", PROOF_ARTIFACT_REFERENCE_SCHEMA_VERSION)
        if schema_version != PROOF_ARTIFACT_REFERENCE_SCHEMA_VERSION:
            raise ValueError("detached proof reference schema version mismatch")
        return cls(
            kind=str(payload["kind"]),
            schema_version=str(schema_version),
            store_id=str(payload["store_id"]),
            artifact_sha256=str(payload["artifact_sha256"]),
            byte_size=byte_size,
            proof_format=str(payload["proof_format"]),
            cnf_digest=str(payload["cnf_digest"]),
            artifact_format=str(payload["artifact_format"]),
            media_type=str(payload["media_type"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "schema_version": self.schema_version,
            "store_id": self.store_id,
            "artifact_sha256": self.artifact_sha256,
            "byte_size": self.byte_size,
            "proof_format": self.proof_format,
            "cnf_digest": self.cnf_digest,
            "artifact_format": self.artifact_format,
            "media_type": self.media_type,
        }


class ProofArtifactStore(Protocol):
    store_id: str

    def open_verified(
        self,
        reference: ProofArtifactReference,
        *,
        max_bytes: int,
    ) -> Iterator[BinaryIO]: ...


class ProofArtifactStoreRegistry:
    """Explicit registry of trusted artifact stores keyed by stable store ID."""

    def __init__(self) -> None:
        self._stores: dict[str, ProofArtifactStore] = {}

    def register(self, store: ProofArtifactStore) -> None:
        if not store.store_id.strip():
            raise ValueError("proof artifact store_id must be non-empty")
        if store.store_id in self._stores:
            raise ValueError(f"Duplicate proof artifact store: {store.store_id}")
        self._stores[store.store_id] = store

    def get(self, store_id: str) -> ProofArtifactStore | None:
        return self._stores.get(store_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._stores))


class LocalContentAddressedProofStore:
    """Read/write content-addressed proof store rooted at one trusted directory.

    The physical path is derived solely from the SHA-256 digest; no path from an
    external solver response is ever used.  ``put_bytes`` is intended for
    trusted capture/import code and tests.  ``open_verified`` validates the
    exact open file before yielding it for streaming parsing.
    """

    def __init__(self, root: str | Path, *, store_id: str = "local-proof-cas") -> None:
        if not store_id.strip():
            raise ValueError("store_id must be non-empty")
        self.store_id = store_id
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_digest(self, digest: str) -> Path:
        if not _SHA256_RE.fullmatch(digest):
            raise ProofArtifactError("invalid proof artifact digest")
        return self.root / f"{digest}.proof"

    def put_bytes(
        self,
        data: bytes,
        *,
        proof_format: str,
        cnf_digest: str,
    ) -> ProofArtifactReference:
        if not data:
            raise ValueError("detached proof artifact cannot be empty")
        digest = hashlib.sha256(data).hexdigest()
        target = self._path_for_digest(digest)
        temporary = self.root / f".{digest}.{os.getpid()}.tmp"
        if target.exists():
            if target.stat().st_size != len(data) or self._hash_file(target) != digest:
                raise ProofArtifactError("existing content-addressed proof artifact is corrupt")
        else:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        return ProofArtifactReference(
            store_id=self.store_id,
            artifact_sha256=digest,
            byte_size=len(data),
            proof_format=proof_format,
            cnf_digest=cnf_digest,
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @contextmanager
    def open_verified(
        self,
        reference: ProofArtifactReference,
        *,
        max_bytes: int,
    ) -> Iterator[BinaryIO]:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if reference.store_id != self.store_id:
            raise ProofArtifactError("proof artifact reference targets a different store")
        if reference.byte_size > max_bytes:
            raise ProofArtifactError("proof artifact exceeds configured byte limit")
        candidate = self._path_for_digest(reference.artifact_sha256)
        if candidate.is_symlink():
            raise ProofArtifactError("proof artifact cannot be a symbolic link")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ProofArtifactError("referenced proof artifact does not exist") from exc
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ProofArtifactError("proof artifact escaped registered store root") from exc
        if not resolved.is_file():
            raise ProofArtifactError("proof artifact is not a regular file")

        with resolved.open("rb") as handle:
            stat = os.fstat(handle.fileno())
            if stat.st_size != reference.byte_size:
                raise ProofArtifactError("proof artifact byte_size mismatch")
            digest = hashlib.sha256()
            total = 0
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                total += len(chunk)
                if total > max_bytes:
                    raise ProofArtifactError("proof artifact exceeds configured byte limit")
                digest.update(chunk)
            if total != reference.byte_size:
                raise ProofArtifactError("proof artifact size changed during verification")
            if digest.hexdigest() != reference.artifact_sha256:
                raise ProofArtifactError("proof artifact SHA-256 mismatch")
            handle.seek(0)
            yield handle
