"""Live Docker lifecycle test for SNAP worker request-timeout cleanup.

This test deliberately launches a disposable worker container that never
answers its first protocol request. It verifies that the adapter's deadline
causes Docker to remove the exact container ID captured by --cidfile.
"""
from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.backend.snap_worker_adapter import (
    SNAPWorkerAdapter,
    SNAPWorkerTimeoutError,
)


def test_snap_worker_timeout_force_removes_a_real_docker_container(
    monkeypatch, tmp_path: Path,
):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker CLI is not available")

    original_run = subprocess.run
    daemon = original_run(
        [docker, "info"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is not available")

    image = f"ae32c-snap-timeout:{uuid.uuid4().hex[:12]}"
    dockerfile = tmp_path / "Dockerfile"
    stalled_worker = tmp_path / "stall.sh"
    dockerfile.write_text(
        "FROM busybox:1.36.1\n"
        "COPY stall.sh /stall.sh\n"
        'ENTRYPOINT ["/bin/sh", "/stall.sh"]\n',
        encoding="utf-8",
    )
    stalled_worker.write_text(
        "#!/bin/sh\n"
        "while IFS= read -r request; do\n"
        "  sleep 300\n"
        "done\n",
        encoding="utf-8",
    )

    try:
        build = original_run(
            [docker, "build", "--pull", "--quiet", "--tag", image, str(tmp_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=180,
        )
        assert build.returncode == 0, (
            "could_not_build_stalled_worker_image: "
            + (build.stderr or build.stdout or "")[-2000:]
        )

        removal_calls: list[tuple[list[str], int]] = []

        def tracked_run(command, *args, **kwargs):
            result = original_run(command, *args, **kwargs)
            command_list = list(command)
            if command_list[:3] == [docker, "rm", "--force"]:
                removal_calls.append((command_list, result.returncode))
            return result

        monkeypatch.setattr(
            "audit_engine.semantic_audit.graph.backend.snap_worker_adapter.subprocess.run",
            tracked_run,
        )
        monkeypatch.setenv("AE32C_SNAP_WORKER_IMAGE", image)
        monkeypatch.setenv(
            "AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS", "3",
        )

        started = time.monotonic()
        with pytest.raises(
            SNAPWorkerTimeoutError,
            match=r"snap_worker_request_timeout:init",
        ):
            SNAPWorkerAdapter(SemanticGraph())
        elapsed = time.monotonic() - started

        assert elapsed < 15.0, f"worker_timeout_cleanup_exceeded_bound:{elapsed:.3f}s"
        assert len(removal_calls) == 1, removal_calls
        command, return_code = removal_calls[0]
        assert command[:3] == [docker, "rm", "--force"]
        assert return_code == 0, f"docker_force_remove_failed:{command!r}"

        container_id = command[3]
        inspected = original_run(
            [docker, "inspect", container_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        assert inspected.returncode != 0, "timed_out_worker_container_still_exists"
    finally:
        original_run(
            [docker, "rmi", "--force", image],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
