"""GitHub Git-ref CAS backend for durable AE-32C publication state.

The publication branch is an append-only state log. Updates are ordinary
fast-forward ref updates: concurrent sibling commits cannot both win. Readers
must re-resolve the authorized source ref before treating a pointer as current.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from .publication import (
    PublicationError, _empty, _verify_state, canonical_bytes, digest,
    verify_run_record,
)

class GitHubAPIError(PublicationError):
    def __init__(self, status: int, message: str):
        super().__init__(f"github_api_{status}:{message}")
        self.status = status

class GitHubRESTTransport:
    """Minimal GitHub REST transport; token is supplied at runtime, never stored."""
    def __init__(self, token: str, api_url: str = "https://api.github.com"):
        if not token:
            raise PublicationError("github_token_missing")
        self.token = token
        self.api_url = api_url.rstrip("/")

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        req = urllib.request.Request(
            self.api_url + path, data=data, method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "AE-32C-publication-controller",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise GitHubAPIError(exc.code, detail[:1000]) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise PublicationError("github_api_transport_failure") from exc

class GitHubRefCASStore:
    """Durable publication state stored as one JSON blob on a dedicated Git ref.

    A candidate commit is parented to the observed publication-ref head. The
    non-force ref update is the CAS: only a fast-forward from that exact parent
    can win. A losing writer rereads state and retries from the new head.
    """
    def __init__(self, transport: GitHubRESTTransport, repository: str,
                 source_branch: str, publication_branch: str = "ae32c-publication-state",
                 state_path: str = "state/publication.json", retries: int = 8):
        if not all((repository, source_branch, publication_branch, state_path)):
            raise PublicationError("github_store_configuration_missing")
        self.http = transport
        self.repository = repository
        self.source_branch = source_branch
        self.publication_branch = publication_branch
        self.state_path = state_path
        self.retries = retries
        self.base = "/repos/" + repository

    def _ref_path(self, branch: str) -> str:
        return self.base + "/git/ref/heads/" + urllib.parse.quote(branch, safe="/")

    def _get_ref(self, branch: str) -> str:
        return self.http.request("GET", self._ref_path(branch))["object"]["sha"]

    def _ensure_publication_ref(self) -> str:
        try:
            return self._get_ref(self.publication_branch)
        except GitHubAPIError as exc:
            if exc.status != 404:
                raise
        source_sha = self._get_ref(self.source_branch)
        try:
            self.http.request("POST", self.base + "/git/refs", {
                "ref": "refs/heads/" + self.publication_branch, "sha": source_sha,
            })
        except GitHubAPIError as exc:
            # A concurrent initializer may have created the branch first.
            if exc.status not in (409, 422):
                raise
        return self._get_ref(self.publication_branch)

    def _read_state_at(self, commit_sha: str) -> dict[str, Any]:
        commit = self.http.request("GET", self.base + "/git/commits/" + commit_sha)
        tree_sha = commit["tree"]["sha"]
        tree = self.http.request("GET", self.base + "/git/trees/" + tree_sha)
        entry = next((x for x in tree.get("tree", []) if x.get("path") == self.state_path), None)
        if entry is None:
            return _empty(self.repository)
        blob = self.http.request("GET", self.base + "/git/blobs/" + entry["sha"])
        import base64
        raw = base64.b64decode(blob["content"])
        state = json.loads(raw.decode("utf-8"))
        _verify_state(state, self.repository)
        return state

    def _commit_state(self, parent_sha: str, state: Mapping[str, Any]) -> str:
        import base64
        raw = canonical_bytes(state)
        blob = self.http.request("POST", self.base + "/git/blobs", {
            "content": base64.b64encode(raw).decode("ascii"), "encoding": "base64",
        })["sha"]
        parent = self.http.request("GET", self.base + "/git/commits/" + parent_sha)
        tree = self.http.request("POST", self.base + "/git/trees", {
            "base_tree": parent["tree"]["sha"],
            "tree": [{"path": self.state_path, "mode": "100644", "type": "blob", "sha": blob}],
        })["sha"]
        return self.http.request("POST", self.base + "/git/commits", {
            "message": "AE-32C: advance durable publication state",
            "tree": tree, "parents": [parent_sha],
        })["sha"]

    def publish(self, record: Mapping[str, Any], *, event_name: str = "push") -> dict[str, Any]:
        verify_run_record(record)
        for _ in range(self.retries):
            parent_sha = self._ensure_publication_ref()
            state = self._read_state_at(parent_sha)
            source_sha = self._get_ref(self.source_branch)
            generation = record["generation"]
            previous = state.get("last_generation")
            decision, reason = "PUBLISHED", "fresh_successful_run"
            if event_name != "push":
                decision, reason = "HISTORICAL_ONLY", "event_not_authorized_for_current_publication"
            elif record["outcome"] != "SUCCEEDED":
                decision, reason = "HISTORICAL_ONLY", "run_not_successful"
            elif record["source_revision"] != source_sha:
                decision, reason = "HISTORICAL_ONLY", "source_revision_not_current_at_authorization_check"
            elif previous is not None and generation <= previous:
                decision, reason = "REJECTED", "generation_not_strictly_monotonic"
            next_state = {k: v for k, v in state.items() if k != "state_sha256"}
            next_state["history"] = [*state.get("history", []), {
                "record": dict(record), "decision": decision, "reason": reason,
                "authorized_source_revision": source_sha,
            }]
            if decision == "PUBLISHED":
                next_state["current"] = dict(record)
                next_state["last_generation"] = list(generation)
                next_state["authorized_source_revision"] = source_sha
            next_state["state_sha256"] = digest(next_state)
            commit_sha = self._commit_state(parent_sha, next_state)
            try:
                self.http.request("PATCH", self._ref_path(self.publication_branch), {
                    "sha": commit_sha, "force": False,
                })
            except GitHubAPIError as exc:
                if exc.status in (409, 422):
                    continue
                raise
            # A source-ref move after the pre-check cannot make the record current:
            # every read rechecks the live source ref (see current()).
            live_source = self._get_ref(self.source_branch)
            effective = decision == "PUBLISHED" and live_source == source_sha
            return {
                "decision": decision,
                "reason": reason if effective or decision != "PUBLISHED" else "source_ref_moved_during_publication",
                "current_effective": effective,
                "publication_commit_sha": commit_sha,
                "authorized_source_revision": source_sha,
                "live_source_revision_after_commit": live_source,
                "history_count": len(next_state["history"]),
            }
        raise PublicationError("github_publication_cas_retry_exhausted")

    def current(self) -> dict[str, Any] | None:
        """Return current only if its authorization SHA still equals the live source ref."""
        head = self._ensure_publication_ref()
        state = self._read_state_at(head)
        current = state.get("current")
        if current is None:
            return None
        verify_run_record(current)
        live_source = self._get_ref(self.source_branch)
        if state.get("authorized_source_revision") != live_source:
            return None
        if current.get("source_revision") != live_source:
            return None
        return dict(current)
