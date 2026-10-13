"""RI-04: bounded, source-bound RDF evidence dossier across GE-04/G7.3.

The authoritative inputs are independently verified GE and G7 reports plus
the canonical G4 RDF projection; an RDF query result cannot authorize action.
No arbitrary SPARQL, remote contexts or writes to the source repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.graph import rdflib_query_layer as ri01
from audit_engine.semantic_audit.graph import rdflib_scientific_index as ri02
from audit_engine.semantic_audit.graph import rdflib_provenance_audit as ri03
from audit_engine.semantic_audit.graph import section_impact_integration as ge04
from audit_engine.semantic_audit.graph import reasoning_document_review as g73
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical

SCHEMA = "ri04-scientific-evidence-review/v1"
MAX_ITEMS = 128
MAX_EVIDENCE = 512
MAX_BYTES = 5_000_000
APPROVAL = {"scientific_truth_established": False,
            "automatic_approval_permitted": False,
            "automatic_document_modification_permitted": False,
            "authoritative_graph_mutation_permitted": False}

class RI04Error(ValueError):
    """Unsafe inputs, source mismatch or unverifiable scientific review dossier."""

def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _args(*, mode: str, knowledge_graph: str | None, document_path: str,
          section_bindings: str | None, inference_bindings: str | None) -> dict:
    if mode not in ("candidate", "latest-transition"):
        raise RI04Error("Invalid graph comparison mode")
    if mode == "candidate" and not knowledge_graph:
        raise RI04Error("Candidate graph required")
    if mode == "latest-transition" and knowledge_graph is not None:
        raise RI04Error("Historical comparison forbids a candidate")
    if not isinstance(document_path, str) or not document_path:
        raise RI04Error("Document path required")
    if not section_bindings and not inference_bindings:
        raise RI04Error("At least one explicit version-bound mapping required")
    return dict(mode=mode, knowledge_graph=knowledge_graph,
                document_path=document_path, section_bindings=section_bindings,
                inference_bindings=inference_bindings)

def build_dossier(repository: Path, *, mode: str, knowledge_graph: str | None,
                  document_path: str, section_bindings: str | None = None,
                  inference_bindings: str | None = None, per_entity_limit: int = 12) -> tuple[dict, bytes]:
    _args(mode=mode, knowledge_graph=knowledge_graph, document_path=document_path,
          section_bindings=section_bindings, inference_bindings=inference_bindings)
    if type(per_entity_limit) is not int or not 1 <= per_entity_limit <= 20:
        raise RI04Error("Per-entity query limit must be from 1 to 20")
    repo = Path(repository).resolve(strict=True)
    section = (ge04.plan(repo, document_path=document_path, bindings_path=section_bindings,
                         mode=mode, knowledge_graph=knowledge_graph)
               if section_bindings else None)
    inference = (g73.plan(repo, document_path=document_path, bindings_path=inference_bindings,
                          mode=mode, knowledge_graph=knowledge_graph)
                 if inference_bindings else None)
    if section and inference:
        if (section["document_sha256"] != inference["document_sha256"] or
            section["graph_store_head_sha256"] != inference["graph_store_head_sha256"] or
            section["compared_snapshot_sha256"] != inference["after_snapshot_sha256"]):
            raise RI04Error("GE and G7 reports are not bound to the same source versions")
    view, store = ri01.resolve_view(repo, mode=("candidate" if mode=="candidate" else "persisted"),
                                    knowledge_graph=knowledge_graph)
    index = ri02.build_scientific_index(view, store_state=store)
    consistency = ri03.audit_index(index)
    ids: set[str] = set()
    sections: dict[str, dict] = {}
    if section:
        for task in section["section_review_tasks"]:
            sections.setdefault(task["section_id"], {"title":task["title"],"triggers":[]})
            sections[task["section_id"]]["triggers"].append({
                "kind":"graph_dependency", "nodes":[r["graph_node_id"] for r in task["triggers"]]})
            ids.update(r["graph_node_id"] for r in task["triggers"])
    if inference:
        for task in inference["section_review_tasks"]:
            sections.setdefault(task["section_id"], {"title":task["title"],"triggers":[]})
            for trigger in task["triggers"]:
                fact = trigger["fact"]
                sections[task["section_id"]]["triggers"].append({
                    "kind":"reasoning_"+trigger["event_kind"],"fact":fact,
                    "before_witness_sha256":trigger["before_witness_sha256"],
                    "after_witness_sha256":trigger["after_witness_sha256"]})
                ids.add(fact["source_id"])
                ids.add(fact["target_id"])
    if len(ids)>MAX_ITEMS or len(sections)>MAX_ITEMS:
        raise RI04Error("Scientific dossier entity budget exceeded")
    # All IDs originate in independently verified GE/G7 reports; no invented links.
    known={node.node_id for node in view.graph.nodes}
    evidence=[]
    for ident in sorted(ids):
        if ident not in known:
            # A G7 retraction may refer to an entity that disappeared from the
            # proposed snapshot. Never claim that it has post-change citations.
            evidence.append({"node_id":ident,"status":"absent_from_current_graph",
                             "citations":[],"evidence_paths":[]})
            continue
        try:
            citations=ri03.provenance_query(index,"sources_for_proposition",ident,per_entity_limit)
            paths=ri03.provenance_query(index,"concept_evidence_paths",ident,per_entity_limit)
        except (ri03.ProvenanceAuditError,ri01.RDFQueryLayerError) as exc:
            raise RI04Error("Source-bound RDF evidence query failed") from exc
        evidence.append({"node_id":ident,"status":"recorded_relationships_only",
                         "citations":citations,"evidence_paths":paths})
    if sum(len(row["citations"])+len(row["evidence_paths"]) for row in evidence)>MAX_EVIDENCE:
        raise RI04Error("Evidence row budget exceeded")
    normalized_sections=[{"section_id":sid,"title":record["title"],
                          "triggers":record["triggers"]} for sid,record in sorted(sections.items())]
    if len(normalized_sections)>MAX_ITEMS:
        raise RI04Error("Too many document sections")
    review_status=("human_review_required" if normalized_sections else
                   "blocked_no_explicit_mapping")
    report={
        "schema_version":SCHEMA,"status":review_status,
        "mode":mode,"document_path":document_path,
        "document_sha256":section["document_sha256"] if section else inference["document_sha256"],
        "ge04_report_sha256":section["report_sha256"] if section else None,
        "g73_report_sha256":inference["report_sha256"] if inference else None,
        "unmapped_graph_nodes":section["unmapped_graph_node_ids"] if section else [],
        "unmapped_inference_events":inference["unmapped_inference_events"] if inference else [],
        "graph_snapshot_sha256":view.snapshot()["snapshot_sha256"],
        "graph_fingerprint":view.fingerprint,
        "g4_manifest_sha256":index.base.g4_manifest["manifest_sha256"],
        "ri02_nquads_sha256":_sha(index.nquads),
        "ri03_consistency":consistency,
        "sections":normalized_sections,
        "evidence":evidence,
        "query_semantics":"Recorded citation structure; absence is not negative scientific evidence",
        "authority":dict(APPROVAL),
    }
    raw=canonical(report)
    if len(raw)>MAX_BYTES: raise RI04Error("Dossier exceeds maximum bytes")
    report["report_sha256"]=_sha(raw)
    return report,index.nquads

def verify_dossier(repository: Path, report: dict, nquads: bytes, **kwargs) -> dict:
    expected, expected_quads=build_dossier(repository,**kwargs)
    if not isinstance(report,dict) or report!=expected or nquads!=expected_quads:
        raise RI04Error("Dossier differs from independently replayed source")
    return {"status":"verified","report_sha256":expected["report_sha256"],
            "section_count":len(expected["sections"]),"entity_count":len(expected["evidence"])}

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="RI-04 source-bound RDF scientific dossier")
    p.add_argument("action",choices=("run","verify"))
    p.add_argument("--repository",required=True)
    p.add_argument("--mode",choices=("candidate","latest-transition"),default="candidate")
    p.add_argument("--knowledge-graph")
    p.add_argument("--document",required=True)
    p.add_argument("--section-bindings")
    p.add_argument("--inference-bindings")
    p.add_argument("--limit",type=int,default=12)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args(argv)
    args=dict(mode=a.mode,knowledge_graph=a.knowledge_graph,document_path=a.document,
              section_bindings=a.section_bindings,inference_bindings=a.inference_bindings,
              per_entity_limit=a.limit)
    root=Path(a.output_dir)
    repo=Path(a.repository)
    if a.action=="run":
        report,raw=build_dossier(repo,**args)
        target=ri01._safe_output(root,repo)
        target.mkdir(mode=0o700)
        ri01._new_file(target/"ri04-dossier.json",canonical(report))
        ri01._new_file(target/"ri04-source-dataset.nq",raw)
        result={"status":report["status"],"report_sha256":report["report_sha256"]}
    else:
        report=json.loads(ri01._read(root/"ri04-dossier.json",MAX_BYTES))
        raw=ri01._read(root/"ri04-source-dataset.nq",ri01.MAX_BYTES)
        result=verify_dossier(repo,report,raw,**args)
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except (RI04Error,ValueError,OSError,KeyError,TypeError) as e:
        import sys
        print("RI-04 rejected:",e,file=sys.stderr)
        raise SystemExit(2)
