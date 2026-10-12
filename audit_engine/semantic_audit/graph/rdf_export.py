"""G4 RDF Export: deterministic, read-only RDF/Turtle and N-Triples projection.

Export GE-01 projections or the independently verified GE-02 persisted graph.
RDF identifiers and named predicates express *structure*, never scientific truth.
The standard RDF reification nodes retain parallel edges and edge metadata.
No graph/repository mutation, implicit external dereference or SAT authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import quote

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.domain_integration import (
    GraphDomainView, from_scientific_graph, GraphDomainError,
)
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, PersistentDomainGraphStore, canonical, parse, _input_path, _strict_view,
)

SCHEMA = 'g4-rdf-export/v1'
NS = 'urn:fea:semantic-graph:v1:'
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
XSD = 'http://www.w3.org/2001/XMLSchema#'
MAX_TRIPLES = 250_000
MAX_BYTES = 48_000_000
_SHA = re.compile(r'^[a-f0-9]{64}$')


class RDFExportError(ValueError):
    """Unsafe RDF projection, source mismatch, or corrupted export."""


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _iri(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise RDFExportError('Invalid graph resource identifier')
    # Never interpret graph node identifiers as already trusted IRIs.
    return '<' + NS + quote(value, safe='') + '>'


def _literal(value: str) -> str:
    if not isinstance(value, str):
        raise RDFExportError('RDF literal must be text')
    try:
        value.encode('utf-8', 'strict')
    except UnicodeError as exc:
        raise RDFExportError('Unpaired surrogate in RDF literal') from exc
    # JSON escapes a superset of the forbidden N-Triples string characters.
    return json.dumps(value, ensure_ascii=True)


def _boolean(value: bool) -> str:
    if type(value) is not bool:
        raise RDFExportError('RDF boolean value expected')
    return _literal('true' if value else 'false') + '^^<' + XSD + 'boolean>'


def _number(value: int) -> str:
    if type(value) is not int or value < 0:
        raise RDFExportError('RDF non-negative integer expected')
    return _literal(str(value)) + '^^<' + XSD + 'nonNegativeInteger>'


def _json_literal(obj: Any) -> str:
    try:
        return _literal(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False))
    except (OverflowError, TypeError, ValueError, UnicodeError) as exc:
        raise RDFExportError('Nonfinite or invalid JSON graph metadata') from exc


def _triple(s: str, p: str, o: str) -> str:
    return f'{s} {p} {o} .\n'


def _predicate(name: str) -> str:
    return _iri('property:' + name)


def _graph_obj(view: GraphDomainView) -> tuple[dict, str]:
    if not isinstance(view, GraphDomainView):
        raise RDFExportError('A verified GE-01 view is required')
    snap = view.snapshot()  # Checks graph determinism and digest.
    _strict_view(snap)       # Independent GE-02 structural/authority validation.
    return snap, _iri('snapshot:' + view.fingerprint)


def export_view(view: GraphDomainView, *, store_state: dict | None = None) -> dict:
    """Generate deterministic RDF bytes and manifest. Does not write files.

    Every node/edge is represented by a resource; direct RDF relation triples
    are emitted for basic RDF clients. Parallel edges have uniquely identified
    reified RDF Statements even when direct triples coincide.
    """
    snapshot, graph_iri = _graph_obj(view)
    if store_state is not None:
        if (not isinstance(store_state, dict) or store_state.get('status') != 'verified'
            or store_state.get('graph_fingerprint') != view.fingerprint
            or store_state.get('snapshot_sha256') != snapshot['snapshot_sha256']
            or not isinstance(store_state.get('generation'), int)
            or not isinstance(store_state.get('head'), str)):
            raise RDFExportError('Persisted graph provenance does not match view')
    graph: SemanticGraph = view.graph
    identifiers = [n.node_id for n in graph.nodes]
    if len(set(identifiers)) != len(identifiers):
        raise RDFExportError('Duplicate semantic node identity')
    if any(e.source_id not in identifiers or e.target_id not in identifiers for e in graph.edges):
        raise RDFExportError('Dangling semantic relationship')
    lines: set[str] = set()

    def emit(s: str, p: str, o: str):
        lines.add(_triple(s, p, o))
        if len(lines) > MAX_TRIPLES:
            raise RDFExportError('RDF triple budget exceeded')

    rdf_type = '<' + RDF + 'type>'
    emit(graph_iri, rdf_type, _iri('type:GraphSnapshot'))
    emit(graph_iri, _predicate('domain'), _literal(view.domain))
    emit(graph_iri, _predicate('graphFingerprint'), _literal(view.fingerprint))
    emit(graph_iri, _predicate('inputSha256'), _literal(view.input_sha256))
    emit(graph_iri, _predicate('snapshotSha256'), _literal(snapshot['snapshot_sha256']))
    emit(graph_iri, _predicate('scientificTruthEstablished'), _boolean(False))
    emit(graph_iri, _predicate('automaticApprovalPermitted'), _boolean(False))
    emit(graph_iri, _predicate('authoritativeMutationPermitted'), _boolean(False))
    if store_state:
        emit(graph_iri, _predicate('persistedHead'), _literal(store_state['head']))
        emit(graph_iri, _predicate('persistedGeneration'), _number(store_state['generation']))

    for node in sorted(graph.nodes, key=lambda n: n.node_id):
        resource = _iri('node:' + node.node_id)
        emit(graph_iri, _predicate('containsNode'), resource)
        emit(resource, rdf_type, _iri('type:' + node.entity_type))
        emit(resource, _predicate('nodeIdentifier'), _literal(node.node_id))
        emit(resource, _predicate('entityType'), _literal(node.entity_type))
        emit(resource, _predicate('attributesJson'), _json_literal(node.attributes))
        emit(resource, _predicate('metadataJson'), _json_literal(node.metadata))

    def edge_value(edge) -> dict:
        return {'source': edge.source_id, 'target': edge.target_id,
                'relation': edge.relation_type, 'attributes': edge.attributes,
                'metadata': edge.metadata}

    edge_payloads = sorted((canonical(edge_value(e)) for e in graph.edges))
    last = None
    instance = 0
    for payload in edge_payloads:
        if payload == last:
            instance += 1
        else:
            instance = 0
        last = payload
        digest = _hash(payload)
        info = parse(payload)
        edge_iri = _iri(f'edge:{digest}:{instance}')
        source_iri = _iri('node:' + info['source'])
        target_iri = _iri('node:' + info['target'])
        rel_iri = _iri('relation:' + info['relation'])
        emit(source_iri, rel_iri, target_iri)
        emit(graph_iri, _predicate('containsEdge'), edge_iri)
        emit(edge_iri, rdf_type, '<' + RDF + 'Statement>')
        emit(edge_iri, '<' + RDF + 'subject>', source_iri)
        emit(edge_iri, '<' + RDF + 'predicate>', rel_iri)
        emit(edge_iri, '<' + RDF + 'object>', target_iri)
        emit(edge_iri, _predicate('relationType'), _literal(info['relation']))
        emit(edge_iri, _predicate('parallelEdgeOccurrence'), _number(instance))
        emit(edge_iri, _predicate('attributesJson'), _json_literal(info['attributes']))
        emit(edge_iri, _predicate('metadataJson'), _json_literal(info['metadata']))
        emit(edge_iri, _predicate('scientificSupportVerified'), _boolean(False))

    content = ''.join(sorted(lines)).encode('utf-8')
    ttl = ('@prefix fea: <' + NS + '> .\n@prefix rdf: <' + RDF + '> .\n'
           '@prefix xsd: <' + XSD + '> .\n\n').encode('ascii') + content
    if len(content) > MAX_BYTES or len(ttl) > MAX_BYTES:
        raise RDFExportError('Export exceeds byte budget')
    report = {
        'schema_version': SCHEMA,
        'domain': view.domain,
        'graph_fingerprint': view.fingerprint,
        'source_snapshot_sha256': snapshot['snapshot_sha256'],
        'source_input_sha256': view.input_sha256,
        'persisted_store_head': store_state['head'] if store_state else None,
        'persisted_store_generation': store_state['generation'] if store_state else None,
        'node_count': len(graph.nodes),
        'edge_occurrence_count': len(graph.edges),
        'triple_count': len(lines),
        'ntriples_sha256': _hash(content),
        'turtle_sha256': _hash(ttl),
        'scientific_truth_established': False,
        'automatic_approval_permitted': False,
        'authoritative_graph_mutation_permitted': False,
        'rdf_semantic_entailment_verified': False,
        'round_trip_semantic_approval': False,
    }
    report['manifest_sha256'] = _hash(canonical(report))
    return {'ntriples': content, 'turtle': ttl, 'manifest': report}


def verify_export(view: GraphDomainView, bundle: dict, *, store_state: dict | None = None) -> bool:
    """Independently regenerate RDF and compare *every byte*, not only self-hashes."""
    expected = export_view(view, store_state=store_state)
    if not isinstance(bundle, dict) or set(bundle) != set(expected):
        raise RDFExportError('Missing or unexpected RDF export members')
    for key in expected:
        if bundle[key] != expected[key]:
            raise RDFExportError(f'RDF export {key} differs from independently projected graph')
    return True


def _output_dir(path: Path, repo: Path) -> Path:
    repo = repo.resolve(strict=True)
    result = path.absolute()
    # Outputs must not change the validated graph/repository under any circumstances.
    if repo == result or repo in result.parents or result.exists() or result.is_symlink():
        raise RDFExportError('Output directory must be new and outside target repository')
    if any(x.is_symlink() for x in (result.parent, *result.parents)):
        raise RDFExportError('Symlinked output parent prohibited')
    if not result.parent.is_dir():
        raise RDFExportError('Missing output parent')
    return result


def _new_file(path: Path, data: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _read_regular(path: Path, limit: int):
    if path.is_symlink():
        raise RDFExportError('Symlinked export forbidden')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise RDFExportError('Unexpected export file type or size')
        data = os.read(fd, limit + 1)
        if len(data) != st.st_size:
            raise RDFExportError('Export changed during read')
        return data
    finally:
        os.close(fd)


def read_export(folder: Path) -> dict:
    return {
        'ntriples': _read_regular(folder/'semantic-graph.nt', MAX_BYTES),
        'turtle': _read_regular(folder/'semantic-graph.ttl', MAX_BYTES),
        'manifest': parse(_read_regular(folder/'rdf-export-manifest.json', 10240)),
    }


def export_to_directory(repo: Path, destination: Path, *, mode: str = 'persisted',
                        knowledge_graph: str | None = None,
                        store: str = '.graph-state/scientific') -> dict:
    repo = Path(repo).resolve(strict=True)
    destination = _output_dir(Path(destination), repo)
    if mode == 'persisted':
        if store != '.graph-state/scientific':
            raise RDFExportError('Only the verified scientific graph-state store is accepted')
        graph_store = PersistentDomainGraphStore(repo/store)
        state = graph_store.verify()
        if state.get('status') != 'verified':
            raise RDFExportError('Cannot RDF-export an empty or unverified graph-state store')
        view = graph_store.current_view()
        assert view is not None
    elif mode == 'candidate':
        if not knowledge_graph:
            raise RDFExportError('Candidate RDF export requires a scientific knowledge graph path')
        from audit_engine.semantic_audit.graph.domain_integration import _read_json
        try:
            view = from_scientific_graph(_read_json(_input_path(repo, knowledge_graph)))
        except (GraphStoreError, GraphDomainError, OSError, ValueError) as exc:
            raise RDFExportError('Unsafe or inconsistent candidate graph') from exc
        state = None
    else:
        raise RDFExportError('Unsupported RDF export mode')
    bundle = export_view(view, store_state=state)
    destination.mkdir(mode=0o700)
    _new_file(destination/'semantic-graph.nt', bundle['ntriples'])
    _new_file(destination/'semantic-graph.ttl', bundle['turtle'])
    _new_file(destination/'rdf-export-manifest.json', canonical(bundle['manifest']))
    if not verify_export(view, read_export(destination), store_state=state):
        raise RDFExportError('Export could not be independently reproduced')
    return bundle['manifest']


def main(argv=None):
    parser = argparse.ArgumentParser(description='G4 deterministic RDF export (read-only)')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=('persisted', 'candidate'), default='persisted')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(argv)
    result = export_to_directory(Path(args.repository), Path(args.output_dir),
                                 mode=args.mode, knowledge_graph=args.knowledge_graph)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RDFExportError, GraphStoreError, GraphDomainError, OSError, ValueError, TypeError, KeyError) as exc:
        print('G4 RDF export rejected:', exc, file=__import__('sys').stderr)
        raise SystemExit(2)
