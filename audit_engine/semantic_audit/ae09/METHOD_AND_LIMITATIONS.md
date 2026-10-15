# AE-09 — Evidence-Bound Runtime Failure Investigation (G9.10)

## Method

AE-09 accepts an existing **independently verified AE-01** audit generation, the corresponding *unchanged* Python source tree, and an **untrusted UTF-8 runtime log** (traceback, pytest failure excerpt, or GitHub Actions `::error file=...,line=...` annotation). It does not execute supplied log text or mutate the source repository.

1. Verify AE-01 generation seal, source manifest, source facts, import-policy graph, applicable-rule receipts and graph fingerprints via AE-02/AE-01 routines.
2. Hash the exact runtime log bytes and extract bounded **line-numbered observations**; do not publish full log lines or exception messages. Extract exception *classes*, not exception text.
3. Resolve each source path against manifest membership; record exact, multi-component suffix, weak basename, ambiguous, unsafe or unresolved status. Match source-byte hash and source-line hash against the snapshot. Weak basename matches are review-only and cause `inconclusive`.
4. Build a bounded **reverse** static `IMPORTS` dependency review closure over the G3 policy graph, retaining import-occurrence witness IDs. Independently invoke G3 `GraphAnalysisEngine` for source-module dependency observations.
5. Produce a deterministic report; mark complete *correlation scope*, not software correctness, only when frames resolve, AE-01 scope is complete, and no graph or observation budgets are exhausted.
6. Atomically publish canonical report and seal with a fail-closed LATEST pointer. An independent replay requires the original log bytes, the source snapshot and AE-01 generation (with verified integrity).

## Assurance boundaries

- **No causal claims:** a traceback frame and a static import path do not prove the actual runtime call path, root cause or correctness of suggested fixes.
- **No full Python runtime semantics:** only witnessed source paths and static import relationships are considered. No arbitrary dynamic import, reflection, thread, subprocess or cross-language closure is claimed.
- **Untrusted logs:** matching source paths may be fabricated. Log hashes attest to byte integrity, not to truth, authenticity or how an execution occurred.
- **Data minimization:** raw logs and exception messages are **not published**; external logs must be preserved separately for independent replay. SHA-256 hashes do not authenticate the origin of a file.
- **Resource limits:** maximum log 2 MB, 50,000 lines, 512 frame occurrences, configurable depth (0–20), candidate cap (1–10,000). Exceeded budgets or incomplete provenance produce inconclusive rather than clean conclusions.
- **Historical source requirement:** use an exact copy of the source tree audited by AE-01; changed source cannot be substituted, even if an import graph is unchanged. No repository files are auto-modified.
- **Native G3 evidence:** source import graph, independent G3 graph query identity and occurrence-witness chains; no alternative semantic graph framework.
- **Publication is not a security sandbox:** run only on trusted source and in an appropriately isolated environment; do not treat logs as trusted instructions.

## CLI

```bash
python -m audit_engine.semantic_audit.ae09 \
  --ae01-output /path/to/sealed-ae01-output \
  --source-root /path/to/exact-audited-source \
  --log-file /path/to/runtime.log \
  --output /path/to/separate/ae09-artifacts

python -m audit_engine.semantic_audit.ae09 \
  --ae01-output /path/to/sealed-ae01-output \
  --source-root /path/to/exact-audited-source \
  --log-file /path/to/runtime.log \
  --output /path/to/separate/ae09-artifacts --verify
```

Exit 0: bounded correlation with no outstanding scope issues. Exit 3: inconclusive analysis. Exit 4: input, publication or verification failure. **Exit 0 does not mean that a program is correct or the failure root cause is proven.**
