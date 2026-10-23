"""Offline, fail-closed AE-32C multi-provider batch evidence assessor.

The GitHub workflow manually authorizes and executes each live trial. This file
never calls a provider and cannot dispatch a workflow, alter source, or access
credentials. It scores protocol completion separately from declared evidence
coverage; diagnostic truth always requires external human review.
"""
from __future__ import annotations

import argparse
import hashlib
import statistics
import json
from pathlib import Path
from typing import Any, Mapping

PROVIDERS = ("cloudflare", "nararouter", "openrouter")


def trial_sequence(rounds: int) -> list[tuple[int, str]]:
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 4:
        raise ValueError("rounds must be an integer between 1 and 4")
    return [(round_index, provider) for round_index in range(1, rounds + 1) for provider in PROVIDERS]


def _verify_comparison_checksums(root: Path, comparison_path: Path) -> bool:
    """Validate the producer manifest before trusting a comparison record.

    A matching digest is a consistency check, not authentication of a provider
    or a proof that the model's conclusions are correct.
    """
    parent = comparison_path.parent
    manifest = parent / "SHA256SUMS.txt"
    try:
        entries = manifest.read_text(encoding="ascii").splitlines()
        if not entries or len(entries) > 20:
            return False
        seen = set()
        for row in entries:
            digest, sep, raw = row.partition("  ")
            if sep != "  " or len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
                return False
            name = raw.strip()
            if name not in {"comparison.json", "comparison.md"} or name in seen:
                return False
            seen.add(name)
            child = parent / name
            if child.is_symlink() or not child.is_file():
                return False
            if hashlib.sha256(child.read_bytes()).hexdigest() != digest:
                return False
        return "comparison.json" in seen and "comparison.md" in seen
    except (OSError, UnicodeError, ValueError):
        return False


def _failure_class(stop_reason: str) -> str:
    """Stable coarse label; does not guess transport internals from HTTP 200."""
    if stop_reason in {"diagnosis_submitted", "diagnosis_submitted_with_required_source_coverage_gap"}:
        return "none_or_evidence_gap"
    if "provider" in stop_reason or "transport" in stop_reason:
        return "provider_or_transport"
    if "json" in stop_reason or "recovery" in stop_reason or "finalization" in stop_reason:
        return "model_protocol_or_budget"
    if "source" in stop_reason or "citation" in stop_reason or "evidence" in stop_reason:
        return "source_or_evidence"
    return "other_or_unclassified"


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
            if not _verify_comparison_checksums(root, candidates[0]):
                failures.append("comparison_sha256_manifest_invalid")
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
            source_support = report.get("source_textual_support")
            if not isinstance(source_support, Mapping):
                source_support = {}
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
                "source_textual_support_status": source_support.get("status", "not_assessed"),
                "source_anchor_count": source_support.get("declared_anchor_count", 0),
                "source_missing_anchors": list(source_support.get("missing_direct_cited_anchors", []))[:16],
                "provider_reported_tokens": (report.get("budget") or {}).get("provider_reported_tokens") if isinstance(report.get("budget"), Mapping) else None,
                "protocol_failure_class": _failure_class(str(summary.get("stop_reason", "unknown"))),
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
            # E.4 task-declared witnesses must be sourced from code lines, not
            # class declarations. Legacy evaluations without a declared witness
            # are not automatically failed; they remain not assessed.
            if source_support.get("status") != "complete" or source_support.get("missing_direct_cited_anchors"):
                failures.append("required_direct_source_anchor_support_incomplete")
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            failures.append("comparison_invalid")
    protocol_complete = not any(code in failures for code in (
        "runner_nonzero_or_missing", "comparison_missing_or_ambiguous", "comparison_invalid",
        "baseline_completed", "diagnosis_accepted", "multiple_model_rounds",
        "evidence_tool_used", "snapshot_verified", "citations_resolved",
        "comparison_sha256_manifest_invalid",
    ))
    return {
        "schema_version": "ae32c/trial-gate/v1",
        "round": round_number,
        "provider": provider,
        "protocol_complete": protocol_complete,
        "evidence_complete": not any(x in failures for x in ("required_source_evidence_incomplete", "required_direct_source_anchor_support_incomplete")) and protocol_complete,
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
    # Provider breakdowns are descriptive, include failures in denominators,
    # and never infer independently established diagnostic correctness.
    provider_breakdown = {}
    for name in PROVIDERS:
        subset = [row for row in trials if row["provider"] == name]
        durations = [row["metrics"].get("elapsed_seconds") for row in subset]
        durations = [float(x) for x in durations if isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= float(x) < 100_000]
        causes = {}
        for row in subset:
            reason = str(row["metrics"].get("stop_reason", "missing"))
            if not row["passed"]:
                causes[reason] = causes.get(reason, 0) + 1
        provider_breakdown[name] = {
            "trials": len(subset),
            "protocol_completed": sum(bool(row["protocol_complete"]) for row in subset),
            "evidence_complete": sum(bool(row["evidence_complete"]) for row in subset),
            "textual_support_complete": sum(row["metrics"].get("source_textual_support_status") == "complete" for row in subset),
            "textual_support_not_assessed": sum(row["metrics"].get("source_textual_support_status") in (None, "not_assessed", "not_configured") for row in subset),
            "median_elapsed_seconds": round(statistics.median(durations), 3) if durations else None,
            "duration_sample_count": len(durations),
            "stop_reasons_for_failed_trials": dict(sorted(causes.items())),
            "diagnostic_accuracy": "not_assessed",
        }
    result = {
        "schema_version": "ae32c/batch-evaluation/v1",
        "sequence": "round_robin",
        "rounds": rounds,
        "expected_trials": len(trials),
        "observed_trials": sum(bool(row["metrics"]) for row in trials),
        "protocol_completed": sum(row["protocol_complete"] for row in trials),
        "evidence_complete": sum(row["passed"] for row in trials),
        "passed": all(row["passed"] for row in trials),
        "provider_breakdown": provider_breakdown,
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
    lines += ["", "## Per-provider operational measures", "", "| Provider | Protocol | Evidence | Textual support | Median seconds |", "|---|---:|---:|---:|---:|"]
    for name, row in result["provider_breakdown"].items():
        lines.append(f"| {name} | {row['protocol_completed']}/{row['trials']} | {row['evidence_complete']}/{row['trials']} | {row['textual_support_complete']}/{row['trials']} | {row['median_elapsed_seconds']} |")
    lines.extend(["", f"- Complete evidence: **{result['evidence_complete']}/{result['expected_trials']}**", "- Diagnostic correctness: **not assessed; human review required**.", ""])
    (root / "batch-summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
