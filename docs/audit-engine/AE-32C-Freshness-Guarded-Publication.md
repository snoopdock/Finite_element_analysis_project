# AE-32C Phase 4 — Freshness-Guarded Result Publication

**Status:** State machine implemented; CI tests added. **Persistent production backend:** Not connected. **PR execution:** Deferred.

## Purpose

Completion order is not publication authority. Older runs can finish after newer runs, and asynchronous results can return after their source is superseded. This phase separates immutable run history from the current result.

Implementation: `audit_engine/semantic_audit/ae32c/publication.py`.

## Immutable run record

Each content-addressed record binds repository, exact source revision, source snapshot ID, graph snapshot ID, rule-registry digest, finding-ledger digest, effective-configuration digest, workflow run ID, generation `[run_number, run_attempt]`, and terminal outcome. `record_sha256` covers the record; tampering is rejected.

## Publication state

State includes repository/schema identity, last published generation, current immutable record, append-only decision history, and `state_sha256`. Local writers serialize through an exclusive lock directory. Writes use a synced temporary file and atomic replacement. Equal or older generations cannot replace current.

## Disposition

| Condition | Decision | Current result |
|---|---|---|
| Successful push, exact authorized source revision, newer generation | `PUBLISHED` | Advances |
| Superseded/mismatched source | `HISTORICAL_ONLY` | Unchanged |
| Failed, cancelled, incomplete | `HISTORICAL_ONLY` | Unchanged |
| Pull-request or other non-push event | `HISTORICAL_ONLY` | Unchanged |
| Equal/older generation | `REJECTED` | Unchanged |

Every decision remains in history. The caller must supply a live authoritative source-ref SHA; event payloads are not authority.

## Critical integration boundary

The workflow runs the state-machine tests but does **not** call `publish_result` against a persistent cross-run store. GitHub Actions runners are ephemeral; a `RUNNER_TEMP` file cannot coordinate independent runs. There is therefore no operational current-result pointer yet, and no claim that production stale-result publication is blocked.

The hosting controller must connect this module to a shared durable transactional store (conditional write/compare-and-swap), resolve the live authorized source ref immediately before publication, and preserve history. The local lock protocol is only for publishers sharing a filesystem with reliable atomic directory creation and rename. Distributed publishers require a database or object-store transaction. Lock recovery after abrupt host loss remains a backend responsibility.

The configuration digest is bound but canonical effective-configuration serialization is not yet defined. The controller must hash the exact effective inputs.

## Validation

`tests/semantic_graph/test_ae32c_publication.py` covers fresh publication, superseded revisions, late completion, equal-generation collisions, cancelled/failed/incomplete outcomes, non-push events, record tampering, and concurrent local writers. CI validates the state machine and local filesystem behavior only, not distributed storage or a live ref-lookup race.

## Remaining work

1. Implement durable cross-run storage with transactional compare-and-swap.
2. Resolve the live authorized ref immediately before the transaction.
3. Define policy for push, dispatch, release and future PR merge events.
4. Canonicalize effective configuration hashing.
5. Test crash recovery, stale locks, backend conflicts and multi-host concurrency.
6. Bind asynchronous model/tool responses to immutable run identity and reject stale attachment.
7. Keep historical retention separate from current-result publication.

No PR was opened or tested. No merge or production approval was performed.
