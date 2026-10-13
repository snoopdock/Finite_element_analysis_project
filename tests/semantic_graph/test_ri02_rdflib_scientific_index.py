"""RI-02 native scientific RDF projections, query semantics, and audit boundaries.

The local fake G4 projection exercises the RI-02 contract on October 13 ZIPs,
which predate G4.5. A separately marked test uses actual G4.5/4.6 modules on
current GitHub, with no monkeypatching of the real source verifier.
"""
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
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical, GraphStoreError
from audit_engine.semantic_audit.graph import rdflib_scientific_index as mod
from audit_engine.semantic_audit.graph import rdflib_query_layer as ri01


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
    return mod.build_scientific_index(view)


def test_dataset_has_five_named_contexts(index):
    assert len(set(index.contexts))==5
    assert all(len(index.dataset.graph(u)) for u in index.contexts)


def test_ri01_assertions_unmodified(index):
    assert set(index.dataset.graph(index.contexts[0])) == set(index.base.dataset.graph(index.base.asserted_context))
    assert set(index.dataset.graph(index.contexts[1])) == set(index.base.dataset.graph(index.base.fields_context))
    assert set(index.dataset.graph(index.contexts[2])) == set(index.base.dataset.graph(index.base.provenance_context))
    assert ri01._nq(index.base.dataset,index.contexts[:3])==index.base.nquads


def test_indexed_scientific_vocabulary(index):
    science=index.dataset.graph(index.contexts[3])
    concept=ri01._uri('node','concept:child')
    assert (concept,mod._indexed('conceptName'),Literal('Hooke law',datatype=XSD.string)) in science
    assert (concept,mod._indexed('originalUUID'),Literal('uuid-child',datatype=XSD.string)) in science
    assert (concept,mod._indexed('reviewStatusUnverified'),Literal('draft',datatype=XSD.string)) in science


def test_vocabulary_is_explicit_and_non_authoritative(index):
    vocabulary=index.dataset.graph(index.contexts[4])
    for key in ('conceptName','propositionStatement','claimedRelationTypeUnverified',
                'reviewStatusUnverified'):
        assert (mod._indexed(key),RDF.type,RDF.Property) in vocabulary
    assert (ri01._uri('ri02-vocabulary',mod.SCHEMA),
            mod._indexed('doesNotEstablishTruth'),Literal(True,datatype=XSD.boolean)) in vocabulary


def test_parallel_edges_have_distinct_index_subjects(index):
    raw=index.dataset.graph(index.contexts[0])
    statements=[s for s in raw.objects(ri01._uri('snapshot',index.base.source_view.fingerprint),
                                       mod._property('containsEdge'))
                if (s,RDF.subject,ri01._uri('node','prop:one')) in raw
                and (s,RDF.object,ri01._uri('node','ref:one')) in raw]
    assert len(statements)==2 and len(set(statements))==2
    meta=index.dataset.graph(index.contexts[3])
    assert all((stmt,mod._indexed('edgeSourceVerifiedFlag'),
                Literal(False,datatype=XSD.boolean)) in meta for stmt in statements)


def test_source_immutable(view,g4_contract):
    before=copy.deepcopy(view.graph.to_dict())
    mod.build_scientific_index(view)
    assert view.graph.to_dict()==before


@pytest.mark.parametrize('query,arg,count',[
    ('concepts_by_status','draft',1),
    ('concepts_by_status','proposed',1),
    ('concepts_by_status','nonexistent',0),
    ('propositions_for_concept','concept:child',1),
    ('propositions_for_concept','concept:parent',0),
    ('citations_for_entity','prop:one',2),
    ('citations_for_entity','concept:child',0),
    ('subconcepts_of','concept:parent',1),
    ('subconcepts_of','concept:child',0),
    ('relations_for_entity','prop:one',4),
    ('edges_by_claimed_type','supports',1),
    ('edges_by_claimed_type','refutes',0),
    ('nodes_by_indexed_field','name',2),
    ('nodes_by_indexed_field','statement',1),
    ('nodes_by_indexed_field','source_id_unverified',1),
])
def test_semantic_catalog_query_cardinality(index,query,arg,count):
    assert len(index.query(query,arg))==count


