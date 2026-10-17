"""CLI for exercising AE-32B evidence tools without contacting an LLM."""
from __future__ import annotations

import argparse
import json
import sys

from .evidence_tools import RepositoryEvidenceTools, build_tool_definitions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AE-32B read-only repository evidence tools")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect")
    parser.add_argument("--source-revision", default=None, help="Exact inspected source revision, if known")
    parser.add_argument("--runner-revision", default=None, help="Trusted tool runner revision, if known")
    parser.add_argument("--list-tools", action="store_true", help="Print provider-neutral tool definitions")
    parser.add_argument("--request-json", default=None, help='One JSON request: {"tool":"repository_summary","arguments":{}}')
    args = parser.parse_args(argv)
    if args.list_tools:
        print(json.dumps({"schema_version": "ae32b/tool-catalog/v1", "tools": build_tool_definitions()}, ensure_ascii=False, indent=2))
        return 0
    if not args.request_json:
        parser.error("provide --list-tools or --request-json")
    try:
        request = json.loads(args.request_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": {"code": "invalid_json", "message": str(exc)}}), file=sys.stdout)
        return 2
    if not isinstance(request, dict) or set(request) - {"tool", "arguments"} or not isinstance(request.get("tool"), str):
        print(json.dumps({"status": "error", "error": {"code": "invalid_request", "message": "Request must contain only tool and arguments"}}), file=sys.stdout)
        return 2
    try:
        server = RepositoryEvidenceTools(
            args.repo_root,
            source_revision=args.source_revision,
            runner_revision=args.runner_revision,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error": {"code": "index_failed", "message": str(exc)[:240]}}), file=sys.stdout)
        return 2
    response = server.invoke(request["tool"], request.get("arguments", {}))
    print(json.dumps(response, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if response.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
