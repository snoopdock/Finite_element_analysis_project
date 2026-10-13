"""RI-04 independent RDF parser parity and bounded seeded performance campaign.

RDFLib is the producer. Oxigraph (optional native Rust extension) parses the
detached N-Quads independently. Neither parser proves scientific validity.
Performance observations cannot be reproduced cryptographically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import median
from time import perf_counter_ns
import tracemalloc
from uuid import UUID

from rdflib import Dataset, URIRef, Literal
from rdflib.namespace import XSD

from audit_engine.semantic_audit.graph import rdflib_query_layer as ri01
from audit_engine.semantic_audit.graph import rdflib_scientific_index as ri02
from audit_engine.semantic_audit.graph import rdflib_provenance_audit as ri03
from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical

SCHEMA="ri04-performance-and-interoperability/v1"
MAX_DATA_BYTES=ri01.MAX_BYTES
MAX_BENCHMARK_NS=300_000_000_000
MAX_CAMPAIGN_BYTES=2_000_000
MAX_CASES=16
AUTHORITY={"scientific_truth_established":False,"automatic_backend_selection_permitted":False,
           "automatic_approval_permitted":False,"authoritative_graph_mutation_permitted":False}

class CampaignError(ValueError):
    pass

def _h(raw):
    return hashlib.sha256(raw).hexdigest()

def _rdflib_term(term):
    if isinstance(term,URIRef): return ("IRI",str(term))
    if isinstance(term,Literal): return ("Literal",str(term),str(term.datatype or XSD.string) if not term.language else str(term.datatype or "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString"),term.language or "")
    raise CampaignError("Unexpected RDFLib term")

def _ox_term(term):
    import pyoxigraph as ox
    if isinstance(term,ox.NamedNode): return ("IRI",term.value)
    if isinstance(term,ox.Literal):
        return ("Literal",term.value,term.datatype.value if term.datatype else "",term.language or "")
    raise CampaignError("Oxigraph returned unexpected term")

def cross_parser_parity(nquads: bytes, *, require_oxigraph: bool=True) -> dict:
    if not isinstance(nquads,bytes) or not nquads or len(nquads)>MAX_DATA_BYTES:
        raise CampaignError("Invalid/budget-exceeded detached N-Quads")
    rd=Dataset(default_union=False)
    try:
        rd.parse(data=nquads.decode("utf-8","strict"),format="nquads")
    except Exception as exc:
        raise CampaignError("RDFLib parser rejected N-Quads") from exc
    left=set()
    for s,p,o,g in rd.quads((None,None,None,None)):
        if not isinstance(g,URIRef) or g==rd.default_graph.identifier:
            raise CampaignError("N-Quads must use explicit named graph IRIs")
        left.add((_rdflib_term(s),_rdflib_term(p),_rdflib_term(o),_rdflib_term(g)))
    if not left:
        raise CampaignError("Detached N-Quads must contain at least one named-graph quad")
    if len(left)>ri01.MAX_QUADS:
        raise CampaignError("Quad budget exceeded")
    try:
        import pyoxigraph as ox
    except ImportError:
        if require_oxigraph:
            raise CampaignError("Native independent parser pyoxigraph is required")
        return {"status":"rdflib_only_no_independent_parser","quad_count":len(left),
                "rdf_sha256":_h(nquads),"independently_verified":False}
    try:
        right=set()
        for q in ox.parse(input=nquads,format=ox.RdfFormat.N_QUADS):
            right.add((_ox_term(q.subject),_ox_term(q.predicate),
                       _ox_term(q.object),_ox_term(q.graph_name)))
            if len(right)>ri01.MAX_QUADS:
                raise CampaignError("Independent parser quad budget exceeded")
    except Exception as exc:
        raise CampaignError("Oxigraph rejected N-Quads") from exc
    if left!=right:
        raise CampaignError("RDFLib and Oxigraph disagree on semantic quad identities")
    return {"status":"independently_verified","quad_count":len(left),
            "rdf_sha256":_h(nquads),"independently_verified":True}

def make_case(*, concepts: int, seed: int) -> dict:
    if type(concepts) is not int or not 4<=concepts<=1024:
        raise CampaignError("Synthetic graph size out of bounds")
    if type(seed) is not int or not 0<=seed<2**31:
        raise CampaignError("Invalid benchmark seed")
    rng=random.Random(seed)
    def uuid(i): return str(UUID(int=i+1))
    cs={}
    props={}
    relations={}
    for i in range(concepts):
        ref=uuid(i)
        parents=([uuid(rng.randrange(i))] if i else [])
        cs[ref]={"concept_id":ref,"name":f"FEM benchmark concept {i}",
                 "type":"concept","status":"proposed","source_ids":[f"bench:{seed}:{i%5}"],
                 "parent_concept_ids":parents}
    for j in range(max(1,concepts//2)):
        ref=uuid(1000+j)
        targets=[uuid(rng.randrange(concepts)) for _ in range(1+(j%3))]
        props[ref]={"proposition_id":ref,"statement":f"Unverified FE proposition {j}",
                    "status":"proposed","concept_ids":sorted(set(targets)),
                    "source_ids":[f"bench:{seed}:{j%5}"]}
    # Deliberate repeated endpoints (but distinct relationship UUIDs)
    for j in range(max(2,concepts//3)):
        ref=uuid(2000+j)
        relations[ref]={"relationship_id":ref,"source_id":uuid(j%concepts),
                        "target_id":uuid((j+1)%concepts),"type":"relates_unverified",
                        "status":"proposed","proposition_ids":[],"source_ids":[]}
    return {"concepts":cs,"propositions":props,"relationships":relations}

def _measure(fn, repeats):
    samples=[]
    peak=[]
    for _ in range(repeats):
        tracemalloc.start()
        start=perf_counter_ns()
        try:
            fn()
            elapsed=perf_counter_ns()-start
            _,high=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        if not 0<=elapsed<=MAX_BENCHMARK_NS:
            raise CampaignError("Invalid wall-clock observation")
        samples.append(elapsed);peak.append(high)
    return {"samples_ns":samples,"median_ns":median(samples),
            "peak_traced_bytes":peak,"median_peak_traced_bytes":median(peak)}

def campaign(*, sizes: tuple[int,...], seeds: tuple[int,...], repeats: int=2,
             require_oxigraph: bool=True) -> dict:
    if (type(repeats) is not int or not 1<=repeats<=5 or
        not 1<=len(sizes)<=4 or not 1<=len(seeds)<=4 or
        len(sizes)*len(seeds)>MAX_CASES or len(set(sizes))!=len(sizes) or
        len(set(seeds))!=len(seeds)):
        raise CampaignError("Campaign exceeds bounded design")
    if any(type(x) is not int or not 4<=x<=1024 for x in sizes):
        raise CampaignError("Invalid benchmark graph sizes")
    if any(type(x) is not int or not 0<=x<2**31 for x in seeds):
        raise CampaignError("Invalid benchmark seed")
    cases=[]
    for size in sorted(sizes):
        for seed in sorted(seeds):
            graph_data=make_case(concepts=size,seed=seed)
            view=from_scientific_graph(graph_data)
            # Warm up the native G4/G4.6 and SPARQL parsers before measurement.
            index=ri02.build_scientific_index(view)
            consistency=ri03.audit_index(index)
            subject=next(n.node_id for n in view.graph.nodes if n.entity_type=="ScientificProposition")
            ri03.provenance_query(index,"sources_for_proposition",subject,limit=20)
            parity=cross_parser_parity(index.nquads,require_oxigraph=require_oxigraph)
            build=_measure(lambda:ri02.build_scientific_index(view),repeats)
            query=_measure(lambda:ri03._query(index,"sources_for_proposition",subject,20),repeats)
            parse=_measure(lambda:cross_parser_parity(index.nquads,require_oxigraph=require_oxigraph),repeats)
            cases.append({
                "size":size,"seed":seed,"synthetic_graph_sha256":_h(canonical(graph_data)),
                "source_snapshot_sha256":view.snapshot()["snapshot_sha256"],
                "nquads_sha256":_h(index.nquads),"quads":parity["quad_count"],
                "node_count":len(view.graph.nodes),"edge_count":len(view.graph.edges),
                "cross_parser":parity,"index_status":consistency["status"],
                "timings":{"build_index":build,"bounded_sparql":query,"parse_parity":parse},
            })
    core={"schema_version":SCHEMA,"cases":cases,"sizes":sorted(sizes),"seeds":sorted(seeds),
          "repeats":repeats,"case_count":len(cases),"authority":dict(AUTHORITY),
          "timing_interpretation":"Environment-dependent descriptive observations, not replayable speed proofs",
          "independent_parser_required":require_oxigraph}
    if len(canonical(core))>MAX_CAMPAIGN_BYTES: raise CampaignError("Campaign report too large")
    core["report_sha256"]=_h(canonical(core))
    return core

def verify_campaign(report, *, require_oxigraph=True):
    if not isinstance(report,dict) or report.get("schema_version")!=SCHEMA:
        raise CampaignError("Invalid campaign report")
    allowed={"schema_version","cases","sizes","seeds","repeats","case_count",
             "authority","timing_interpretation","independent_parser_required",
             "report_sha256"}
    if set(report)!=allowed:
        raise CampaignError("Unexpected campaign fields")
    original=report.get("report_sha256")
    if not isinstance(original,str) or original!=_h(canonical({k:v for k,v in report.items() if k!="report_sha256"})):
        raise CampaignError("Campaign digest mismatch")
    if report.get("authority")!=AUTHORITY or report.get("timing_interpretation")!="Environment-dependent descriptive observations, not replayable speed proofs":
        raise CampaignError("Campaign authority/interpretation altered")
    if report.get("independent_parser_required") is not require_oxigraph:
        raise CampaignError("Independent parser setting changed")
    cases=report.get("cases")
    sizes=report.get("sizes")
    seeds=report.get("seeds")
    if not isinstance(cases,list) or len(cases)>MAX_CASES or not isinstance(sizes,list) or not isinstance(seeds,list):
        raise CampaignError("Malformed benchmark campaign")
    repeats=report.get("repeats")
    if (type(repeats) is not int or not 1<=repeats<=5 or
        type(report.get("case_count")) is not int or report["case_count"]!=len(cases) or
        len(cases)!=len(sizes)*len(seeds) or len(set(sizes))!=len(sizes) or
        len(set(seeds))!=len(seeds)):
        raise CampaignError("Inconsistent campaign shape")
    keys=[(c["size"],c["seed"]) for c in cases]
    if keys!=sorted((size,seed) for size in sizes for seed in seeds):
        raise CampaignError("Unexpected campaign cases")
    for case in cases:
        if set(case)!={"size","seed","synthetic_graph_sha256","source_snapshot_sha256",
                      "nquads_sha256","quads","node_count","edge_count","cross_parser",
                      "index_status","timings"}:
            raise CampaignError("Unexpected benchmark case fields")
        view=from_scientific_graph(make_case(concepts=case["size"],seed=case["seed"]))
        index=ri02.build_scientific_index(view)
        check=cross_parser_parity(index.nquads,require_oxigraph=require_oxigraph)
        expected={"synthetic_graph_sha256":_h(canonical(make_case(concepts=case["size"],seed=case["seed"]))),
                  "source_snapshot_sha256":view.snapshot()["snapshot_sha256"],
                  "nquads_sha256":_h(index.nquads),"quads":check["quad_count"],
                  "node_count":len(view.graph.nodes),"edge_count":len(view.graph.edges),
                  "cross_parser":check,"index_status":ri03.audit_index(index)["status"]}
        if any(case.get(k)!=v for k,v in expected.items()):
            raise CampaignError("Source-bound synthetic graph or RDF parity changed")
        timings=case.get("timings")
        if not isinstance(timings,dict) or set(timings)!={"build_index","bounded_sparql","parse_parity"}:
            raise CampaignError("Missing benchmark observations")
        for item in timings.values():
            vals=item.get("samples_ns");peaks=item.get("peak_traced_bytes")
            if (not isinstance(vals,list) or len(vals)!=repeats or not isinstance(peaks,list) or len(peaks)!=repeats
                or any(type(v) is not int or not 0<=v<=MAX_BENCHMARK_NS for v in vals)
                or any(type(v) is not int or v<0 or v>2**40 for v in peaks)
                or item.get("median_ns")!=median(vals) or item.get("median_peak_traced_bytes")!=median(peaks)):
                raise CampaignError("Invalid benchmark statistics")
    return {"status":"verified","case_count":len(cases),"report_sha256":original,
            "timing_verified":"arithmetic_only"}

def main(argv=None):
    parser=argparse.ArgumentParser(description="RI-04 bounded seeded RDF interoperability campaign")
    parser.add_argument("action",choices=("run","verify"))
    parser.add_argument("--report",required=True)
    parser.add_argument("--sizes",default="12,36")
    parser.add_argument("--seeds",default="20261013,20261014")
    parser.add_argument("--repeats",type=int,default=2)
    args=parser.parse_args(argv)
    path=Path(args.report)
    if args.action=="run":
        if path.exists() or path.is_symlink() or not path.parent.is_dir():
            raise CampaignError("Campaign output must be a new file")
        report=campaign(sizes=tuple(int(x) for x in args.sizes.split(",")),
                        seeds=tuple(int(x) for x in args.seeds.split(",")),
                        repeats=args.repeats)
        ri01._new_file(path,canonical(report))
        output={"status":"created","report_sha256":report["report_sha256"],
                "case_count":report["case_count"]}
    else:
        data=json.loads(ri01._read(path,MAX_CAMPAIGN_BYTES))
        if ri01._read(path,MAX_CAMPAIGN_BYTES)!=canonical(data):
            raise CampaignError("Noncanonical detached benchmark report")
        output=verify_campaign(data)
    print(json.dumps(output,sort_keys=True))
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except (CampaignError,ValueError,TypeError,OSError,KeyError) as exc:
        import sys
        print("RI-04 rejected:",exc,file=sys.stderr)
        raise SystemExit(2)
