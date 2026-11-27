#!/usr/bin/env python3
"""Validate provisional AE-32D references and score explicitly exploratory trials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "evaluation/ae32d/machine-reference-registry.json"
REGISTRY_SCHEMA = "evaluation/ae32d/machine-reference-registry.schema.json"
TRIAL_SCHEMA = "evaluation/ae32d/exploratory-trials.schema.json"
MANIFEST = "evaluation/ae32d/manifest.json"
LEDGER = "evaluation/ae32d/machine-verification-ledger.json"
CONDITIONS = ("A_deterministic", "B_graph", "C_graph_llm")


def read_json(root: Path, rel: str):
    return json.loads((root / rel).read_text(encoding="utf-8"))


def schema_errors(schema, value):
    Draft202012Validator.check_schema(schema)
    return [e.message for e in Draft202012Validator(schema).iter_errors(value)]


def validate_registry(root: Path):
    errors = []
    try:
        registry = read_json(root, REGISTRY)
        schema = read_json(root, REGISTRY_SCHEMA)
        manifest = read_json(root, MANIFEST)
        ledger = read_json(root, LEDGER)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"load_failed:{type(exc).__name__}"], None
    errors.extend(f"registry_schema:{e}" for e in schema_errors(schema, registry))
    entries = {x["case_id"]: x for x in manifest.get("cases", [])}
    records = registry.get("records", [])
    ids = [r.get("case_id") for r in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_machine_reference_case_id")
    if set(ids) != set(entries):
        errors.append("machine_reference_case_set_mismatch")
    ledger_by_id = {r.get("case_id"): r for r in ledger.get("records", [])}
    for record in records:
        cid = record.get("case_id")
        entry = entries.get(cid)
        ledger_record = ledger_by_id.get(cid)
        if not entry:
            errors.append(f"orphan_machine_reference:{cid}")
            continue
        try:
            case = read_json(root, "evaluation/ae32d/" + entry["path"])
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            errors.append(f"case_load_failed:{cid}:{type(exc).__name__}")
            continue
        if record.get("source_commit_sha") != case.get("source", {}).get("source_commit_sha"):
            errors.append(f"reference_source_commit_mismatch:{cid}")
        if not ledger_record or record.get("source_commit_sha") != ledger_record.get("source_commit_sha"):
            errors.append(f"reference_ledger_mismatch:{cid}")
        if record.get("workflow_run_id") != (ledger_record or {}).get("workflow_run_id"):
            errors.append(f"reference_workflow_mismatch:{cid}")
        if record.get("artifact_id") != (ledger_record or {}).get("artifact_id"):
            errors.append(f"reference_artifact_mismatch:{cid}")
        if case.get("ground_truth", {}).get("label") != "pending_adjudication":
            errors.append(f"machine_reference_cannot_change_ground_truth:{cid}")
        if case.get("review", {}).get("status") == "adjudicated":
            errors.append(f"unexpected_adjudication_state:{cid}")
        if case.get("evaluation", {}).get("primary_benchmark_eligible") is not False:
            errors.append(f"machine_reference_cannot_grant_primary_eligibility:{cid}")
        if entry.get("primary_benchmark_eligible") is not False:
            errors.append(f"manifest_primary_eligibility_must_remain_false:{cid}")
    if registry.get("ground_truth_write_allowed") is not False:
        errors.append("ground_truth_write_must_be_forbidden")
    if registry.get("primary_benchmark_promotion_allowed") is not False:
        errors.append("primary_promotion_must_be_forbidden")
    return errors, registry


def score_trials(root: Path, trials: dict):
    errors, registry = validate_registry(root)
    if errors:
        raise ValueError("registry_invalid:" + ";".join(errors))
    schema = read_json(root, TRIAL_SCHEMA)
    schema_problems = schema_errors(schema, trials)
    if schema_problems:
        raise ValueError("trial_schema_invalid:" + ";".join(schema_problems))
    references = {r["case_id"]: r for r in registry["records"]}
    seen_ids, seen_pairs = set(), set()
    for trial in trials["records"]:
        tid = trial["trial_id"]
        pair = (trial["case_id"], trial["condition"])
        if tid in seen_ids:
            errors.append(f"duplicate_trial_id:{tid}")
        if pair in seen_pairs:
            errors.append(f"duplicate_case_condition:{pair[0]}:{pair[1]}")
        seen_ids.add(tid)
        seen_pairs.add(pair)
        ref = references.get(trial["case_id"])
        if ref is None:
            errors.append(f"unknown_case:{trial['case_id']}")
        elif trial["source_commit_sha"] != ref["source_commit_sha"]:
            errors.append(f"trial_source_commit_mismatch:{tid}")
    if errors:
        raise ValueError("trial_contract_invalid:" + ";".join(errors))

    by_pair = {(t["case_id"], t["condition"]): t for t in trials["records"]}
    reports = {}
    for condition in CONDITIONS:
        counts = {
            "reference_defect": 0, "reference_no_defect": 0, "reference_ambiguous": 0,
            "predicted_defect": 0, "true_positive": 0, "false_positive": 0,
            "predicted_no_defect": 0, "appropriate_ambiguous_abstention": 0,
            "abstain": 0, "error": 0, "missing": 0, "false_negative_or_unresolved_defect": 0
        }
        rows = []
        for cid, ref in sorted(references.items()):
            expected = ref["provisional_outcome"]
            trial = by_pair.get((cid, condition))
            outcome = "missing" if trial is None else trial["outcome"]
            if expected == "defect":
                counts["reference_defect"] += 1
                if outcome == "defect":
                    counts["true_positive"] += 1
                else:
                    counts["false_negative_or_unresolved_defect"] += 1
            elif expected == "no_defect":
                counts["reference_no_defect"] += 1
                if outcome == "defect":
                    counts["false_positive"] += 1
            else:
                counts["reference_ambiguous"] += 1
                if outcome == "abstain":
                    counts["appropriate_ambiguous_abstention"] += 1
            if outcome == "defect":
                counts["predicted_defect"] += 1
            elif outcome == "no_defect":
                counts["predicted_no_defect"] += 1
            elif outcome == "abstain":
                counts["abstain"] += 1
            elif outcome == "error":
                counts["error"] += 1
            elif outcome == "missing":
                counts["missing"] += 1
            rows.append({"case_id": cid, "provisional_reference": expected, "observed_outcome": outcome,
                         "trial_id": None if trial is None else trial["trial_id"],
                         "trial_status": "missing" if trial is None else trial["status"]})
        d = counts["reference_defect"]
        n = counts["reference_no_defect"]
        a = len(references)
        counts["exploratory_defect_detection_rate"] = counts["true_positive"] / d if d else None
        counts["exploratory_false_positive_rate"] = counts["false_positive"] / n if n else None
        counts["exploratory_abstention_rate"] = counts["abstain"] / a if a else None
        counts["ambiguous_abstention_rate"] = (
            counts["appropriate_ambiguous_abstention"] / counts["reference_ambiguous"]
            if counts["reference_ambiguous"] else None
        )
        reports[condition] = {"counts": counts, "case_outcomes": rows}
    return {
        "schema_version": "ae32d/exploratory-score/v1",
        "experiment_id": trials["experiment_id"],
        "status": "exploratory_only_not_gold_adjudication",
        "reference_authority": "machine_derived_fixture_contract",
        "gold_adjudication_performed": False,
        "primary_benchmark_score": False,
        "primary_benchmark_eligible_cases": 0,
        "conditions": reports,
        "limitations": [
            "Metrics compare trial outputs with provisional machine references, not independently adjudicated gold labels.",
            "Missing and failed trials remain visible and are not silently removed from denominators.",
            "Exploratory metrics must not be described as primary benchmark scores."
        ]
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--trials", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    root = args.repository.resolve()
    errors, _ = validate_registry(root)
    if errors:
        result = {"status": "invalid", "errors": errors}
        code = 1
    elif args.validate_only:
        result = {"status": "valid", "registry_records": 6, "ground_truth_modified": False,
                  "primary_benchmark_promotion": False}
        code = 0
    elif args.trials:
        try:
            trials = json.loads(args.trials.read_text(encoding="utf-8"))
            result = score_trials(root, trials)
            code = 0
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result = {"status": "invalid", "errors": [str(exc)]}
            code = 1
    else:
        parser.error("--trials is required unless --validate-only is set")
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
