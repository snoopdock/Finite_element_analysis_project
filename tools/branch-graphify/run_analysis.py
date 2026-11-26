#!/usr/bin/env python3
"""Build one commit-pinned, code-only Graphify snapshot for a single branch."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run(command: list[str], cwd: Path | None = None, check: bool = True) -> str:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(command)}\n{proc.stdout}"
        )
    return proc.stdout.strip()


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(["git", "-C", str(repo), *args], check=check)


def resolve_ref(repo: Path, name: str) -> str:
    for candidate in (f"refs/remotes/origin/{name}", f"refs/heads/{name}", name):
        result = git(repo, "rev-parse", "--verify", "--quiet", candidate, check=False)
        if result:
            return result.splitlines()[0]
    raise RuntimeError(f"Cannot resolve branch/ref: {name}")


def graphify_command() -> list[str]:
    executable = shutil.which("graphify")
    if executable:
        return [executable]
    if importlib.util.find_spec("graphify") is not None:
        return [sys.executable, "-m", "graphify"]
    raise RuntimeError("Graphify CLI not found; install tools/branch-graphify/requirements.txt")


def graphify_version() -> str:
    for package in ("graphifyy", "graphify"):
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "unknown"


def graph_collections(payload: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    if isinstance(payload.get("nodes"), list):
        nodes = payload["nodes"]
        edges = payload.get("edges", payload.get("links", []))
    else:
        graph = payload.get("graph", payload)
        if not isinstance(graph, dict):
            raise ValueError("Graphify JSON has no graph object")
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", graph.get("links", []))
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Graphify JSON nodes/edges (or links) are not arrays")
    return nodes, edges


def safe_name(branch: str) -> str:
    return branch.replace("/", "-")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def analyze_branch(
    repo: Path, branch: str, commit: str, output: Path, worktree_root: Path,
    command: list[str],
) -> dict[str, Any]:
    snapshot = worktree_root / safe_name(branch)
    generated = output / "graphify-out"
    output.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "--detach", str(snapshot), commit)
    try:
        extract = subprocess.run(
            command + ["extract", str(snapshot), "--code-only", "--force", "--out", str(output)],
            cwd=str(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace",
        )
        (output / "graphify-run.log").write_text(extract.stdout, encoding="utf-8")
        if extract.returncode:
            raise RuntimeError(
                f"Graphify extraction failed for {branch} (exit {extract.returncode}); "
                "inspect graphify-run.log"
            )

        cluster = subprocess.run(
            command + ["cluster-only", str(snapshot), "--graph", str(generated / "graph.json"),
                       "--no-label"],
            cwd=str(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace",
        )
        with (output / "graphify-run.log").open("a", encoding="utf-8") as log:
            log.write("\n\n--- cluster-only ---\n")
            log.write(cluster.stdout)
        if cluster.returncode:
            raise RuntimeError(
                f"Graphify cluster-only failed for {branch} (exit {cluster.returncode}); "
                "inspect graphify-run.log"
            )

        required = ("graph.html", "graph.json", "GRAPH_REPORT.md")
        missing = [name for name in required if not (generated / name).is_file()]
        if missing:
            found = sorted(path.name for path in generated.glob("*")) if generated.exists() else []
            raise RuntimeError(
                f"Graphify output for {branch} incomplete; missing {missing}; found {found}"
            )
        for filename in required:
            shutil.copy2(generated / filename, output / filename)
        shutil.rmtree(generated)

        graph_path = output / "graph.json"
        nodes, edges = graph_collections(json.loads(graph_path.read_text(encoding="utf-8")))
        return {
            "branch": branch,
            "source_commit": commit,
            "graphify_version": graphify_version(),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "graph_json_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
            "artifacts": {
                "html": "graph.html",
                "json": "graph.json",
                "report": "GRAPH_REPORT.md",
                "log": "graphify-run.log",
            },
            "interpretation_boundary": (
                "Code-structure extraction only. Presence of an adapter, import, or graph "
                "relationship is not evidence that the adapter is invoked or computes correctly."
            ),
        }
    finally:
        git(repo, "worktree", "remove", "--force", str(snapshot), check=False)
        git(repo, "worktree", "prune", check=False)


def render_report(output: Path, metadata: dict[str, Any]) -> None:
    write_json(output / "run-metadata.json", metadata)
    report = [
        "# Branch Graphify snapshot",
        "",
        f"- Branch: `{metadata['branch']}`",
        f"- Source commit: `{metadata['source_commit']}`",
        f"- Graphify version: `{metadata['graphify_version']}`",
        f"- Generated (UTC): {metadata['generated_at_utc']}",
        f"- Nodes: {metadata['node_count']}",
        f"- Edges: {metadata['edge_count']}",
        f"- Graph JSON SHA-256: `{metadata['graph_json_sha256']}`",
        "",
        "## Artifacts",
        "",
        "- [Interactive graph](graph.html)",
        "- [Machine-readable graph](graph.json)",
        "- [Graphify structural report](GRAPH_REPORT.md)",
        "- [Run metadata](run-metadata.json)",
        "- [Execution log](graphify-run.log)",
        "",
        "## Audit interpretation",
        "",
        "This is an independent structural snapshot of one exact branch commit. It does not "
        "compare branches and does not establish runtime behavior, adapter invocation, "
        "computation correctness, or backend suitability. Those claims require separate "
        "source tracing and behavioral/structural validation.",
        "",
    ]
    (output / "analysis-report.md").write_text("\n".join(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--branch", required=True, help="One branch name to analyze")
    parser.add_argument("--commit", help="Exact commit SHA; defaults to the resolved branch tip")
    parser.add_argument(
        "--output", type=Path,
        help="Output directory; defaults to branch-graphify-results/latest/<branch-slug>",
    )
    args = parser.parse_args()

    repo = args.repo.resolve()
    if not git(repo, "rev-parse", "--git-dir", check=False):
        raise RuntimeError(f"{repo} is not a Git working tree")
    resolved = resolve_ref(repo, args.branch)
    commit = args.commit or resolved
    git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    output = args.output or (repo / "branch-graphify-results" / "latest" / safe_name(args.branch))
    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    command = graphify_command()
    with tempfile.TemporaryDirectory(prefix="branch-graphify-worktree-") as temporary:
        metadata = analyze_branch(
            repo, args.branch, commit, output, Path(temporary), command
        )
    render_report(output, metadata)
    print(json.dumps({
        "status": "CAPTURED",
        "branch": args.branch,
        "source_commit": commit,
        "node_count": metadata["node_count"],
        "edge_count": metadata["edge_count"],
        "graph_json_sha256": metadata["graph_json_sha256"],
        "output": str(output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
