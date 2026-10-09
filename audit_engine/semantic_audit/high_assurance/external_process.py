"""Fixed-command JSON subprocess boundary for controlled external verification.

This module is the *only* G3.4 high-assurance component that owns a subprocess
API.  It intentionally provides protocol/identity containment rather than
claiming an operating-system sandbox:

* the executable and arguments are registered by trusted application code,
* the executable digest is verified immediately before every run,
* ``shell=True`` is never used,
* request data travels only through JSON stdin,
* stdout must be exactly one bounded JSON object,
* the working directory and common temp/home variables are ephemeral,
* execution has a hard wall-clock timeout.

Python alone cannot guarantee network or filesystem isolation for an arbitrary
external binary.  Callers must explicitly acknowledge those missing OS-level
controls before a process can run.  A future sandbox broker may replace this
runner without changing the semantic high-assurance adapter contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from types import MappingProxyType
from typing import Any, Mapping, Sequence


EXTERNAL_JSON_PROCESS_PROTOCOL = "semantic_external_json_process/v1"
_SHA256_HEX_LENGTH = 64


class ExternalProcessError(RuntimeError):
    """A controlled-external process failed before semantic interpretation."""


@dataclass(frozen=True)
class ExternalProcessSpec:
    """Trusted identity of one fixed external executable invocation."""

    process_id: str
    process_version: str
    executable_path: str
    executable_sha256: str
    arguments: tuple[str, ...] = ()
    protocol_version: str = EXTERNAL_JSON_PROCESS_PROTOCOL

    def __post_init__(self) -> None:
        if not self.process_id.strip() or not self.process_version.strip():
            raise ValueError("process_id and process_version must be non-empty.")
        path = Path(self.executable_path)
        if not path.is_absolute():
            raise ValueError("External process executable_path must be absolute.")
        digest = self.executable_sha256.lower()
        if len(digest) != _SHA256_HEX_LENGTH or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("executable_sha256 must be a 64-character hexadecimal SHA-256 digest.")
        if not self.protocol_version.strip():
            raise ValueError("protocol_version must be non-empty.")
        for argument in self.arguments:
            if "\x00" in argument:
                raise ValueError("External process arguments cannot contain NUL bytes.")
        object.__setattr__(self, "executable_sha256", digest)
        object.__setattr__(self, "arguments", tuple(self.arguments))


@dataclass(frozen=True)
class ExternalProcessRiskAcknowledgement:
    """Explicit acceptance of controls this runner cannot enforce itself.

    The fields are intentionally negatively phrased.  Setting them to ``True``
    does not claim isolation; it records that the caller knowingly accepts that
    the corresponding OS-level isolation is absent.
    """

    accept_no_network_isolation: bool = False
    accept_no_filesystem_isolation: bool = False


@dataclass(frozen=True)
class ExternalProcessTranscript:
    process_id: str
    process_version: str
    executable_sha256: str
    input_sha256: str
    stdout_sha256: str
    stderr_sha256: str
    return_code: int
    timeout_ms: int
    stdout_bytes: int
    stderr_bytes: int
    shell_used: bool = False
    ephemeral_working_directory: bool = True
    network_isolation_enforced: bool = False
    filesystem_isolation_enforced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "process_version": self.process_version,
            "executable_sha256": self.executable_sha256,
            "input_sha256": self.input_sha256,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "return_code": self.return_code,
            "timeout_ms": self.timeout_ms,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "shell_used": self.shell_used,
            "ephemeral_working_directory": self.ephemeral_working_directory,
            "network_isolation_enforced": self.network_isolation_enforced,
            "filesystem_isolation_enforced": self.filesystem_isolation_enforced,
        }


@dataclass(frozen=True)
class ExternalJsonProcessResult:
    payload: Mapping[str, Any]
    transcript: ExternalProcessTranscript

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class ControlledJsonSubprocessRunner:
    """Run one pre-registered executable using a strict JSON stdin/stdout protocol.

    This is *controlled external execution*, not a sandbox.  The process can run
    only after explicit acknowledgement that network and filesystem isolation
    are not enforced by this implementation.
    """

    def __init__(
        self,
        spec: ExternalProcessSpec,
        *,
        risk_acknowledgement: ExternalProcessRiskAcknowledgement | None = None,
        max_input_bytes: int = 64 * 1024,
        max_stdout_bytes: int = 256 * 1024,
        max_stderr_bytes: int = 64 * 1024,
    ) -> None:
        if min(max_input_bytes, max_stdout_bytes, max_stderr_bytes) < 1:
            raise ValueError("External process byte limits must be positive.")
        self.spec = spec
        self.risk_acknowledgement = risk_acknowledgement or ExternalProcessRiskAcknowledgement()
        self.max_input_bytes = max_input_bytes
        self.max_stdout_bytes = max_stdout_bytes
        self.max_stderr_bytes = max_stderr_bytes

    @staticmethod
    def sha256_file(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _verified_executable(self) -> Path:
        path = Path(self.spec.executable_path).resolve(strict=True)
        if not path.is_file():
            raise ExternalProcessError("registered executable is not a regular file")
        actual = self.sha256_file(path)
        if actual != self.spec.executable_sha256:
            raise ExternalProcessError("registered executable digest mismatch")
        return path

    def _check_risk_acknowledgement(self) -> None:
        if not self.risk_acknowledgement.accept_no_network_isolation:
            raise ExternalProcessError(
                "external process denied: network isolation is not enforced and was not acknowledged"
            )
        if not self.risk_acknowledgement.accept_no_filesystem_isolation:
            raise ExternalProcessError(
                "external process denied: filesystem isolation is not enforced and was not acknowledged"
            )

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return

    @staticmethod
    def _read_limited_stream(
        stream,
        *,
        limit: int,
        chunks: list[bytes],
        overflow: threading.Event,
    ) -> None:
        total = 0
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            total += len(chunk)
            if total > limit:
                overflow.set()
                return
            chunks.append(chunk)

    def run(self, payload: Mapping[str, Any], *, timeout_ms: int) -> ExternalJsonProcessResult:
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be positive.")
        self._check_risk_acknowledgement()
        executable = self._verified_executable()
        request_payload = {
            "transport_protocol": self.spec.protocol_version,
            "payload": dict(payload),
        }
        encoded = json.dumps(
            request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self.max_input_bytes:
            raise ExternalProcessError("external process input exceeds configured byte limit")

        input_digest = hashlib.sha256(encoded).hexdigest()
        with tempfile.TemporaryDirectory(prefix="semantic-external-") as workdir:
            environment = {
                "HOME": workdir,
                "TMPDIR": workdir,
                "TEMP": workdir,
                "PYTHONHASHSEED": "0",
                "PYTHONIOENCODING": "utf-8",
                "LC_ALL": "C.UTF-8",
            }
            command = [str(executable), *self.spec.arguments]
            with tempfile.TemporaryFile() as stdin_file:
                stdin_file.write(encoded)
                stdin_file.seek(0)
                process = subprocess.Popen(
                    command,
                    stdin=stdin_file,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=workdir,
                    env=environment,
                    shell=False,
                    start_new_session=True,
                )
                assert process.stdout is not None and process.stderr is not None
                stdout_chunks: list[bytes] = []
                stderr_chunks: list[bytes] = []
                stdout_overflow = threading.Event()
                stderr_overflow = threading.Event()
                stdout_thread = threading.Thread(
                    target=self._read_limited_stream,
                    args=(process.stdout,),
                    kwargs={
                        "limit": self.max_stdout_bytes,
                        "chunks": stdout_chunks,
                        "overflow": stdout_overflow,
                    },
                    daemon=True,
                )
                stderr_thread = threading.Thread(
                    target=self._read_limited_stream,
                    args=(process.stderr,),
                    kwargs={
                        "limit": self.max_stderr_bytes,
                        "chunks": stderr_chunks,
                        "overflow": stderr_overflow,
                    },
                    daemon=True,
                )
                stdout_thread.start()
                stderr_thread.start()
                deadline = time.monotonic() + timeout_ms / 1000.0
                timed_out = False
                overflow_reason: str | None = None
                while process.poll() is None:
                    if stdout_overflow.is_set():
                        overflow_reason = "external process stdout exceeds configured byte limit"
                        self._kill_process_tree(process)
                        break
                    if stderr_overflow.is_set():
                        overflow_reason = "external process stderr exceeds configured byte limit"
                        self._kill_process_tree(process)
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        self._kill_process_tree(process)
                        break
                    time.sleep(0.002)
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._kill_process_tree(process)
                    process.wait(timeout=1.0)
                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)
                stdout = b"".join(stdout_chunks)
                stderr = b"".join(stderr_chunks)
                if timed_out:
                    raise ExternalProcessError("external process timeout")
                if overflow_reason:
                    raise ExternalProcessError(overflow_reason)
                if stdout_overflow.is_set():
                    raise ExternalProcessError("external process stdout exceeds configured byte limit")
                if stderr_overflow.is_set():
                    raise ExternalProcessError("external process stderr exceeds configured byte limit")
                return_code = int(process.returncode)

        if return_code != 0:
            raise ExternalProcessError(f"external process returned non-zero status {return_code}")
        try:
            text = stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExternalProcessError("external process stdout is not UTF-8") from exc
        try:
            response = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExternalProcessError("external process stdout is not exactly one JSON document") from exc
        if not isinstance(response, dict):
            raise ExternalProcessError("external process JSON response must be an object")
        if response.get("transport_protocol") != self.spec.protocol_version:
            raise ExternalProcessError("external process transport protocol mismatch")
        result_payload = response.get("payload")
        if not isinstance(result_payload, dict):
            raise ExternalProcessError("external process response payload must be an object")

        transcript = ExternalProcessTranscript(
            process_id=self.spec.process_id,
            process_version=self.spec.process_version,
            executable_sha256=self.spec.executable_sha256,
            input_sha256=input_digest,
            stdout_sha256=hashlib.sha256(stdout).hexdigest(),
            stderr_sha256=hashlib.sha256(stderr).hexdigest(),
            return_code=return_code,
            timeout_ms=timeout_ms,
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
        )
        return ExternalJsonProcessResult(payload=result_payload, transcript=transcript)
