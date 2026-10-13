"""RI-04: source-bound integration, explicit review, parser parity, resource budgets."""
import copy
from pathlib import Path
import sys
import warnings

import pytest

from audit_engine.semantic_audit.graph import rdflib_production_integration as dossier
from audit_engine.semantic_audit.graph import rdflib_interoperability_campaign as perf
from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph
from audit_engine.semantic_audit.graph import rdflib_query_layer as ri01


def test_deterministic_synthetic_graph():
    x=perf.make_case(concepts=12,seed=17)
    assert x==perf.make_case(concepts=12,seed=17)
    assert x!=perf.make_case(concepts=12,seed=18)
    view=from_scientific_graph(x)
    assert len(view.graph.nodes)>12
    assert len(view.graph.edges)>12
    assert len(view.graph.nodes)==len({n.node_id for n in view.graph.nodes})
    assert sum(e.relation_type=="SCIENTIFIC_RELATION" for e in view.graph.edges)==4
    assert any(n.entity_type=="ScientificSourceRef" for n in view.graph.nodes)


@pytest.mark.parametrize("size,seed",[(0,10),(1025,10),(12,-1),(12,2**31),(True,1)])
def test_invalid_synthetic_input_rejected(size,seed):
    with pytest.raises(perf.CampaignError):
        perf.make_case(concepts=size,seed=seed)


@pytest.mark.parametrize("sizes,seeds,repeats",[
    ((12,12),(1,),2),((12,),(1,1),2),((4,),(1,),0),
    ((4,),(1,),6),((1,),(1,),2),((10,),(2**33,),2),
])
def test_invalid_campaign_parameters_rejected(sizes,seeds,repeats):
    with pytest.raises(perf.CampaignError):
        perf.campaign(sizes=sizes,seeds=seeds,repeats=repeats)


def test_rdflib_only_does_not_claim_independent_parser():
    x=perf.cross_parser_parity(b'<urn:s> <urn:p> "text" <urn:g> .\n',
                               require_oxigraph=False)
    assert x["quad_count"]==1
    if x["status"]=="rdflib_only_no_independent_parser":
        assert x["independently_verified"] is False
    else:
        assert x["independently_verified"] is True


@pytest.mark.parametrize("payload",[
    b"",b'garbage',b'<urn:s> <urn:p> "x" <urn:g> .\n_:', b'<urn:s> <urn:p> "x" .\n',
])
def test_malformed_or_unsafe_dataset_rejected(payload):
    with pytest.raises(perf.CampaignError):
        perf.cross_parser_parity(payload,require_oxigraph=False)


def test_disallow_untrusted_inference_approval_and_unmapped_inputs():
    for kwargs in [
        dict(mode="candidate",knowledge_graph=None,document_path="doc.json",
             section_bindings="sections.json",inference_bindings=None),
        dict(mode="latest-transition",knowledge_graph="bad.json",document_path="doc.json",
             section_bindings="sections.json",inference_bindings=None),
        dict(mode="candidate",knowledge_graph="candidate.json",document_path="doc.json",
             section_bindings=None,inference_bindings=None)
    ]:
        with pytest.raises(dossier.RI04Error):
            dossier._args(**kwargs)
    assert all(value is False for value in dossier.APPROVAL.values())


@pytest.mark.parametrize("limit",[0,21,100,True])
def test_dossier_bad_limits_fail_before_reading_sources(tmp_path,limit):
    with pytest.raises(dossier.RI04Error):
        dossier.build_dossier(tmp_path,mode="candidate",knowledge_graph="abc",
                              document_path="doc",section_bindings="sections",per_entity_limit=limit)


def test_rehash_cannot_forge_campaign_authority():
    report={"schema_version":perf.SCHEMA,"cases":[],"sizes":[12],"seeds":[17],
            "repeats":1,"case_count":0,"authority":dict(perf.AUTHORITY),
            "timing_interpretation":"Environment-dependent descriptive observations, not replayable speed proofs",
            "independent_parser_required":False}
    report["authority"]["automatic_approval_permitted"]=True
    report["report_sha256"]=perf._h(perf.canonical(report))
    with pytest.raises(perf.CampaignError):
        perf.verify_campaign(report,require_oxigraph=False)


def test_rehash_cannot_forge_replay_shape():
    report={"schema_version":perf.SCHEMA,"cases":[],"sizes":[12],"seeds":[17],
            "repeats":1,"case_count":0,"authority":dict(perf.AUTHORITY),
            "timing_interpretation":"Environment-dependent descriptive observations, not replayable speed proofs",
            "independent_parser_required":False}
    report["report_sha256"]=perf._h(perf.canonical(report))
    with pytest.raises(perf.CampaignError):
        perf.verify_campaign(report,require_oxigraph=False)


