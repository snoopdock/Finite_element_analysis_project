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

## Durable backend adapter

`audit_engine/semantic_audit/ae32c/github_publication.py` adds a GitHub-native durable store. It writes one canonical state document to `state/publication.json` on the dedicated `ae32c-publication-state` ref. Each candidate state is committed as a child of the exact publication-ref head that was read. The controller advances the ref with a non-force update. Competing writers create sibling commits; only one can fast-forward the ref, and losers reread state and retry. This makes the publication-ref update the serialization/CAS point without relying on runner-local files.

The adapter resolves the source branch ref itself immediately before eligibility evaluation. It records that authorized SHA in state. It then resolves the source ref again after the publication-ref update. Crucially, `current()` independently resolves the live source branch and returns a record only when both the stored authorization SHA and the record source revision still equal that live SHA. Thus a source-branch move between pre-check and publication cannot leave a stale record readable as current. Historical records remain in the state log.

Six fake-transport tests exercise persistence across store instances, stale-source history retention, a source move during commit, failed/non-push disposition, generation collision, and retry after a simulated ref-update conflict. The workflow runs these tests without a write token.

**Credential boundary:** the existing snapshot workflow intentionally retains `contents: read`. The durable adapter is not yet invoked by that workflow. A trusted publisher must receive a narrowly scoped write credential in a separate trust boundary; do not simply change the current job to `contents: write`, because it executes repository-controlled Python and is also configured for pull-request events. The module is an implemented backend adapter, not yet a live production publication service.

## Remaining work

1. Implement durable cross-run storage with transactional compare-and-swap.
2. Resolve the live authorized ref immediately before the transaction.
3. Define policy for push, dispatch, release and future PR merge events.
4. Canonicalize effective configuration hashing.
5. Test crash recovery, stale locks, backend conflicts and multi-host concurrency.
6. Bind asynchronous model/tool responses to immutable run identity and reject stale attachment.
7. Keep historical retention separate from current-result publication.

No PR was opened or tested. No merge or production approval was performed.


## Bounded inline history and immutable archive segments

The GitHub CAS backend now caps inline history at 256 decisions by default. When the threshold is exceeded, the oldest decisions are moved to immutable segments containing at most 128 records each, continuing until inline history is within the cap. Segments are linked by previous-path and previous-digest references; each segment digest binds its repository, sequence, entries, and predecessor. The active state stores the archive tip and aggregate segment/record counts.

All newly created segment blobs and the updated state pointer are written into one candidate Git tree and one commit before the non-force ref update. The ref update remains the CAS point, so a losing or interrupted writer cannot publish a pointer without its archive segment. Every state read verifies the full archive chain, all segment digests and sequence/path bindings, each archived run-record digest, and aggregate counts. Missing, altered, truncated, or miscounted archives fail closed.

This bounds the frequently rewritten state document, not total storage: archived history is intentionally retained and grows with use. No record is silently discarded. A destructive retention/expiry policy is not implemented and would require separate authorization and an independently preserved audit anchor. Fake-transport tests cover multiple segments, bounded inline state, and tamper rejection. The publisher prepare pipeline also has end-to-end fixture tests for API/event binding, artifact digest verification, workflow allowlisting, and incomplete-coverage history-only behavior. Live GitHub API behavior remains unverified.
