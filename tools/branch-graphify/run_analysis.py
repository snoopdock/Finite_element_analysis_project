#!/usr/bin/env python3
"""Build Graphify code maps and Git lineage reports for two repository refs."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
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
        command, cwd=str(cwd) if cwd else None, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
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
        result = git(repo, "rev-parse", "--verify", candidate, check=False)
        if result:
            return result.splitlines()[0]
    raise RuntimeError(f"Cannot resolve branch/ref: {name}")


def graphify_command() -> list[str]:
    executable = shutil.which("graphify")
    if executable:
        return [executable]
    if importlib.util.find_spec("graphify") is not None:
        return [sys.executable, "-m", "graphify"]
    raise RuntimeError("Graphify CLI not found. Install with: python -m pip install graphifyy")


def graphify_version() -> str:
    for package in ("graphifyy", "graphify"):
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    return "unknown"


def graph_collections(payload: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    graph = payload.get("graph", payload)
    if not isinstance(graph, dict):
        raise ValueError("Graphify JSON has no graph object")
    nodes, edges = graph.get("nodes", []), graph.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Graphify JSON nodes/edges are not arrays")
    return nodes, edges


def node_key(node: dict[str, Any]) -> str:
    for key in ("id", "node_id", "key", "name", "label"):
        if node.get(key) is not None:
            return str(node[key])
    return json.dumps(node, sort_keys=True, ensure_ascii=False)


def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    source = next((edge[k] for k in ("source", "from", "src", "source_id") if edge.get(k) is not None), "")
    target = next((edge[k] for k in ("target", "to", "dst", "target_id") if edge.get(k) is not None), "")
    relation = next((edge[k] for k in ("relation", "type", "label", "kind", "edge_type") if edge.get(k) is not None), "")
    return str(source), str(target), str(relation)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_name(branch: str) -> str:
    return branch.replace("/", "-")


def run_graphify(repo: Path, commit: str, branch: str, destination: Path,
                 worktree_root: Path, command: list[str]) -> dict[str, Any]:
    snapshot = worktree_root / safe_name(branch)
    destination.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "--detach", str(snapshot), commit)
    try:
        cmd = command + [
            "extract", str(snapshot), "--code-only", "--force",
            "--out", str(destination),
        ]
        proc = subprocess.run(
            cmd, cwd=str(repo), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
        )
        (destination / "graphify-run.log").write_text(proc.stdout, encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(
                f"Graphify failed for {branch} (exit {proc.returncode}); "
                f"inspect {destination / 'graphify-run.log'}"
            )

        generated = destination / "graphify-out"
        required = ("graph.html", "graph.json", "GRAPH_REPORT.md")
        missing = [name for name in required if not (generated / name).is_file()]
        if missing:
            found = sorted(p.name for p in generated.glob("*")) if generated.exists() else []
            raise RuntimeError(
                f"Graphify output for {branch} incomplete; missing {missing}; found {found}"
            )

        # Publish only portable user-facing artifacts; omit machine-local caches.
        for filename in required:
            shutil.copy2(generated / filename, destination / filename)

        graph_path = destination / "graph.json"
        nodes, edges = graph_collections(json.loads(graph_path.read_text(encoding="utf-8")))
        return {
            "branch": branch, "commit": commit, "graphify_version": graphify_version(),
            "node_count": len(nodes), "edge_count": len(edges),
            "graph_json_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
            "artifacts": {"html": "graph.html", "json": "graph.json", "report": "GRAPH_REPORT.md"},
        }
    finally:
        git(repo, "worktree", "remove", "--force", str(snapshot), check=False)
        git(repo, "worktree", "prune", check=False)


def git_inventory(repo: Path, base_name: str, compare_name: str,
                  base_sha: str, compare_sha: str) -> dict:
    merge_base = git(repo, "merge-base", base_sha, compare_sha)
    counts = git(repo, "rev-list", "--left-right", "--count", f"{base_sha}...{compare_sha}")
    base_only, compare_only = [int(value) for value in counts.split()]
    base_changes = git(repo, "diff", "--name-status", "--find-renames",
                       f"{merge_base}..{base_sha}").splitlines()
    compare_changes = git(repo, "diff", "--name-status", "--find-renames",
                          f"{merge_base}..{compare_sha}").splitlines()
    symmetric_log = git(
        repo, "log", "--left-right", "--cherry-pick",
        "--format=%m%x09%H%x09%s", f"{base_sha}...{compare_sha}",
    ).splitlines()

    def parse_changes(lines: list[str]) -> list[dict[str, str]]:
        result = []
        for line in lines:
            fields = line.split("\t")
            if len(fields) >= 2:
                item = {"status": fields[0], "path": fields[-1]}
                if len(fields) == 3:
                    item["previous_path"] = fields[1]
                result.append(item)
        return result

    commits = []
    for line in symmetric_log:
        fields = line.split("\t", 2)
        if len(fields) == 3:
            commits.append({"side": fields[0], "sha": fields[1], "subject": fields[2]})

    return {
        "base_branch": base_name, "compare_branch": compare_name,
        "base_sha": base_sha, "compare_sha": compare_sha,
        "merge_base_sha": merge_base,
        "base_only_commit_count": base_only,
        "compare_only_commit_count": compare_only,
        "base_changes_since_merge_base": parse_changes(base_changes),
        "compare_changes_since_merge_base": parse_changes(compare_changes),
        "symmetric_commits": commits,
    }


def architecture_delta(base_dir: Path, compare_dir: Path) -> dict:
    base_payload = json.loads((base_dir / "graph.json").read_text(encoding="utf-8"))
    compare_payload = json.loads((compare_dir / "graph.json").read_text(encoding="utf-8"))
    base_nodes, base_edges = graph_collections(base_payload)
    compare_nodes, compare_edges = graph_collections(compare_payload)
    base_node_ids = {node_key(node) for node in base_nodes}
    compare_node_ids = {node_key(node) for node in compare_nodes}
    base_edge_ids = {edge_key(edge) for edge in base_edges}
    compare_edge_ids = {edge_key(edge) for edge in compare_edges}
    return {
        "identity_note": (
            "Node keys use the first available id/node_id/key/name/label field. "
            "Edge keys use source/target/relation-like fields. These are structural "
            "comparison keys, not proof of semantic equivalence."
        ),
        "base": {"branch": base_dir.name, "node_count": len(base_nodes), "edge_count": len(base_edges)},
        "compare": {"branch": compare_dir.name, "node_count": len(compare_nodes), "edge_count": len(compare_edges)},
        "nodes": {
            "common_count": len(base_node_ids & compare_node_ids),
            "base_only_count": len(base_node_ids - compare_node_ids),
            "compare_only_count": len(compare_node_ids - base_node_ids),
            "base_only": sorted(base_node_ids - compare_node_ids),
            "compare_only": sorted(compare_node_ids - base_node_ids),
        },
        "edges": {
            "common_count": len(base_edge_ids & compare_edge_ids),
            "base_only_count": len(base_edge_ids - compare_edge_ids),
            "compare_only_count": len(compare_edge_ids - base_edge_ids),
            "base_only": [list(x) for x in sorted(base_edge_ids - compare_edge_ids)],
            "compare_only": [list(x) for x in sorted(compare_edge_ids - base_edge_ids)],
        },
    }


def render_reports(output: Path, git_data: dict, graph_data: dict,
                   delta: dict, base_name: str, compare_name: str) -> None:
    write_json(output / "git-lineage.json", git_data)
    write_json(output / "architecture-delta.json", delta)
    base_short, compare_short = git_data["base_sha"][:12], git_data["compare_sha"][:12]
    merge_short = git_data["merge_base_sha"][:12]
    mermaid = "\n".join([
        "flowchart LR",
        f'  MB["Merge base<br/>{merge_short}"]',
        f'  B["{base_name}<br/>{base_short}"]',
        f'  C["{compare_name}<br/>{compare_short}"]',
        "  MB --> B", "  MB --> C",
        f'  B_note["{git_data["base_only_commit_count"]} commits unique to {base_name}"]',
        f'  C_note["{git_data["compare_only_commit_count"]} commits unique to {compare_name}"]',
        "  B -.-> B_note", "  C -.-> C_note", "",
    ])
    (output / "git-lineage.mmd").write_text(mermaid, encoding="utf-8")

    n, e = delta["nodes"], delta["edges"]
    comparison = [
        "# Branch architecture comparison", "",
        f"- Base: {base_name} at {git_data['base_sha']}",
        f"- Compared branch: {compare_name} at {git_data['compare_sha']}",
        f"- Merge base: {git_data['merge_base_sha']}", "",
        "## Graphify code-structure counts", "",
        "| Metric | Base branch | Comparison branch |", "|---|---:|---:|",
        f"| Nodes | {graph_data[base_name]['node_count']} | {graph_data[compare_name]['node_count']} |",
        f"| Edges | {graph_data[base_name]['edge_count']} | {graph_data[compare_name]['edge_count']} |", "",
        "## Identity-based graph delta", "",
        f"- Common nodes: {n['common_count']}",
        f"- Nodes only in {base_name}: {n['base_only_count']}",
        f"- Nodes only in {compare_name}: {n['compare_only_count']}",
        f"- Common relationships: {e['common_count']}",
        f"- Relationships only in {base_name}: {e['base_only_count']}",
        f"- Relationships only in {compare_name}: {e['compare_only_count']}", "",
        "Detailed identity lists are in architecture-delta.json. Graphify IDs and extracted relationships can change across tool versions; inspect source diffs before interpreting a graph delta as a code deletion or addition.", "",
        "## Git divergence", "",
        f"- Commits unique to {base_name}: {git_data['base_only_commit_count']}",
        f"- Commits unique to {compare_name}: {git_data['compare_only_commit_count']}",
        f"- Files changed from merge base on {base_name}: {len(git_data['base_changes_since_merge_base'])}",
        f"- Files changed from merge base on {compare_name}: {len(git_data['compare_changes_since_merge_base'])}", "",
        "See git-lineage.json for complete file inventories and the symmetric commit list.", "",
    ]
    (output / "architecture-comparison.md").write_text("\n".join(comparison), encoding="utf-8")

    report = [
        "# Branch Graphify analysis", "",
        f"- Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"- Graphify version: {graphify_version()}",
        f"- Base branch: {base_name} at {git_data['base_sha']}",
        f"- Comparison branch: {compare_name} at {git_data['compare_sha']}",
        f"- Merge base: {git_data['merge_base_sha']}", "",
        "## Start here", "",
        "- [Architecture comparison](architecture-comparison.md)",
        "- [Git lineage JSON](git-lineage.json)",
        "- [Git lineage diagram source](git-lineage.mmd)",
        "- [Architecture delta JSON](architecture-delta.json)",
        f"- [{base_name} interactive graph]({safe_name(base_name)}/graph.html)",
        f"- [{base_name} Graphify report]({safe_name(base_name)}/GRAPH_REPORT.md)",
        f"- [{compare_name} interactive graph]({safe_name(compare_name)}/graph.html)",
        f"- [{compare_name} Graphify report]({safe_name(compare_name)}/GRAPH_REPORT.md)", "",
        "## Graphify run summary", "",
        "| Branch | Commit | Nodes | Edges |", "|---|---|---:|---:|",
        f"| {base_name} | {graph_data[base_name]['commit'][:12]} | {graph_data[base_name]['node_count']} | {graph_data[base_name]['edge_count']} |",
        f"| {compare_name} | {graph_data[compare_name]['commit'][:12]} | {graph_data[compare_name]['node_count']} | {graph_data[compare_name]['edge_count']} |", "",
        "## Interpretation", "",
        "Graphify maps code structure within each branch snapshot. Git metadata separately establishes ancestry and divergence. Neither graph similarity nor node overlap proves behavioral equivalence. Review source-level file inventories and commits before drawing architectural conclusions.", "",
    ]
    (output / "analysis-report.md").write_text("\n".join(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="main")
    parser.add_argument("--compare", default="stage1/section-uuids")
    parser.add_argument("--output", type=Path, default=Path("branch-graphify-results/latest"))
    args = parser.parse_args()

    repo = args.repo.resolve()
    if not git(repo, "rev-parse", "--git-dir", check=False):
        raise RuntimeError(f"{repo} is not a Git working tree")
    base_sha, compare_sha = resolve_ref(repo, args.base), resolve_ref(repo, args.compare)
    output = args.output if args.output.is_absolute() else repo / args.output
    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    command = graphify_command()
    with tempfile.TemporaryDirectory(prefix="branch-graphify-worktrees-") as temp:
        worktree_root = Path(temp)
        base_dir, compare_dir = output / safe_name(args.base), output / safe_name(args.compare)
        print(f"Graphify {graphify_version()}: analyzing {args.base} at {base_sha}")
        base_info = run_graphify(repo, base_sha, args.base, base_dir, worktree_root, command)
        print(f"Graphify {graphify_version()}: analyzing {args.compare} at {compare_sha}")
        compare_info = run_graphify(repo, compare_sha, args.compare, compare_dir, worktree_root, command)

    git_data = git_inventory(repo, args.base, args.compare, base_sha, compare_sha)
    graph_data = {args.base: base_info, args.compare: compare_info}
    delta = architecture_delta(base_dir, compare_dir)
    write_json(output / "graphify-run-summary.json", graph_data)
    render_reports(output, git_data, graph_data, delta, args.base, args.compare)
    print(f"Analysis complete. Results: {output}")
    print(
        f"Git divergence: {git_data['base_only_commit_count']} commits unique to {args.base}; "
        f"{git_data['compare_only_commit_count']} unique to {args.compare}."
    )
    print(
        f"Graphify nodes: {base_info['node_count']} vs {compare_info['node_count']}; "
        f"edges: {base_info['edge_count']} vs {compare_info['edge_count']}."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
