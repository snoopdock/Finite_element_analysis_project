"""CLI for a bounded, read-only AE-32C investigation.

The command never executes target repository code and never applies model-
generated patches. Reports are printed to stdout unless an output directory
outside the inspected repository is explicitly supplied.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from audit_engine.semantic_audit.ae32c import (
    InvestigationLimits,
    RepositoryInvestigator,
    write_report_artifacts,
)
from providers.factory import SUPPORTED_PROVIDERS, build_provider
from providers.safe_errors import sanitize_provider_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AE-32C read-only interactive repository investigation")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect")
    parser.add_argument("--problem", required=True, help="Failure or repository behavior to investigate")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default=None, help="Provider; defaults to FEA_LLM_PROVIDER or cloudflare")
    parser.add_argument("--model", default=None, help="Explicit model ID; otherwise use provider configuration")
    parser.add_argument("--source-revision", default=None, help="Caller-asserted source revision; not independently Git-verified")
    parser.add_argument("--runner-revision", default=None, help="Caller-asserted trusted runner revision")
    parser.add_argument("--output-dir", default=None, help="Optional existing directory outside the repository for JSON and Markdown reports")
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--max-tool-calls", type=int, default=10)
    parser.add_argument("--max-tokens-per-call", type=int, default=800)
    parser.add_argument("--max-total-tokens", type=int, default=18_000)
    parser.add_argument("--max-elapsed-seconds", type=int, default=180)
    args = parser.parse_args(argv)

    provider_name = (args.provider or os.environ.get("FEA_LLM_PROVIDER", "cloudflare")).strip().lower()
    model_name = (args.model or os.environ.get("FEA_LLM_MODEL", "")).strip()
    if provider_name not in SUPPORTED_PROVIDERS:
        print(json.dumps({"status": "error", "code": "unsupported_provider"}), file=sys.stdout)
        return 2

    budget = {
        "max_llm_calls_per_run": args.max_rounds,
        "max_tokens_per_call": args.max_tokens_per_call,
    }
    config = {
        "budget": budget,
        "cloudflare_models": [model_name] if model_name else ["@cf/meta/llama-3.1-8b-instruct-fast"],
    }
    try:
        provider = build_provider(
            config,
            budget,
            provider_name,
            model_name,
            environ=os.environ,
        )
        limits = InvestigationLimits(
            max_rounds=args.max_rounds,
            max_tool_calls=args.max_tool_calls,
            max_tokens_per_call=args.max_tokens_per_call,
            max_total_tokens=args.max_total_tokens,
            max_elapsed_seconds=args.max_elapsed_seconds,
        )
        investigator = RepositoryInvestigator(
            args.repo_root,
            provider,
            provider_name=provider_name,
            model_name=model_name or None,
            source_revision=args.source_revision,
            runner_revision=args.runner_revision,
            limits=limits,
        )
        report = investigator.run(args.problem)
    except Exception as exc:
        report = {
            "schema_version": "ae32c/interactive-investigation/v1",
            "status": "failed",
            "stop_reason": "initialization_failed",
            "error_type": sanitize_provider_error(type(exc).__name__, limit=100),
        }

    artifact_result = None
    if args.output_dir and report.get("schema_version") == "ae32c/interactive-investigation/v1":
        try:
            artifact_result = write_report_artifacts(report, args.output_dir, args.repo_root)
        except Exception as exc:
            artifact_result = {"publication": "failed", "error_code": sanitize_provider_error(type(exc).__name__, limit=100)}
    output = {"report": report}
    if artifact_result is not None:
        output["artifact_publication"] = artifact_result
    print(json.dumps(output, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report.get("status") in {"completed", "completed_with_incomplete_evidence"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
