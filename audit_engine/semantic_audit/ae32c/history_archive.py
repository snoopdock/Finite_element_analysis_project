"""Digest-chained immutable archive segments for AE-32C publication history.

Compaction bounds the frequently rewritten state document without deleting audit
records. Archived records remain independently verifiable and are committed in
the same Git tree update as the state pointer that references them.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from .publication import PublicationError, digest, verify_run_record

ARCHIVE_SCHEMA = "ae32c/publication-history-segment/v1"
_PATH_RE = re.compile(r"^state/history/segment-[0-9]{8}-[0-9a-f]{16}\.json$")


def _verify_entry(entry: Any) -> None:
    if not isinstance(entry, Mapping):
        raise PublicationError("publication_history_entry_invalid")
    record = entry.get("record")
    if not isinstance(record, Mapping):
        raise PublicationError("publication_history_record_missing")
    verify_run_record(record)
    if entry.get("decision") not in {"PUBLISHED", "HISTORICAL_ONLY", "REJECTED"}:
        raise PublicationError("publication_history_decision_invalid")
    if not isinstance(entry.get("reason"), str) or not entry["reason"]:
        raise PublicationError("publication_history_reason_invalid")
    if not isinstance(entry.get("authorized_source_revision"), str) or not entry["authorized_source_revision"]:
        raise PublicationError("publication_history_authorized_revision_invalid")


def compact_history(
    state: Mapping[str, Any], *, max_inline_records: int = 256,
    archive_batch_size: int = 128,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Archive oldest decisions in bounded batches until inline history is within limit."""
    if max_inline_records < 1 or archive_batch_size < 1:
        raise PublicationError("publication_history_compaction_limits_invalid")
    payload = {k: v for k, v in state.items() if k != "state_sha256"}
    history = payload.get("history")
    if not isinstance(history, list):
        raise PublicationError("publication_history_invalid")
    for entry in history:
        _verify_entry(entry)
    if len(history) <= max_inline_records:
        payload["state_sha256"] = digest(payload)
        return payload, []

    previous = payload.get("history_archive")
    if previous is not None:
        if not isinstance(previous, Mapping):
            raise PublicationError("publication_history_archive_pointer_invalid")
        sequence = previous.get("segment_count")
        record_count = previous.get("record_count")
        if not isinstance(sequence, int) or sequence < 1 or not isinstance(record_count, int) or record_count < 1:
            raise PublicationError("publication_history_archive_pointer_invalid")
        previous_link = {"path": previous.get("path"), "sha256": previous.get("sha256")}
    else:
        sequence, record_count, previous_link = 0, 0, None

    remaining = list(history)
    archives: list[dict[str, Any]] = []
    while len(remaining) > max_inline_records:
        count = min(archive_batch_size, len(remaining) - max_inline_records + archive_batch_size - 1)
        archived, remaining = remaining[:count], remaining[count:]
        segment_payload = {
            "schema": ARCHIVE_SCHEMA,
            "repository": payload["repository"],
            "sequence": sequence + 1,
            "previous": previous_link,
            "entries": archived,
        }
        segment_sha256 = digest(segment_payload)
        segment = {**segment_payload, "segment_sha256": segment_sha256}
        segment_path = f"state/history/segment-{sequence + 1:08d}-{segment_sha256[:16]}.json"
        archives.append({"path": segment_path, "segment": segment})
        sequence += 1
        record_count += count
        previous_link = {"path": segment_path, "sha256": segment_sha256}

    payload["history"] = remaining
    payload["history_archive"] = {
        "path": previous_link["path"],
        "sha256": previous_link["sha256"],
        "segment_count": sequence,
        "record_count": record_count,
    }
    payload["state_sha256"] = digest(payload)
    return payload, archives

def verify_archive_segment(
    segment: Mapping[str, Any], *, repository: str, expected_sha256: str,
    expected_sequence: int,
) -> None:
    payload = {k: v for k, v in segment.items() if k != "segment_sha256"}
    if segment.get("schema") != ARCHIVE_SCHEMA or segment.get("repository") != repository:
        raise PublicationError("publication_history_archive_identity_invalid")
    if segment.get("sequence") != expected_sequence:
        raise PublicationError("publication_history_archive_sequence_invalid")
    if segment.get("segment_sha256") != expected_sha256 or digest(payload) != expected_sha256:
        raise PublicationError("publication_history_archive_digest_invalid")
    entries = segment.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PublicationError("publication_history_archive_entries_invalid")
    for entry in entries:
        _verify_entry(entry)
    previous = segment.get("previous")
    if previous is not None:
        if not isinstance(previous, Mapping) or not isinstance(previous.get("path"), str) or not isinstance(previous.get("sha256"), str):
            raise PublicationError("publication_history_archive_link_invalid")


def verify_archive_chain(
    state: Mapping[str, Any], tree_entries: list[Mapping[str, Any]],
    read_blob: Callable[[str], bytes],
) -> None:
    """Verify every archive segment from the state tip back to the root."""
    pointer = state.get("history_archive")
    if pointer is None:
        return
    if not isinstance(pointer, Mapping):
        raise PublicationError("publication_history_archive_pointer_invalid")
    expected_segments = pointer.get("segment_count")
    expected_records = pointer.get("record_count")
    if not isinstance(expected_segments, int) or expected_segments < 1 or not isinstance(expected_records, int) or expected_records < 1:
        raise PublicationError("publication_history_archive_pointer_invalid")
    by_path = {entry.get("path"): entry for entry in tree_entries if isinstance(entry, Mapping)}
    path, expected_sha = pointer.get("path"), pointer.get("sha256")
    sequence, total_records, seen = expected_segments, 0, set()
    while path is not None:
        if (not isinstance(path, str) or not _PATH_RE.fullmatch(path) or path in seen
                or not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
                or path != f"state/history/segment-{sequence:08d}-{expected_sha[:16]}.json"):
            raise PublicationError("publication_history_archive_path_invalid")
        seen.add(path)
        tree_entry = by_path.get(path)
        if tree_entry is None or not isinstance(tree_entry.get("sha"), str):
            raise PublicationError("publication_history_archive_segment_missing")
        import json
        try:
            segment = json.loads(read_blob(tree_entry["sha"]).decode("utf-8"))
        except Exception as exc:
            raise PublicationError("publication_history_archive_segment_unreadable") from exc
        if not isinstance(segment, Mapping):
            raise PublicationError("publication_history_archive_segment_invalid")
        verify_archive_segment(
            segment, repository=str(state["repository"]),
            expected_sha256=str(expected_sha), expected_sequence=sequence,
        )
        total_records += len(segment["entries"])
        previous = segment.get("previous")
        if sequence == 1:
            if previous is not None:
                raise PublicationError("publication_history_archive_root_invalid")
            path = expected_sha = None
        else:
            if previous is None:
                raise PublicationError("publication_history_archive_chain_truncated")
            path, expected_sha = previous.get("path"), previous.get("sha256")
        sequence -= 1
    if sequence != 0 or len(seen) != expected_segments or total_records != expected_records:
        raise PublicationError("publication_history_archive_count_mismatch")