def test_proposition_query_joins_edge_occurrences(index):
    row=index.query('propositions_for_concept','concept:child')[0]
    assert row['source']['value']==str(ri01._uri('node','prop:one'))
    assert row['target']['value']==str(ri01._uri('node','concept:child'))
    assert row['statement']['type']=='iri'


def test_query_order_deterministic(index):
    assert index.query('citations_for_entity','prop:one')==index.query('citations_for_entity','prop:one')


def test_query_limit_is_enforced(index):
    assert len(index.query('citations_for_entity','prop:one',1))==1


@pytest.mark.parametrize('query,arg,limit',[
    ('SELECT * WHERE { ?s ?p ?o }','x',2),
    ('DELETE WHERE { ?s ?p ?o }','x',2),
    ('SERVICE <https://bad.invalid>','x',2),
    ('relations_for_entity','',2),
    ('relations_for_entity','x',0),
    ('relations_for_entity','x',201),
    ('relations_for_entity','x',True),
    ('nodes_by_indexed_field','metadataJson',2),
    ('nodes_by_indexed_field','a} SERVICE <https://bad.invalid>',2),
])
def test_untrusted_catalog_request_rejected(index,query,arg,limit):
    with pytest.raises(mod.ScientificIndexError):
        index.query(query,arg,limit)


def test_sparql_argument_is_bound_not_interpolated(index):
    assert index.query('propositions_for_concept','concept:child} UNION { ?s ?p ?o')==[]
    assert index.query('edges_by_claimed_type','supports" . ?s ?p ?o')==[]


def test_flattened_edge_scalar_has_distinct_types(index):
    idx=index.dataset.graph(index.contexts[3])
    statements=list(idx.subjects(mod._indexed('edgeWeight'),None))
    assert len(statements)==1
    assert list(idx.objects(statements[0],mod._indexed('edgeWeight')))==[Literal(0.5,datatype=XSD.double)]
    assert list(idx.objects(statements[0],mod._indexed('scientificSupportVerifiedFlag')))==[
        Literal(False,datatype=XSD.boolean)]


def test_opaque_metadata_not_automatically_indexed(view,g4_contract):
    view.graph.add_node(SemanticNode('extra','ScientificConcept',
                                    {'name':'Complex','nested':{'unsafe':['not indexed']}},{}))
    indexed=mod.build_scientific_index(view)
    predicates={str(p) for _,p,_ in indexed.dataset.graph(indexed.contexts[3])}
    assert not any('nested' in p for p in predicates)


@pytest.mark.parametrize('field,value',[
    ('name',['not','scalar']),('name','x'*9000),('status',None),('status',True),
])
def test_invalid_scientific_scalar_fails_closed(view,g4_contract,field,value):
    view.graph.add_node(SemanticNode('invalid','ScientificConcept',{field:value},{}))
    with pytest.raises(mod.ScientificIndexError):
        mod.build_scientific_index(view)


@pytest.mark.parametrize('bad', [float('nan'),float('inf'),True,'heavy'])
def test_invalid_edge_weight_fails_closed(view,g4_contract,bad):
    view.graph.add_edge(SemanticEdge('concept:parent','concept:child','SUPPORTS',
                                    {'weight':bad},{}))
    with pytest.raises((mod.ScientificIndexError, GraphStoreError)):
        mod.build_scientific_index(view)


def test_canonical_nquads_and_rdflib_parse(index):
    assert index.nquads==b''.join(sorted(index.nquads.splitlines(keepends=True)))
    parsed=Dataset(default_union=False)
    parsed.parse(data=index.nquads.decode(),format='nquads')
    assert set(parsed.quads((None,None,None,None)))==set(index.dataset.quads((None,None,None,None)))


def test_source_edge_count_preserved(index):
    assert index.projection_counts['source_edge_occurrence_count']==6
    assert index.projection_counts['source_node_count']==4


def test_report_digest_and_detached_roundtrip(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *a,**kw:(view,None))
    report,nq=mod.build_report(tmp_path,mode='candidate',knowledge_graph='example.json',
                               query_id='citations_for_entity',argument='prop:one',limit=50)
    assert report['result_count']==2
    assert report['report_sha256']==hashlib.sha256(canonical({k:v for k,v in report.items()
                                                             if k!='report_sha256'})).hexdigest()
    source=tmp_path/'source';source.mkdir()
    dest=tmp_path/'detached'
    mod.write_report(dest,source,report,nq)
    assert mod.verify_report(dest,source,mode='candidate',knowledge_graph='example.json',
                             query_id='citations_for_entity',argument='prop:one',limit=50)==report
    assert (dest/'scientific-index.nq').read_bytes() == nq
    assert (dest/'scientific-index-report.json').read_bytes() == canonical(report)
    assert len(report['results']) == 2


