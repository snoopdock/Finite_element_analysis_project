# AE-07 Verified Assurance Portfolio

See `AE07_METHOD_AND_LIMITATIONS.md` for contract and evidence boundaries.

```sh
python -m audit_engine.semantic_audit.ae07 publish --manifest input.json --output /audits/portfolio
python -m audit_engine.semantic_audit.ae07 verify --manifest input.json --output /audits/portfolio
```

Example trusted `input.json`:

```json
{"entries":[{"assessment_output":"/audits/ae06_assessment","inputs":{
  "origin_before":"/audits/pre_violation", "flagged_output":"/audits/flagged",
  "current_output":"/audits/followup", "origin_campaign":"/campaigns/initial",
  "origin_review":"/reviews/initial", "followup_campaign":"/campaigns/followup"
}}]}
```

The included `results.sarif` is generated strictly from verified current findings. A CLI exit status `3` indicates review/incomplete/blocking evidence (the expected outcome for many legitimate portfolio datasets); `4` signals verification or invocation failure. Exit `0` indicates only bounded evidence readiness for **human** review, never release approval.
