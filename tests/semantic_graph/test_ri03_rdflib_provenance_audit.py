"""RI-03: provenance joins, source replay, RDF tampering, benchmark contracts."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import types

import pytest
from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical
from audit_engine.semantic_audit.graph import rdflib_scientific_index as ri02
from audit_engine.semantic_audit.graph import rdflib_query_layer as ri01
from audit_engine.semantic_audit.graph import rdflib_provenance_audit as ri03

@pytest.fixture
def view():
    g = SemanticGraph()
    g.add_node(SemanticNode('concept:parent', 'ScientificConcept',
                            {'name': 'Elasticity', 'status': 'proposed'},
                            {'original_id': 'uuid-parent'}))
    g.add_node(SemanticNode('concept:child', 'ScientificConcept',
                            {'name': 'Hooke law', 'status': 'draft'},
                            {'original_id': 'uuid-child'}))
    g.add_node(SemanticNode('prop:one', 'ScientificProposition',
                            {'statement': 'stress is proportional to strain',
                             'status': 'draft', 'framework': 'small strain'}, {}))
    g.add_node(SemanticNode('ref:one', 'ScientificSourceRef',
                            {'source_id_unverified': 'paper-1'}, {}))
    g.add_edge(SemanticEdge('concept:child','concept:parent','SUBCONCEPT_OF',{},{}))
    g.add_edge(SemanticEdge('prop:one','concept:child','HAS_CONCEPT',{},{}))
    g.add_edge(SemanticEdge('prop:one','ref:one','CITES_SOURCE',{},
                            {'source_verified': False}))
    g.add_edge(SemanticEdge('prop:one','ref:one','CITES_SOURCE',{},
                            {'source_verified': False}))
    g.add_edge(SemanticEdge('concept:child','prop:one','SCIENTIFIC_RELATION',
                            {'claimed_relation_type': 'supports','status_unverified':'proposed',
                             'weight': 0.5},
                            {'relationship_id':'rel:one','scientific_support_verified':False}))
    g.add_edge(SemanticEdge('prop:one','prop:one','SELF',{},{}))
    return GraphDomainView(g,'scientific_knowledge','e'*64)


@pytest.fixture
def g4_contract(monkeypatch):
    module = 'audit_engine.semantic_audit.graph.'
    fake = types.ModuleType(module+'rdf_export')
    fake.NS = 'urn:fea:semantic-graph:v1:'

    def emit(view, *, store_state=None):
        g = Graph()
        snap = ri01._uri('snapshot',view.fingerprint)
        g.add((snap,ri01._uri('property','domain'),Literal(view.domain)))
        for n in view.graph.nodes:
            u = ri01._uri('node',n.node_id)
            g.add((snap,ri01._uri('property','containsNode'),u))
            g.add((u,ri01._uri('property','nodeIdentifier'),Literal(n.node_id)))
            g.add((u,ri01._uri('property','entityType'),Literal(n.entity_type)))
        occurrences = {}
        for idx,e in enumerate(view.graph.edges):
            signature=(e.source_id,e.target_id,e.relation_type)
            occ=occurrences.get(signature,0);occurrences[signature]=occ+1
            stmt=ri01._uri('edge',f'{idx}:{occ}')
            g.add((snap,ri01._uri('property','containsEdge'),stmt))
            g.add((stmt,RDF.type,RDF.Statement))
            g.add((stmt,RDF.subject,ri01._uri('node',e.source_id)))
            g.add((stmt,RDF.object,ri01._uri('node',e.target_id)))
            g.add((stmt,ri01._uri('property','relationType'),Literal(e.relation_type)))
            g.add((stmt,ri01._uri('property','parallelEdgeOccurrence'),
                   Literal(occ,datatype=XSD.nonNegativeInteger)))
            for key,value in [('attributesJson',e.attributes),('metadataJson',e.metadata)]:
                g.add((stmt,ri01._uri('property',key),Literal(canonical(value).decode().strip())))
        raw=g.serialize(format='nt').encode()
        return {'ntriples':raw,'manifest':{'manifest_sha256':hashlib.sha256(raw).hexdigest()}}

    fake.export_view=emit
    fake2=types.ModuleType(module+'rdf_interoperability')
    fake2._read_rdf=lambda bundle:Graph().parse(data=bundle['ntriples'],format='nt')
    fake2.verify_rdf_interoperability=lambda v,b,store_state=None:{'triple_count':len(fake2._read_rdf(b))}
    monkeypatch.setitem(sys.modules,module+'rdf_export',fake)
    monkeypatch.setitem(sys.modules,module+'rdf_interoperability',fake2)
    return fake,fake2


@pytest.fixture
def index(view,g4_contract):
    return ri02.build_scientific_index(view)




def test_consistency_audit_real_source_counts(index):
    r=ri03.audit_index(index)
    assert r['status']=='consistent'
    assert r['node_count']==4
    assert r['edge_occurrence_count']==6
    assert r['named_graph_count']==5
    assert r['relation_occurrence_counts']['CITES_SOURCE']==2
    assert r['node_type_counts']['ScientificConcept']==2
    assert r['explicit_scientific_support_false_count']==1
    assert r['g4_manifest_sha256']==index.base.g4_manifest['manifest_sha256']


@pytest.mark.parametrize('query,arg,expected', [
    ('sources_for_proposition','prop:one',2),
    ('sources_for_proposition','concept:child',0),
    ('propositions_citing_source','ref:one',2),
    ('propositions_citing_source','prop:one',0),
    ('concept_evidence_paths','concept:child',2),
    ('concept_evidence_paths','concept:parent',0),
    ('relations_with_unverified_support','concept:child',1),
    ('relations_with_unverified_support','prop:one',0),
])
def test_bounded_provenance_query(index,query,arg,expected):
    assert len(ri03.provenance_query(index,query,arg))==expected


def test_multiple_citation_occurrences_stay_distinct(index):
    rows=ri03.provenance_query(index,'sources_for_proposition','prop:one')
    assert len({r['citation']['value'] for r in rows})==2
    assert {r['sourceRef']['value'] for r in rows}=={str(ri01._uri('node','ref:one'))}
    assert len({r['occurrence']['value'] for r in rows})==2


def test_join_source_and_concept_multiplicity(index):
    rows=ri03.provenance_query(index,'concept_evidence_paths','concept:child')
    assert len(rows)==2
    assert {r['proposition']['value'] for r in rows}=={str(ri01._uri('node','prop:one'))}
    assert len({r['citation']['value'] for r in rows})==2


@pytest.mark.parametrize('query,arg,limit', [
    ('SELECT * WHERE { ?s ?p ?o }','prop:one',2),
    ('sources_for_proposition','',2),
    ('sources_for_proposition','foo',0),
    ('sources_for_proposition','foo',101),
    ('sources_for_proposition','foo',True),
    ('DELETE WHERE { ?s ?p ?o }','foo',2),
    ('concept_evidence_paths','x'*5000,1),
])
def test_unsafe_query_fails_closed(index,query,arg,limit):
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.provenance_query(index,query,arg,limit)


def test_provenance_sparql_injection_as_literal_id(index):
    assert ri03.provenance_query(index,'sources_for_proposition',
                                'prop:one} SERVICE <https://invalid.example>')==[]


def test_extra_index_triple_rejected(index):
    index.dataset.graph(index.contexts[3]).add((ri01._uri('node','concept:parent'),
                   ri02._indexed('conceptName'),Literal('FORGED')))
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.audit_index(index)


def test_missing_index_triple_rejected(index):
    idx=index.dataset.graph(index.contexts[3])
    idx.remove((ri01._uri('node','concept:parent'),ri02._indexed('conceptName'),None))
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.audit_index(index)


def test_modified_g4_occurrence_rejected(index):
    graph=index.dataset.graph(index.contexts[0])
    stmt=next(graph.objects(ri01._uri('snapshot',index.base.source_view.fingerprint),
                            ri01._uri('property','containsEdge')))
    graph.remove((stmt,ri01._uri('property','parallelEdgeOccurrence'),None))
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.audit_index(index)


def test_changed_provenance_authority_flag_rejected(index):
    graph=index.dataset.graph(index.contexts[2])
    graph.remove((None,ri01._uri('query-provenance','automatic_approval_permitted'),None))
    subject=ri01._uri('query-view',index.base.source_view.snapshot()['snapshot_sha256'])
    graph.add((subject,ri01._uri('query-provenance','automatic_approval_permitted'),
               Literal(True,datatype=XSD.boolean)))
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.audit_index(index)


def test_orphan_index_record_rejected(index):
    index.dataset.graph(index.contexts[3]).add((ri01._uri('node','forged'),
                            ri02._indexed('conceptName'),Literal('forged')))
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.audit_index(index)


def test_benchmark_replay_and_readonly(view,g4_contract,tmp_path,monkeypatch):
    original=copy.deepcopy(view.graph.to_dict())
    monkeypatch.setattr(ri01,'resolve_view',lambda *args,**kw:(view,None))
    src=tmp_path/'repo';src.mkdir()
    output=tmp_path/'artifact'
    args=dict(mode='candidate',knowledge_graph='ignored.json',
              query_id='concept_evidence_paths',argument='concept:child',limit=25,repeats=2)
    report,raw=ri03.build_report(src,**args)
    assert report['result_count']==2
    assert len(report['benchmark']['measurements']['build_index']['samples_ns'])==2
    assert all(report[name] is False for name in ri03.LIMITATIONS)
    ri03.write_report(output,src,report,raw)
    assert ri03.verify_report(output,src,**args)==report
    assert view.graph.to_dict()==original
    assert (output/'ri03-scientific-dataset.nq').read_bytes()==raw
    assert (output/'ri03-audit-report.json').read_bytes()==canonical(report)


def test_report_query_result_tampering_even_when_rehashed(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *args,**kw:(view,None))
    src=tmp_path/'repo';src.mkdir(); output=tmp_path/'art'
    kw=dict(mode='candidate',knowledge_graph='x',query_id='sources_for_proposition',
            argument='prop:one',repeats=1)
    report,raw=ri03.build_report(src,**kw)
    ri03.write_report(output,src,report,raw)
    changed=copy.deepcopy(report)
    changed['results']=[]
    changed['result_count']=0
    changed['report_sha256']=hashlib.sha256(canonical({k:v for k,v in changed.items()
                                                        if k!='report_sha256'})).hexdigest()
    (output/'ri03-audit-report.json').write_bytes(canonical(changed))
    with pytest.raises(ri03.ProvenanceAuditError,match='source replay'):
        ri03.verify_report(output,src,**kw)


def test_benchmark_summary_tampering_rejected(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *args,**kw:(view,None))
    src=tmp_path/'repo';src.mkdir(); output=tmp_path/'art'
    kw=dict(mode='candidate',knowledge_graph='x',query_id='sources_for_proposition',
            argument='prop:one',repeats=2)
    report,raw=ri03.build_report(src,**kw)
    ri03.write_report(output,src,report,raw)
    changed=copy.deepcopy(report)
    changed['benchmark']['measurements']['build_index']['median_ns']+=1
    changed['report_sha256']=hashlib.sha256(canonical({k:v for k,v in changed.items()
                                                        if k!='report_sha256'})).hexdigest()
    (output/'ri03-audit-report.json').write_bytes(canonical(changed))
    with pytest.raises(ri03.ProvenanceAuditError,match='Timing statistics'):
        ri03.verify_report(output,src,**kw)


def test_nquads_tampering_rejected(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *args,**kw:(view,None))
    src=tmp_path/'repo';src.mkdir(); output=tmp_path/'art'
    kw=dict(mode='candidate',knowledge_graph='x',query_id='sources_for_proposition',
            argument='prop:one',repeats=1)
    report,raw=ri03.build_report(src,**kw)
    ri03.write_report(output,src,report,raw)
    (output/'ri03-scientific-dataset.nq').write_bytes(raw+b'\n')
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.verify_report(output,src,**kw)


@pytest.mark.parametrize('repeats', [0,8,True])
def test_reject_invalid_benchmark_repeats(view,g4_contract,tmp_path,monkeypatch,repeats):
    monkeypatch.setattr(ri01,'resolve_view',lambda *args,**kw:(view,None))
    with pytest.raises(ri03.ProvenanceAuditError):
        ri03.build_report(tmp_path,mode='candidate',knowledge_graph='x',
                          query_id='sources_for_proposition',argument='prop:one',repeats=repeats)


def test_existing_output_directory_not_overwritten(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *args,**kw:(view,None))
    src=tmp_path/'repo';src.mkdir(); output=tmp_path/'art';output.mkdir()
    report,raw=ri03.build_report(src,mode='candidate',knowledge_graph='x',
                     query_id='sources_for_proposition',argument='prop:one',repeats=1)
    with pytest.raises(ri01.RDFQueryLayerError):
        ri03.write_report(output,src,report,raw)


def test_native_g4_real_integration_if_available():
    from importlib.util import find_spec
    if find_spec('audit_engine.semantic_audit.graph.rdf_export') is None:
        pytest.skip('Older local snapshot lacks G4 exporter; GitHub current branch must run it')
    from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph
    import uuid
    c1=str(uuid.UUID('00000000-0000-4000-8000-000000000001'))
    c2=str(uuid.UUID('00000000-0000-4000-8000-000000000002'))
    graph={'concepts':{c1:{'concept_id':c1,'name':'Root','parent_concept_ids':[],
                            'source_ids':[],'type':'physics','status':'proposed'},
                       c2:{'concept_id':c2,'name':'Child','parent_concept_ids':[c1],
                            'source_ids':[],'type':'physics','status':'proposed'}},
           'propositions':{},'relationships':{}}
    index=ri02.build_scientific_index(from_scientific_graph(graph))
    assert ri03.audit_index(index)['node_count']==2


def test_real_ge02_persisted_store_source_readonly(g4_contract):
    """Exercise the real committed GE-02 state under the local G4 fixture."""
    repository = Path(__file__).resolve().parents[2]
    if not (repository / '.graph-state/scientific/HEAD.json').exists():
        pytest.skip('No persisted GE-02 HEAD available in this environment')
    from audit_engine.semantic_audit.graph.persistent_domain_state import PersistentDomainGraphStore
    store = PersistentDomainGraphStore(repository / '.graph-state/scientific')
    assert store.verify()['status'] == 'verified'
    view, state = ri01.resolve_view(repository, mode='persisted')
    before = copy.deepcopy(view.graph.to_dict())
    idx = ri02.build_scientific_index(view, store_state=state)
    result = ri03.audit_index(idx)
    assert result['node_count'] == len(view.graph.nodes)
    assert result['edge_occurrence_count'] == len(view.graph.edges)
    assert result['source_graph_fingerprint'] == view.fingerprint
    assert view.graph.to_dict() == before
