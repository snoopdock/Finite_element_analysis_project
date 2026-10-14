# AE-02 — Verified Audit Evolution (reworked)

AE-02 is a **read-only** consumer of sealed AE-01 generations. It must not promote
successful execution into compliance, and it must not describe a vanished finding
as a proven repair. This implementation replaces the unvalidated, boolean-only
AE-02 prototype. It does not replace existing `semantic_audit/evolution/`.

## Data and verification boundary

`load_generation(output_root, generation_id=None)` verifies AE-01 SHA-256
membership, seal, source manifest, source/graph fingerprints, G3 verification
receipts and occurrence witnesses via AE-01's independent `_verify_contract`.
AE-02 adds a cross-check of internal import targets against the sealed policy
graph. A missing/failed current `LATEST.json` is rejected; an **explicit** sealed
historical generation may still be inspected for controlled comparisons.
Historical evidence is verified against its sealed bytes, not current working-tree
source (which will usually differ). A self-generated SHA-256 seal is not a
third-party signature; authentic historical attribution requires an external
trusted retention/signing mechanism.

## Comparing real generations

```bash
python -m audit_engine.semantic_audit.ae02 \
  --before-output /path/to/old-ae01-output \
  --after-output /path/to/new-ae01-output
```

Explicit generation IDs may be provided with `--before-generation` and
`--after-generation` (`ae01-` plus 32 hexadecimal digits). CLI exit codes:
`0` complete comparison, `3` incomplete successor assurance, `4` verification
or execution error. An exit code of zero does **not** mean defect-free.

Report includes deterministic `comparison_sha256`, source additions/deletions and
hash changes; import occurrence changes; policy and lifecycle changes; original
G3 graph-evolution diff (`GraphSnapshot.capture` and `compare_snapshots`) over
policy-relevant graph; previous/current per-rule coverage; and source-bound
finding reconciliation. Changed policy marks new findings `new_under_changed_policy`.
A disappearing finding is `not_observed_in_complete_audit` only when the next
run is complete under equivalent policy. Incomplete successor outcomes stay
`unassessed_after_change`. Location changes are conservatively treated as an
old occurrence absent and a new one present; relocation matching or semantic
proof of a fix is not inferred.

## Limitations

- Static Python import/call semantics inherit AE-01's explicit uncertainty.
- Policy classification is explicit, versioned, and cannot be inferred from names.
- Finding identity uses file, line, column, target and context; a moved statement
  is not automatically recognized as the same semantic obligation.
- Historical generation authenticity depends on the trusted storage of the
  original AE-01 seal; checksums detect uncoordinated modification, not a
  well-positioned adversary who replaces the entire historical trust root.
- Lifecycle manager records actor/evidence claims but **does not authenticate**
  the actor or apply human dispositions automatically.
- No repository edits, automatic PRs, or scheduled GitHub validation.

## Manual validation

Install `validation/profiles/G9.2.yaml` **in the development branch**, then run
Manual Validation Dispatcher from `main` with `TARGET_BRANCH=stage1/section-uuids`,
`TARGET_PROFILE=G9.2`, `REGRESSION_MODE=profile`. The profile selects AE-02,
AE-01 and pre-existing graph/verification regression tests and enables full
regression. Before uploading, run the release preflight from the patch root:

```bash
python tools/check_validation_patch.py --package PATCH.zip --repository-root . --profile G9.2
```

Never claim remote acceptance without GitHub Actions evidence.
