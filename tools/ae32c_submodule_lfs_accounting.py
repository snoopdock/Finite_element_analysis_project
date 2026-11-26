#!/usr/bin/env python3
"""Emit bounded recursive Git submodule/LFS accounting for a verified source snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from audit_engine.semantic_audit.ae32c.git_object_source import GitObjectSourceProvider
from audit_engine.semantic_audit.ae32c.submodule_lfs_accounting import account_submodule_lfs


def _mapping(values: list[str], option: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(option + "_must_be_PATH_EQUALS_DIRECTORY")
        key, directory = value.split("=", 1)
        if not key or not directory or key in result:
            raise ValueError(option + "_mapping_invalid_or_duplicate")
        result[key] = directory
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".")
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--submodule-repository", action="append", default=[],
                        metavar="GITLINK_PATH=LOCAL_DIRECTORY",
                        help="Explicit already-present submodule repository; repeat for nested paths")
    parser.add_argument("--lfs-object-store", action="append", default=[],
                        metavar="GITLINK_PATH=LOCAL_OBJECT_STORE",
                        help="Explicit local LFS object store for a supplied submodule; repeat as needed")
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--max-repositories", type=int, default=256)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(Path(args.source_manifest).read_text(encoding="utf-8"))
        provider = GitObjectSourceProvider(args.repository, manifest)
        report = account_submodule_lfs(
            provider,
            submodule_repositories=_mapping(args.submodule_repository, "submodule_repository"),
            lfs_object_stores=_mapping(args.lfs_object_store, "lfs_object_store"),
            max_depth=args.max_depth,
            max_repositories=args.max_repositories,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n", encoding="utf-8")
        print(json.dumps({
            "schema": report["schema"],
            "gitlink_count": report["gitlink_count"],
            "scanned_repository_count": report["scanned_repository_count"],
            "recursive_scan_complete": report["recursive_scan_complete"],
            "recursive_content_verified": report["recursive_content_verified"],
            "accounting_sha256": report["accounting_sha256"],
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print("submodule_lfs_accounting_error:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
