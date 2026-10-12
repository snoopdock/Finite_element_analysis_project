"""GE-01: strict read-only projection of scientific and SAT-audit evidence into SemanticGraph.

This is an *adapter* to the pre-existing graph core, not a new graph library.
Neither structural citations nor provenance create scientific truth or authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph.service import SemanticGraphAnalysisService
from core.knowledge_graph import validate_graph_references

SCHEMA = "graph-domain-view/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 2_000_000


class GraphDomainError(ValueError):
    """Unsafe or inconsistent domain data; never silently repair it."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise GraphDomainError("Domain input must be finite JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _copy(value: Any) -> Any:
    # Immutable-by-value projection: no references into caller-owned records.
    return json.loads(_canonical(value))


def _identity(kind: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 1024:
        raise GraphDomainError(f"Invalid {kind} identifier")
    return f"{kind}:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _uuid(value: str, kind: str) -> str:
    try:
        normalized = str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise GraphDomainError(f"Invalid {kind} UUID") from exc
    if normalized != value:
        raise GraphDomainError(f"Noncanonical {kind} UUID")
    return normalized


def _mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise GraphDomainError(f"{name} must be an object")
    return value


def _id_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise GraphDomainError(f"{field} must be a list of identifiers")
    if len(value) != len(set(value)):
        raise GraphDomainError(f"Repeated {field} reference")
    return value


@dataclass(frozen=True)
class GraphDomainView:
    graph: SemanticGraph
    domain: str
    input_sha256: str

    @property
    def fingerprint(self) -> str:
        return graph_fingerprint(self.graph)

    def analyze(self, query):
        """Reuse the established graph analysis API; never write audit memory to disk."""
        return SemanticGraphAnalysisService(self.graph).analyze(query)

    def snapshot(self) -> dict:
        payload = self.graph.to_dict()
        payload["nodes"].sort(key=lambda n: n["id"])
        payload["edges"].sort(key=lambda e: (e["source"], e["target"], e["relation"], _canonical(e)))
        record = {
            "schema_version": SCHEMA,
            "domain": self.domain,
            "input_sha256": self.input_sha256,
            "graph_fingerprint": self.fingerprint,
            "graph": payload,
            "authoritative_mutation_permitted": False,
            "scientific_truth_established": False,
        }
        record["snapshot_sha256"] = _digest(record)
        return record


def verify_snapshot(view: GraphDomainView, snapshot: Any) -> bool:
    """Recompute all content from the supplied read-only view (not just rehash a forgery)."""
    if snapshot != view.snapshot():
        raise GraphDomainError("Graph snapshot does not match the independently projected input")
    return True


def from_scientific_graph(raw: Mapping[str, Any]) -> GraphDomainView:
    """Bridge the existing core.knowledge_graph UUID model; reject dangling refs.

    A legacy UUID denotes identity, not scientific accuracy. Source identifiers
    remain unverified until a separate source resolver checks them.
    """
    if not isinstance(raw, Mapping):
        raise GraphDomainError("Scientific graph must be a mapping")
    data = _copy(dict(raw))
    concepts = _mapping(data.get("concepts", {}), "concepts")
    propositions = _mapping(data.get("propositions", {}), "propositions")
    relationships = _mapping(data.get("relationships", {}), "relationships")
    if sum(map(len, (concepts, propositions, relationships))) > 50000:
        raise GraphDomainError("Graph exceeds GE-01 resource limit")
    for kind, collection, id_field in (("concept", concepts, "concept_id"),
                                       ("proposition", propositions, "proposition_id"),
                                       ("relationship", relationships, "relationship_id")):
        for key, item in collection.items():
            _uuid(key, kind)
            _mapping(item, kind)
            if item.get(id_field) != key:
                raise GraphDomainError(f"Inconsistent {kind} key and record identity")
    # The established reference validator detects graph-dangling UUID edges.
    violations = validate_graph_references({"concepts": concepts, "propositions": propositions,
                                            "relationships": relationships})
    if violations:
        raise GraphDomainError("Scientific graph reference violation: " + "; ".join(violations[:8]))

    graph = SemanticGraph()
    # Namespace disambiguates source IDs and cross-collection UUIDs.
    node_ids = {"concept": {}, "proposition": {}}
    for kind, collection, entity_type in (("concept", concepts, "ScientificConcept"),
                                          ("proposition", propositions, "ScientificProposition")):
        for key, item in sorted(collection.items()):
            node_id = f"scientific:{kind}:{key}"
            node_ids[kind][key] = node_id
            safe = {k: _copy(item.get(k)) for k in
                    (("name", "type", "status") if kind == "concept" else
                     ("statement", "status", "framework", "assumptions", "conditions", "domain_of_validity"))
                    if k in item}
            graph.add_node(SemanticNode(node_id, entity_type, attributes=safe,
                                        metadata={"original_id": key, "source_verified": False,
                                                  "scientific_truth_established": False}))

    source_ids = set()
    for collection in (concepts, propositions, relationships):
        for item in collection.values():
            source_ids.update(_id_list(item.get("source_ids", []), "source_ids"))
    for value in sorted(source_ids):
        graph.add_node(SemanticNode(_identity("scientific:source", value), "ScientificSourceRef",
                                    attributes={"source_id_unverified": value},
                                    metadata={"source_verified": False}))
    edges: list[SemanticEdge] = []
    for key, item in sorted(concepts.items()):
        for parent in _id_list(item.get("parent_concept_ids", []), "parent_concept_ids"):
            edges.append(SemanticEdge(node_ids["concept"][key], node_ids["concept"][parent],
                                      "SUBCONCEPT_OF", metadata={"scientific_support_verified": False}))
    for kind, collection in (("concept", concepts), ("proposition", propositions)):
        for key, item in sorted(collection.items()):
            for source_id in _id_list(item.get("source_ids", []), "source_ids"):
                edges.append(SemanticEdge(node_ids[kind][key], _identity("scientific:source", source_id),
                                          "CITES_SOURCE", metadata={"source_verified": False}))
            if kind == "proposition":
                for concept_id in _id_list(item.get("concept_ids", []), "concept_ids"):
                    edges.append(SemanticEdge(node_ids[kind][key], node_ids["concept"][concept_id],
                                              "HAS_CONCEPT", metadata={"scientific_support_verified": False}))
    for key, item in sorted(relationships.items()):
        source_id = item["source_id"]
        target_id = item["target_id"]
        src = node_ids["concept"].get(source_id) or node_ids["proposition"].get(source_id)
        dst = node_ids["concept"].get(target_id) or node_ids["proposition"].get(target_id)
        if src is None or dst is None:
            raise GraphDomainError("Unknown scientific relationship endpoint")
        edges.append(SemanticEdge(src, dst, "SCIENTIFIC_RELATION", attributes={
            "claimed_relation_type": str(item.get("type", "related_to")),
            "status_unverified": str(item.get("status", "proposed"))
        }, metadata={"relationship_id": key, "scientific_support_verified": False}))
        for prop_id in _id_list(item.get("proposition_ids", []), "proposition_ids"):
            edges.append(SemanticEdge(src, node_ids["proposition"][prop_id],
                                      "RELATION_ASSERTED_BY", metadata={"relationship_id": key,
                                                                        "scientific_support_verified": False}))
    for edge in sorted(edges, key=lambda e: (e.source_id,e.target_id,e.relation_type,_canonical(e.metadata))):
        graph.add_edge(edge)
    return GraphDomainView(graph, "scientific_knowledge", _digest(data))


def from_verified_assurance_cycle(cycle: dict, repository: Path, *,
                                  review_submission: dict | None = None,
                                  github_actor: str = "unknown") -> GraphDomainView:
    """Project G3.5 citations *only after* source-bound independent verification."""
    from decision_memory.assurance_integration import verify_cycle, AssuranceIntegrationError
    if not isinstance(cycle, dict):
        raise GraphDomainError("Cycle must be a JSON object")
    if cycle.get("schema_version") != "sat-audit-integration/v1" or cycle.get("profile_id") != "G3.5":
        raise GraphDomainError("Expected G3.5 assurance cycle")
    try:
        if not verify_cycle(cycle, repository, review_submission=review_submission,
                            github_actor=github_actor):
            raise GraphDomainError("Independent G3.5 verification returned false")
    except (AssuranceIntegrationError, ValueError, OSError, TypeError) as exc:
        raise GraphDomainError("G3.5 cycle source verification failed") from exc
    projection = _mapping(cycle.get("graph_handoff"), "graph_handoff")
    if (projection.get("schema_version") != "sat-audit-graph-handoff/v1"
            or projection.get("authoritative_graph_mutation_permitted") is not False
            or projection.get("projection_is_semantic_entailment") is not False):
        raise GraphDomainError("Unsafe G3.5 handoff semantics")
    graph = SemanticGraph()
    nodes = projection.get("nodes")
    edges = projection.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list) or len(nodes)+len(edges) > 50000:
        raise GraphDomainError("Unsafe graph handoff collection")
    for item in sorted(nodes, key=lambda x: x.get("id", "") if isinstance(x, dict) else ""):
        _mapping(item, "graph node")
        ident = item.get("id")
        kind = item.get("type")
        if not isinstance(ident, str) or not ident or kind not in {"memory_record", "generated_claim"}:
            raise GraphDomainError("Unknown G3.5 node identity/type")
        if kind == "memory_record":
            sha = item.get("source_sha256")
            if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
                raise GraphDomainError("Source without bound SHA-256")
            attrs = {"record_id": item["record_id"], "source_path": item["source_path"],
                     "source_sha256": sha}
        else:
            attrs = {"claim_sha256": item["claim_sha256"], "claim_index": item["claim_index"],
                     "text_untrusted": item["text_untrusted"]}
        graph.add_node(SemanticNode("audit:"+ident, "Audit"+kind.title().replace("_", ""),
                                    attributes=_copy(attrs), metadata={"scientific_support_verified": False,
                                                                        "authority": "read_only"}))
    for item in sorted(edges, key=lambda x: (x.get("from", ""), x.get("to", "")) if isinstance(x,dict) else ("", "")):
        _mapping(item, "graph edge")
        if item.get("type") != "cites_structurally" or item.get("semantic_entailment_verified") is not False:
            raise GraphDomainError("Unproven G3.5 relation cannot imply scientific entailment")
        try:
            graph.add_edge(SemanticEdge("audit:"+item["from"], "audit:"+item["to"],
                                        "CITES_STRUCTURALLY", metadata={"semantic_entailment_verified": False}))
        except (TypeError, KeyError, ValueError) as exc:
            raise GraphDomainError("Invalid G3.5 citation edge") from exc
    return GraphDomainView(graph, "generated_text_audit", _digest(cycle))


