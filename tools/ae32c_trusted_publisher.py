"""Trusted AE-32C publisher entry point.

The prepare phase uses only the read-only Actions token to obtain upstream
metadata and the exact workflow artifact. The publish phase is a separate
invocation and requires a short-lived, narrowly installed GitHub App token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any, Mapping

from audit_engine.semantic_audit.ae32c.github_publication import (
    GitHubRefCASStore,
    GitHubRESTTransport,
)
from audit_engine.semantic_audit.ae32c.publication import canonical_bytes
from audit_engine.semantic_audit.ae32c.trusted_artifact import (
    TrustedArtifactError,
    validate_artifact_bytes,
)

PRODUCER_WORKFLOW_ID = 430355742
PRODUCER_WORKFLOW_PATH = ".github/workflows/ae32c_source_snapshot_manifest.yml"
ARTIFACT_PREFIX = "ae32c-source-graph-snapshot-"
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024


class PublisherError(RuntimeError):
    """The trusted publisher cannot safely prepare or publish this run."""


def _api_json(api_url: str, token: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        api_url.rstrip("/") + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AE-32C-trusted-publisher",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        raise PublisherError("github_read_api_request_failed:" + path) from exc
    if not isinstance(value, dict):
        raise PublisherError("github_api_response_not_object:" + path)
    return value


def _download_artifact(api_url: str, token: str, repository: str, artifact_id: int) -> bytes:
    url = api_url.rstrip("/") + f"/repos/{repository}/actions/artifacts/{artifact_id}/zip"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AE-32C-trusted-publisher",
        },
    )
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        try:
            response = opener.open(request, timeout=60)
        except urllib.error.HTTPError as redirect:
            if redirect.code not in (301, 302, 303, 307, 308):
                raise
            location = redirect.headers.get("Location")
            if not location:
                raise PublisherError("artifact_redirect_location_missing")
            target = urlsplit(location)
            source = urlsplit(api_url)
            if (target.scheme != "https" or not target.hostname
                    or target.username or target.password):
                raise PublisherError("artifact_redirect_target_invalid")
            same_origin = (target.scheme, target.hostname, target.port) == (
                source.scheme, source.hostname, source.port
            )
            # GitHub's artifact redirect commonly points to object storage.
            # Never forward the GitHub API bearer token to a different origin.
            redirected_request = urllib.request.Request(
                location,
                headers=({"Authorization": "Bearer " + token} if same_origin else {}),
            )
            response = opener.open(redirected_request, timeout=60)
        with response:
            raw = response.read(MAX_DOWNLOAD_BYTES + 1)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise PublisherError("upstream_artifact_download_failed") from exc
    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise PublisherError("upstream_artifact_download_too_large")
    return raw

def build_expected_metadata(
    run: Mapping[str, Any], repository_metadata: Mapping[str, Any], repository: str
) -> dict[str, Any]:
    """Build validator metadata exclusively from GitHub API responses."""
    run_repository = run.get("repository")
    run_repository_name = run_repository.get("full_name") if isinstance(run_repository, dict) else None
    head_repository = run.get("head_repository")
    if not isinstance(head_repository, dict):
        head_repository_name = None
    else:
        head_repository_name = head_repository.get("full_name")
    default_branch = repository_metadata.get("default_branch")
    required_values = {
        "run_id": run.get("id"),
        "run_attempt": run.get("run_attempt"),
        "run_number": run.get("run_number"),
        "workflow_id": run.get("workflow_id"),
        "workflow_path": run.get("path"),
        "head_sha": run.get("head_sha"),
        "head_branch": run.get("head_branch"),
        "event": run.get("event"),
        "ref": run.get("head_branch"),
        "conclusion": run.get("conclusion"),
        "repository": repository,
        "head_repository": head_repository_name,
        "run_repository": run_repository_name,
        "default_branch": default_branch,
    }
    if any(value in (None, "") for value in required_values.values()):
        raise PublisherError("upstream_run_metadata_incomplete")
    if run_repository_name != repository:
        raise PublisherError("upstream_run_repository_mismatch")
    return {
        "repository": repository,
        "default_branch": str(default_branch),
        "head_branch": str(run["head_branch"]),
        "head_repository": str(head_repository_name),
        "ref": "refs/heads/" + str(run["head_branch"]),
        "event": str(run["event"]),
        "head_sha": str(run["head_sha"]),
        "run_id": int(run["id"]),
        "run_attempt": int(run["run_attempt"]),
        "run_number": int(run["run_number"]),
        "workflow_id": int(run["workflow_id"]),
        "workflow_path": str(run["path"]),
        "conclusion": str(run["conclusion"]),
    }


def select_expected_artifact(
    artifacts: list[Mapping[str, Any]], *, run_id: int, run_attempt: int,
    head_sha: str | None = None,
) -> Mapping[str, Any]:
    expected_name = f"{ARTIFACT_PREFIX}{run_id}-{run_attempt}"
    matches = [item for item in artifacts if item.get("name") == expected_name]
    if len(matches) != 1:
        raise PublisherError("expected_upstream_artifact_missing_or_duplicated")
    artifact = matches[0]
    if artifact.get("expired") is not False:
        raise PublisherError("expected_upstream_artifact_expired")
    if type(artifact.get("id")) is not int or artifact["id"] < 1:
        raise PublisherError("expected_upstream_artifact_id_invalid")
    upstream = artifact.get("workflow_run")
    if not isinstance(upstream, dict) or upstream.get("id") != run_id:
        raise PublisherError("artifact_workflow_run_id_mismatch")
    if head_sha is not None and upstream.get("head_sha") != head_sha:
        raise PublisherError("artifact_workflow_head_sha_mismatch")
    if not isinstance(artifact.get("digest"), str) or not artifact["digest"].startswith("sha256:"):
        raise PublisherError("expected_upstream_artifact_digest_missing")
    return artifact


def prepare(
    *,
    api_url: str,
    read_token: str,
    repository: str,
    event_path: str,
    output_path: str,
    trusted_root: str,
) -> dict[str, Any]:
    try:
        event_payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        upstream_event = event_payload["workflow_run"]
        run_id = int(upstream_event["id"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PublisherError("workflow_run_event_payload_invalid") from exc

    run = _api_json(api_url, read_token, f"/repos/{repository}/actions/runs/{run_id}")
    repo_meta = _api_json(api_url, read_token, f"/repos/{repository}")
    expected = build_expected_metadata(run, repo_meta, repository)
    if expected["run_id"] != run_id:
        raise PublisherError("workflow_run_id_disagrees_with_event")
    if expected["workflow_id"] != PRODUCER_WORKFLOW_ID or expected["workflow_path"] != PRODUCER_WORKFLOW_PATH:
        raise PublisherError("producer_workflow_not_allowlisted")

    artifacts_response = _api_json(
        api_url, read_token, f"/repos/{repository}/actions/runs/{run_id}/artifacts"
    )
    artifacts = artifacts_response.get("artifacts")
    if not isinstance(artifacts, list):
        raise PublisherError("upstream_artifact_list_invalid")
    artifact = select_expected_artifact(
        artifacts, run_id=run_id, run_attempt=expected["run_attempt"],
        head_sha=expected["head_sha"],
    )
    archive = _download_artifact(api_url, read_token, repository, artifact["id"])
    actual_digest = hashlib.sha256(archive).hexdigest()
    if actual_digest != artifact["digest"].removeprefix("sha256:"):
        raise PublisherError("upstream_artifact_digest_mismatch")

    schema_root = Path(trusted_root) / "docs" / "audit-engine" / "schemas"
    source_schema = json.loads(
        (schema_root / "ae32c-source-snapshot-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    graph_schema = json.loads(
        (schema_root / "ae32c-graph-snapshot-manifest-v1.schema.json").read_text(encoding="utf-8")
    )
    result = validate_artifact_bytes(
        archive,
        expected=expected,
        source_schema=source_schema,
        graph_schema=graph_schema,
    )
    prepared = {
        "repository": repository,
        "default_branch": expected["default_branch"],
        "upstream_run_id": run_id,
        "upstream_run_attempt": expected["run_attempt"],
        "artifact_id": artifact["id"],
        "artifact_sha256": actual_digest,
        "current_eligible": result["current_eligible"],
        "eligibility_reason": result["eligibility_reason"],
        "record": result["record"],
    }
    Path(output_path).write_bytes(canonical_bytes(prepared))
    return prepared


def publish_prepared(*, prepared_path: str, publication_token: str) -> dict[str, Any]:
    if not publication_token:
        raise PublisherError("publication_app_token_missing")
    try:
        prepared = json.loads(Path(prepared_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PublisherError("prepared_record_invalid") from exc
    if not isinstance(prepared, dict) or not isinstance(prepared.get("record"), dict):
        raise PublisherError("prepared_record_invalid")
    repository = prepared.get("repository")
    default_branch = prepared.get("default_branch")
    if not isinstance(repository, str) or not isinstance(default_branch, str):
        raise PublisherError("prepared_record_identity_missing")
    store = GitHubRefCASStore(
        GitHubRESTTransport(publication_token),
        repository=repository,
        source_branch=default_branch,
    )
    return store.publish(prepared["record"], event_name="push")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "publish"))
    parser.add_argument("--prepared-path", default=os.path.join(os.environ.get("RUNNER_TEMP", "."), "ae32c-prepared.json"))
    args = parser.parse_args()
    try:
        if args.phase == "prepare":
            token = os.environ.get("GITHUB_TOKEN", "")
            repository = os.environ.get("GITHUB_REPOSITORY", "")
            event_path = os.environ.get("GITHUB_EVENT_PATH", "")
            if not all((token, repository, event_path)):
                raise PublisherError("read_only_github_context_missing")
            result = prepare(
                api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
                read_token=token,
                repository=repository,
                event_path=event_path,
                output_path=args.prepared_path,
                trusted_root=os.getcwd(),
            )
            print(json.dumps({
                "upstream_run_id": result["upstream_run_id"],
                "artifact_id": result["artifact_id"],
                "artifact_sha256": result["artifact_sha256"],
                "current_eligible": result["current_eligible"],
                "eligibility_reason": result["eligibility_reason"],
                "record_sha256": result["record"]["record_sha256"],
            }, sort_keys=True))
            return 0
        token = os.environ.get("AE32C_PUBLICATION_TOKEN", "")
        result = publish_prepared(prepared_path=args.prepared_path, publication_token=token)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PublisherError, TrustedArtifactError, ValueError) as exc:
        print("AE32C trusted publisher rejected run: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