def test_real_g4_native_dataset_import_for_current_branch():
    pytest.importorskip("audit_engine.semantic_audit.graph.rdf_export")
    from audit_engine.semantic_audit.graph import rdflib_scientific_index as ri02
    repo=Path(__file__).resolve().parents[2]
    doc=repo/"examples/graph_engine/ge02_demo_graph.json"
    from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph
    import json
    view=from_scientific_graph(json.loads(doc.read_text()))
    index=ri02.build_scientific_index(view)
    result=perf.cross_parser_parity(index.nquads,require_oxigraph=False)
    assert result["quad_count"]>10
    assert index.base.g4_manifest["triple_count"]>20


def test_real_g4_native_campaign_replay_for_current_branch():
    pytest.importorskip("audit_engine.semantic_audit.graph.rdf_export")
    report=perf.campaign(sizes=(4,),seeds=(17,),repeats=1,require_oxigraph=False)
    assert report["case_count"]==1
    assert report["cases"][0]["edge_count"]>2
    assert perf.verify_campaign(report,require_oxigraph=False)["status"]=="verified"
    changed=copy.deepcopy(report)
    changed["cases"][0]["edge_count"]+=1
    changed["report_sha256"]=perf._h(perf.canonical({k:v for k,v in changed.items() if k!="report_sha256"}))
    with pytest.raises(perf.CampaignError):
        perf.verify_campaign(changed,require_oxigraph=False)


def test_native_oxigraph_parity_when_installed():
    pytest.importorskip("pyoxigraph")
    rdf=b'<urn:s> <urn:p> "one" <urn:g> .\n<urn:s> <urn:p> "two" <urn:g> .\n'
    result=perf.cross_parser_parity(rdf)
    assert result["independently_verified"] is True
    assert result["quad_count"]==2


def test_native_document_dossier_when_g4_available():
    pytest.importorskip("audit_engine.semantic_audit.graph.rdf_export")
    repo=Path(__file__).resolve().parents[2]
    report,quads=dossier.build_dossier(repo,mode="candidate",
          knowledge_graph="examples/graph_engine/g72_demo_reparented_graph.json",
          document_path="examples/graph_engine/ge04_demo_document.json",
          inference_bindings="examples/graph_engine/g73_demo_inference_section_bindings.json")
    assert len(report["sections"])==2
    assert report["status"]=="human_review_required"
    assert report["authority"]["automatic_approval_permitted"] is False
    assert dossier.verify_dossier(repo,report,quads,mode="candidate",
          knowledge_graph="examples/graph_engine/g72_demo_reparented_graph.json",
          document_path="examples/graph_engine/ge04_demo_document.json",
          inference_bindings="examples/graph_engine/g73_demo_inference_section_bindings.json")["status"]=="verified"
    modified=copy.deepcopy(report)
    modified["sections"][0]["title"]="forged"
    modified["report_sha256"]=dossier._sha(perf.canonical({k:v for k,v in modified.items() if k!="report_sha256"}))
    with pytest.raises(dossier.RI04Error):
        dossier.verify_dossier(repo,modified,quads,mode="candidate",
          knowledge_graph="examples/graph_engine/g72_demo_reparented_graph.json",
          document_path="examples/graph_engine/ge04_demo_document.json",
          inference_bindings="examples/graph_engine/g73_demo_inference_section_bindings.json")