def combine_views(*views: GraphDomainView) -> GraphDomainView:
    """Deterministic disjoint union; never infer joins from equal-looking labels."""
    if not views:
        raise GraphDomainError("Provide at least one domain view")
    graph = SemanticGraph()
    for view in sorted(views, key=lambda v: (v.domain, v.input_sha256)):
        for node in view.graph.nodes:
            if graph.has_node(node.node_id):
                raise GraphDomainError("Cross-domain identifier collision")
            graph.add_node(_copy_node(node))
        for edge in view.graph.edges:
            graph.add_edge(_copy_edge(edge))
    return GraphDomainView(graph, "combined_read_only", _digest([
        {"domain": v.domain, "input_sha256": v.input_sha256}
        for v in sorted(views, key=lambda v: (v.domain, v.input_sha256))]))


def _copy_node(node: SemanticNode) -> SemanticNode:
    return SemanticNode(node.node_id, node.entity_type, _copy(node.attributes), _copy(node.metadata))


def _copy_edge(edge: SemanticEdge) -> SemanticEdge:
    return SemanticEdge(edge.source_id, edge.target_id, edge.relation_type,
                        _copy(edge.attributes), _copy(edge.metadata))


def _unique_pairs(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise GraphDomainError("Duplicate JSON key")
        obj[k] = v
    return obj


def _read_json(path: Path) -> Any:
    if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise GraphDomainError("Unsafe JSON input path")
    if path.stat().st_size > MAX_BYTES:
        raise GraphDomainError("JSON input exceeds GE-01 limit")
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(GraphDomainError("Nonfinite number")))
    except (ValueError, UnicodeError) as exc:
        raise GraphDomainError("Invalid JSON input") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="GE-01 read-only graph projection")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--knowledge-graph", help="Existing core.knowledge_graph data as JSON")
    parser.add_argument("--g35-cycle", help="Verified G3.5 cycle JSON")
    parser.add_argument("--output", help="Output JSON file outside the source repository")
    args = parser.parse_args(argv)
    repository = Path(args.repository).resolve(strict=True)
    if not repository.is_dir() or (not args.knowledge_graph and not args.g35_cycle):
        raise GraphDomainError("Expected repository and at least one graph input")
    views = []
    if args.knowledge_graph:
        views.append(from_scientific_graph(_read_json(Path(args.knowledge_graph))))
    if args.g35_cycle:
        views.append(from_verified_assurance_cycle(_read_json(Path(args.g35_cycle)), repository))
    view = combine_views(*views) if len(views) > 1 else views[0]
    snapshot = view.snapshot()
    result = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output).absolute()
        if output.is_symlink() or any(p.is_symlink() for p in output.parents):
            raise GraphDomainError("Unsafe output path")
        if output == repository or repository in output.parents:
            raise GraphDomainError("Refusing to write graph snapshot into repository")
        if not output.parent.is_dir() or output.exists():
            raise GraphDomainError("Output parent must exist and destination must be new")
        output.write_text(result, encoding="utf-8", errors="strict")
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GraphDomainError, FileNotFoundError, OSError) as exc:
        print(f"GE-01 projection rejected: {exc}", file=sys.stderr)
        sys.exit(2)