def test_detached_report_tampering_rejected(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *a,**kw:(view,None))
    s=tmp_path/'source';s.mkdir();dest=tmp_path/'report'
    options=dict(mode='candidate',knowledge_graph='example.json',
                 query_id='citations_for_entity',argument='prop:one',limit=3)
    report,nq=mod.build_report(s,**options)
    mod.write_report(dest,s,report,nq)
    report['result_count']=500
    report['report_sha256']=hashlib.sha256(canonical({k:v for k,v in report.items()
                                                    if k!='report_sha256'})).hexdigest()
    (dest/'scientific-index-report.json').write_bytes(canonical(report))
    with pytest.raises(mod.ScientificIndexError):
        mod.verify_report(dest,s,**options)


def test_nquads_tampering_rejected(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *a,**kw:(view,None))
    s=tmp_path/'source';s.mkdir();dest=tmp_path/'report'
    options=dict(mode='candidate',knowledge_graph='example.json',
                 query_id='concepts_by_status',argument='draft')
    report,nq=mod.build_report(s,**options)
    mod.write_report(dest,s,report,nq)
    (dest/'scientific-index.nq').write_bytes(nq+b'\n')
    with pytest.raises(mod.ScientificIndexError):
        mod.verify_report(dest,s,**options)


def test_missing_g4_occurrence_cannot_be_indexed(view,g4_contract,monkeypatch):
    orig=g4_contract[0].export_view
    def changed(v,*,store_state=None):
        res=orig(v,store_state=store_state)
        g=Graph().parse(data=res['ntriples'],format='nt')
        snapshot=ri01._uri('snapshot',v.fingerprint)
        stmt=next(g.objects(snapshot,mod._property('containsEdge')))
        g.remove((snapshot,mod._property('containsEdge'),stmt))
        g.remove((stmt,None,None))
        res['ntriples']=g.serialize(format='nt').encode()
        return res
    monkeypatch.setattr(g4_contract[0],'export_view',changed)
    with pytest.raises(mod.ScientificIndexError):
        mod.build_scientific_index(view)


def test_existing_output_not_replaced(view,g4_contract,tmp_path,monkeypatch):
    monkeypatch.setattr(ri01,'resolve_view',lambda *a,**kw:(view,None))
    s=tmp_path/'source';s.mkdir();dest=tmp_path/'report';dest.mkdir()
    a,nq=mod.build_report(s,mode='candidate',knowledge_graph='x',
                          query_id='relations_for_entity',argument='prop:one')
    with pytest.raises(ri01.RDFQueryLayerError):
        mod.write_report(dest,s,a,nq)


def test_failed_g4_verification_blocks_index(view,g4_contract,monkeypatch):
    def fail(*a,**kw):
        raise ValueError('source verification failed')
    monkeypatch.setattr(g4_contract[1],'verify_rdf_interoperability',fail)
    with pytest.raises(ValueError, match='source verification failed'):
        mod.build_scientific_index(view)


def test_native_g4_integration_if_installed(tmp_path):
    from importlib.util import find_spec
    if find_spec('audit_engine.semantic_audit.graph.rdf_export') is None:
        pytest.skip('October 13 source snapshot predates G4.5 native exporter')
    from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph
    import uuid
    c1=str(uuid.UUID('00000000-0000-4000-8000-000000000001'))
    c2=str(uuid.UUID('00000000-0000-4000-8000-000000000002'))
    raw={'concepts':{c1:{'concept_id':c1,'name':'Root','parent_concept_ids':[],
                         'source_ids':[],'type':'physics','status':'proposed'},
                     c2:{'concept_id':c2,'name':'Child','parent_concept_ids':[c1],
                         'source_ids':[],'type':'physics','status':'proposed'}},
         'propositions':{},'relationships':{}}
    v=from_scientific_graph(raw)
    idx=mod.build_scientific_index(v)
    assert len(idx.query('subconcepts_of',f'scientific:concept:{c1}'))==1
    assert idx.base.g4_manifest['manifest_sha256']