def _mock_dossier_layers(monkeypatch, *, mismatch=False):
    from types import SimpleNamespace
    from audit_engine.semantic_audit.graph import rdflib_production_integration as m
    class Node:
        node_id="scientific:proposition:claim-1"
    class View:
        fingerprint="f"*64
        graph=SimpleNamespace(nodes=[Node()])
        def snapshot(self): return {"snapshot_sha256":"a"*64}
    class FakeIndex:
        nquads=b'<urn:a> <urn:b> "v" <urn:c> .\n'
        base=SimpleNamespace(g4_manifest={"manifest_sha256":"d"*64})
    monkeypatch.setattr(m.ri01,"resolve_view",lambda *a,**k:(View(),None))
    monkeypatch.setattr(m.ri02,"build_scientific_index",lambda *a,**k:FakeIndex())
    monkeypatch.setattr(m.ri03,"audit_index",lambda *a,**k:{"status":"consistent"})
    monkeypatch.setattr(m.ri03,"provenance_query",
        lambda index,query_id,argument,limit:[{"source":query_id,"value":argument,"limit":limit}])
    monkeypatch.setattr(m.ge04,"plan",lambda *a,**k:{
        "document_sha256":"b"*64, "graph_store_head_sha256":"c"*64,
        "compared_snapshot_sha256":"a"*64,"report_sha256":"e"*64,
        "unmapped_graph_node_ids":[],
        "section_review_tasks":[{"section_id":"sect1","title":"Assumptions",
            "triggers":[{"graph_node_id":"scientific:proposition:claim-1"}]}]})
    monkeypatch.setattr(m.g73,"plan",lambda *a,**k:{
        "document_sha256":"b"*64, "graph_store_head_sha256":"c"*64,
        "after_snapshot_sha256":("z"*64 if mismatch else "a"*64),
        "report_sha256":"f"*64,"unmapped_inference_events":[],
        "section_review_tasks":[{"section_id":"sect2","title":"Weak form",
            "triggers":[{"event_kind":"retracted",
                "fact":{"rule_id":"rule","source_id":"scientific:proposition:claim-1",
                        "inferred_relation":"HAS_ANCESTOR_CONCEPT","target_id":"no-longer-present"},
                "before_witness_sha256":"1"*64,"after_witness_sha256":None}]}]})
    return m

def test_dossier_cross_layer_join_and_missing_after_graph(monkeypatch,tmp_path):
    m=_mock_dossier_layers(monkeypatch)
    options=dict(mode="candidate",knowledge_graph="candidate.json",document_path="doc.json",
                 section_bindings="sections.json",inference_bindings="facts.json")
    report,nq=m.build_dossier(tmp_path,**options)
    assert report["status"]=="human_review_required"
    assert len(report["sections"])==2
    assert len(report["evidence"])==2
    assert any(e["status"]=="absent_from_current_graph" for e in report["evidence"])
    assert report["authority"]["automatic_approval_permitted"] is False
    assert m.verify_dossier(tmp_path,report,nq,**options)["status"]=="verified"
    forged=copy.deepcopy(report)
    forged["evidence"][0]["citations"]=[{"fake":"citation"}]
    forged["report_sha256"]=m._sha(perf.canonical({k:v for k,v in forged.items() if k!="report_sha256"}))
    with pytest.raises(m.RI04Error):
        m.verify_dossier(tmp_path,forged,nq,**options)
    with pytest.raises(m.RI04Error):
        m.verify_dossier(tmp_path,report,nq+b"altered",**options)

def test_dossier_rejects_misaligned_g7_and_ge_snapshots(monkeypatch,tmp_path):
    m=_mock_dossier_layers(monkeypatch,mismatch=True)
    with pytest.raises(m.RI04Error,match="same source"):
        m.build_dossier(tmp_path,mode="candidate",knowledge_graph="candidate.json",
                        document_path="doc.json",section_bindings="sections.json",
                        inference_bindings="facts.json")

def test_dossier_finite_query_budget_and_explicit_section(monkeypatch,tmp_path):
    m=_mock_dossier_layers(monkeypatch)
    report,nq=m.build_dossier(tmp_path,mode="candidate",knowledge_graph="candidate.json",
                document_path="doc.json",section_bindings="sections.json",per_entity_limit=2)
    assert len(report["sections"])==1
    assert report["evidence"][0]["citations"][0]["limit"]==2

def test_dossier_rejects_unsafe_query_argument_limits(monkeypatch,tmp_path):
    m=_mock_dossier_layers(monkeypatch)
    for limit in [-1,21,1.5,True]:
        with pytest.raises(m.RI04Error):
            m.build_dossier(tmp_path,mode="candidate",knowledge_graph="candidate.json",
                            document_path="doc.json",section_bindings="sections.json",
                            per_entity_limit=limit)

def test_self_rehashed_campaign_with_fake_count_is_rejected():
    report={"schema_version":perf.SCHEMA,"cases":[],"sizes":[12],"seeds":[17],
            "repeats":1,"case_count":1,"authority":dict(perf.AUTHORITY),
            "timing_interpretation":"Environment-dependent descriptive observations, not replayable speed proofs",
            "independent_parser_required":False}
    report["report_sha256"]=perf._h(perf.canonical(report))
    with pytest.raises(perf.CampaignError):
        perf.verify_campaign(report,require_oxigraph=False)

def test_literal_with_blank_node_looking_text_remains_valid():
    result=perf.cross_parser_parity(b'<urn:s> <urn:p> "hello _:not-a-node" <urn:g> .',
                                    require_oxigraph=False)
    assert result["quad_count"]==1
