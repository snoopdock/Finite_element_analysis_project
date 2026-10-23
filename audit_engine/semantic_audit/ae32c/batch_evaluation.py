"""Offline, fail-closed AE-32C multi-provider batch evidence assessor.

The GitHub workflow manually authorizes and executes each live trial. This file
never calls a provider and cannot dispatch a workflow, alter source, or access
credentials. It scores protocol completion separately from declared evidence
coverage; diagnostic truth always requires external human review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

PROVIDERS = ("cloudflare", "nararouter", "openrouter")


def trial_sequence(rounds: int) -> list[tuple[int, str]]:
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 4:
        raise ValueError("rounds must be an integer between 1 and 4")
    return [(round_index, provider) for round_index in range(1, rounds + 1) for provider in PROVIDERS]


def evaluate_trial(root: Path, *, round_number: int, provider: str) -> dict[str, Any]:
    if (round_number, provider) not in trial_sequence(4):
        raise ValueError("invalid round/provider")
    failures: list[str] = []
    try:
        exit_code = int((root / "runner-exit-code.txt").read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        exit_code = None
    if exit_code != 0:
        failures.append("runner_nonzero_or_missing")
    candidates = sorted(root.rglob("comparison.json")) if root.is_dir() else []
    metrics: dict[str, Any] = {}
    if len(candidates) != 1:
        failures.append("comparison_missing_or_ambiguous")
    else:
        try:
            record = json.loads(candidates[0].read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("provider") != provider:
                raise ValueError("comparison_provider_mismatch")
            baseline = record["baseline"]
            assisted = record["graph_assisted"]
            summary = assisted["summary"]
            report = assisted["report"]
            if not all(isinstance(obj, Mapping) for obj in (baseline, summary, report)):
                raise ValueError("comparison_invalid")
            rounds = summary.get("model_rounds")
            tool_calls = summary.get("tool_call_count")
            coverage = report.get("required_source_coverage")
            if not isinstance(coverage, Mapping):
                coverage = {}
            metrics = {
                "baseline_status": baseline.get("status"),
                "investigation_status": summary.get("status"),
                "stop_reason": summary.get("stop_reason"),
                "model_rounds": rounds,
                "tool_call_count": tool_calls,
                "snapshot_status": report.get("snapshot_check_status"),
                "citation_validation": summary.get("final_citation_validation"),
                "coverage_status": coverage.get("status"),
                "missing_source_reads": list(coverage.get("missing_complete_reads", [])),
                "missing_root_citations": list(coverage.get("missing_root_cause_direct_citations", [])),
                "diagnosis_assurance": summary.get("diagnosis_assurance"),
                "elapsed_seconds": report.get("elapsed_seconds"),
            }
            requirements = {
                "baseline_completed": baseline.get("status") == "completed",
                "diagnosis_accepted": summary.get("status") in ("completed", "completed_with_incomplete_evidence"),
                "multiple_model_rounds": isinstance(rounds, int) and not isinstance(rounds, bool) and rounds >= 2,
                "evidence_tool_used": isinstance(tool_calls, int) and not isinstance(tool_calls, bool) and tool_calls >= 1,
                "snapshot_verified": report.get("snapshot_check_status") == "verified",
                "citations_resolved": summary.get("final_citation_validation") == "references_resolved",
            }
            for key, passed in requirements.items():
                if not passed:
                    failures.append(key)
            # `not_configured` does not satisfy the evidence-completeness gate.
            evidence_complete = (
                summary.get("status") == "completed"
                and coverage.get("status") == "complete"
                and not coverage.get("missing_complete_reads")
                and not coverage.get("missing_root_cause_direct_citations")
            )
            if not evidence_complete:
                failures.append("required_source_evidence_incomplete")
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            failures.append("comparison_invalid")
    protocol_complete = not any(code in failures for code in (
        "runner_nonzero_or_missing", "comparison_missing_or_ambiguous", "comparison_invalid",
        "baseline_completed", "diagnosis_accepted", "multiple_model_rounds",
        "evidence_tool_used", "snapshot_verified", "citations_resolved",
    ))
    return {
        "schema_version": "ae32c/trial-gate/v1",
        "round": round_number,
        "provider": provider,
        "protocol_complete": protocol_complete,
        "evidence_complete": "required_source_evidence_incomplete" not in failures and protocol_complete,
        "passed": not failures,
        "issues": sorted(set(failures)),
        "metrics": metrics,
        "diagnostic_accuracy": "not_assessed",
        "human_review_required": True,
    }


def build_summary(root: Path, rounds: int) -> dict[str, Any]:
    trials = []
    for round_number, provider in trial_sequence(rounds):
        trial_root = root / f"round-{round_number:02d}" / provider
        # Re-derive each result from comparison and runner exit; never trust a
        # pre-written success flag that could be stale or forged.
        trials.append(evaluate_trial(trial_root, round_number=round_number, provider=provider))
    result = {
        "schema_version": "ae32c/batch-evaluation/v1",
        "sequence": "round_robin",
        "rounds": rounds,
        "expected_trials": len(trials),
        "observed_trials": sum(bool(row["metrics"]) for row in trials),
        "protocol_completed": sum(row["protocol_complete"] for row in trials),
        "evidence_complete": sum(row["passed"] for row in trials),
        "passed": all(row["passed"] for row in trials),
        "trials": trials,
        "diagnostic_accuracy": "not_assessed",
        "human_review_required": True,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", required=True)
    parser.add_argument("--rounds", type=int, required=True, choices=(1, 2, 3, 4))
    args = parser.parse_args(argv)
    root = Path(args.batch_dir).resolve()
    if not root.is_dir():
        parser.error("batch directory missing")
    result = build_summary(root, args.rounds)
    (root / "batch-summary.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# AE-32C Round-Robin Evaluation", "", "| Round | Provider | Protocol | Evidence | Stop reason |", "|---:|---|---|---|---|"]
    for trial in result["trials"]:
        metrics = trial["metrics"]
        reason = str(metrics.get("stop_reason", "missing"))
        lines.append(f"| {trial['round']} | {trial['provider']} | {'PASS' if trial['protocol_complete'] else 'FAIL'} | {'PASS' if trial['passed'] else 'FAIL'} | `{reason}` |")
    lines.extend(["", f"- Complete evidence: **{result['evidence_complete']}/{result['expected_trials']}**", "- Diagnostic correctness: **not assessed; human review required**.", ""])
    (root / "batch-summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
