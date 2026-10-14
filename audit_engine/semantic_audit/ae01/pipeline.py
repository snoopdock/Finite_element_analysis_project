"""AE-01 vertical slice: source bytes -> source graph -> G3 verification -> sealed findings."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis.identity import edge_fingerprint, graph_fingerprint
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.verification import GraphAttributeConstraintVerifier, VerifierRegistry, VerificationService

from .publication import attempt, canonical, publish, sha
from .source import extract, inventory, module_name
from .projection import project_imports

VERSION = 'ae01/v1'
POLICY_VALUES = frozenset({'production', 'experimental', 'stable', 'deprecated'})


def _graph(manifest: dict, sources: dict[str, bytes], imports: list[dict], calls: list[dict],
           functions: list[dict], lifecycles: dict[str, str]) -> SemanticGraph:
    graph = SemanticGraph()
    known: set[str] = set()
    def add(id: str, kind: str, attrs: dict | None = None, meta: dict | None = None):
        if id in known:
            return
        graph.nodes.append(SemanticNode(id, kind, dict(attrs or {}), dict(meta or {})))
        known.add(id)
    def edge(src: str, dst: str, rel: str, meta: dict):
        if src not in known or dst not in known:
            raise ValueError('AE01 attempted dangling edge')
        graph.edges.append(SemanticEdge(src, dst, rel, metadata=meta))
    for row in manifest['files']:
        if row['status'] != 'included':
            continue
        path, module = row['path'], module_name(row['path'])
        add('file:' + path, 'SourceFile', {'sha256': row['sha256'], 'path': path})
        add('module:' + module, 'Module', {'lifecycle': lifecycles[module]} if module in lifecycles else {},
            {'path': path, 'sha256': row['sha256']})
        edge('module:' + module, 'file:' + path, 'DEFINED_IN', {'source_id': path})
    for imp in imports:
        src = 'module:' + module_name(imp['file'])
        node = imp['id']
        add(node, 'ImportOccurrence', {'status': imp['status']}, {'source_id': imp['file'], 'line': imp['line']})
        edge(src, node, 'HAS_IMPORT', {'source_id': imp['file'], 'occurrence_id': node})
        if imp['status'] == 'internal':
            dest = 'module:' + imp['target']
            edge(src, dest, 'IMPORTS', {'source_id': imp['file'], 'source_sha256': next(
                r['sha256'] for r in manifest['files'] if r['path'] == imp['file']),
                'line': imp['line'], 'column': imp['column'], 'occurrence_id': node,
                'context': imp['context']})
        elif imp['status'] == 'external':
            dest = 'external:' + str(imp['target'])
            add(dest, 'ExternalModule')
            edge(src, dest, 'IMPORTS', {'source_id': imp['file'], 'occurrence_id': node,
                                        'line': imp['line'], 'external': True})
    for f in functions:
        add(f['id'], 'Function', {'name': f['name']}, {'source_id': f['file'], 'line': f['line']})
        edge('module:' + module_name(f['file']), f['id'], 'DEFINES', {'source_id': f['file']})
    for call in calls:
        add(call['id'], 'CallSite', {'spelling': call['spelling'], 'resolution': call['resolution']},
            {'source_id': call['file'], 'line': call['line'], 'column': call['column']})
        edge('module:' + module_name(call['file']), call['id'], 'HAS_CALL', {'source_id': call['file']})
    return graph


def audit_repository(source_root: Path | str, output_root: Path | str, *,
                     lifecycle: dict[str, str], policy_file: Path | str,
                     excludes: tuple[str, ...] = ()) -> dict[str, Any]:
    source_root, output_root = Path(source_root).absolute(), Path(output_root).absolute()
    if source_root == output_root:
        raise ValueError('Source and output root must differ')
    with attempt(output_root):
        for mod, value in lifecycle.items():
            if not mod or value not in POLICY_VALUES:
                raise ValueError(f'Invalid lifecycle for {mod!r}: {value!r}')
        policy = DomainRuleLoader.from_yaml(policy_file)
        if policy.policy.rule_id != 'architecture.no_production_to_experimental_dependency':
            raise ValueError('AE-01 only supports the pinned architecture policy')
        if policy.verifier_id != 'graph-attribute-constraint' or tuple(policy.selector.source_entity_types) != ('Module',) or tuple(policy.selector.target_entity_types) != ('Module',):
            raise ValueError('AE-01 rule schema incompatibility')
        if not policy.selector.predicates or 'IMPORTS' not in policy.selector.predicates:
            raise ValueError('AE-01 architecture policy does not select IMPORTS')
        policy_bytes = Path(policy_file).read_bytes()
        manifest, sources = inventory(source_root, excludes=excludes, output=output_root)
        imports, calls, functions, issues = extract(sources, manifest, lifecycle)
        graph = _graph(manifest, sources, imports, calls, functions, lifecycle)
        # G3 architecture verifiers operate on an explicit, deterministic, lossless
        # projection of all internal module IMPORTS edges (including parallels).
        # The large source graph retains every file, function, call and occurrence.
        policy_graph = SemanticGraph(
            nodes=[node for node in graph.nodes if node.entity_type == 'Module'],
            edges=[edge for edge in graph.edges if edge.relation_type == 'IMPORTS'
                   and not edge.metadata.get('external')],
        )
        missing_classification = []
        for imp in imports:
            if imp['status'] != 'internal':
                continue
            source_module = module_name(imp['file'])
            if source_module not in lifecycle or imp['target'] not in lifecycle:
                missing_classification.append(imp['id'])
        if missing_classification:
            issues.append({'kind': 'unclassified_internal_dependency', 'occurrences': sorted(missing_classification)})
        unsafe_paths = [r['path'] for r in manifest['files'] if r.get('reason') in ('symlink_file', 'symlink_directory')]
        if unsafe_paths:
            issues.append({'kind': 'symlink_scope_excluded', 'paths': unsafe_paths})
        second_manifest, second_sources = inventory(source_root, excludes=excludes, output=output_root)
        if second_manifest != manifest or second_sources != sources:
            issues.append({'kind': 'source_changed_during_audit'})
        if manifest['summary']['error']:
            issues.append({'kind': 'source_scan_incomplete', 'count': manifest['summary']['error']})
        for imp in imports:
            if imp['status'] == 'internal' and imp['context']:
                issues.append({'kind': 'conditional_dependency', 'occurrence_id': imp['id'], 'context': imp['context']})
                if 'type_checking' in imp['context']:
                    issues.append({'kind': 'type_checking_only_dependency', 'occurrence_id': imp['id']})
        # G3 graph analysis independently computes the witness record and graph fingerprint.
        registry = VerifierRegistry()
        registry.register(GraphAttributeConstraintVerifier())
        executor = DomainRuleExecutor(VerificationService(registry))
        executions = []
        findings = []
        evidence_to_occurrence: dict[str, dict] = {}
        for edge in policy_graph.edges:
            if edge.relation_type == 'IMPORTS':
                evidence_to_occurrence[edge_fingerprint(edge)] = dict(edge.metadata)
        considered = 0
        modules_with_imports = {e.source_id for e in policy_graph.edges}
        for module in sorted({module_name(p) for p in sources}):
            if 'module:' + module not in modules_with_imports:
                continue
            scoped_graph = project_imports(policy_graph, 'module:' + module)
            scoped_service = SemanticGraphAnalysisService(scoped_graph)
            result = scoped_service.analyze(GraphQuery('ae01-imports:' + module, QueryType.DEPENDENCY,
                                                      ['module:' + module], {'max_depth': 1, 'relation_types': ['IMPORTS']}))
            execution = executor.execute(policy, result, scoped_graph)
            selected = [o for o in result.observations if o.predicate == 'IMPORTS' and
                        scoped_graph.get_node(o.object_id).entity_type == 'Module']
            considered += len(selected)
            if execution.reason != 'executed' or len(execution.obligations) != len(selected):
                issues.append({'kind': 'rule_applicability_failure', 'module': module,
                               'reason': execution.reason, 'expected': len(selected),
                               'actual': len(execution.obligations)})
            for receipt in execution.receipts:
                if receipt.decision.value in ('inconclusive', 'error') or receipt.evidence_state.value != 'validated':
                    issues.append({'kind': 'verification_incomplete', 'receipt_id': receipt.receipt_id})
            for finding in execution.findings:
                # Each obligation binds exactly one observed edge/evidence record.
                if len(finding.evidence_ids) != 1 or finding.evidence_ids[0] not in evidence_to_occurrence:
                    issues.append({'kind': 'missing_occurrence_witness', 'finding_id': finding.finding_id})
                    continue
                witness = evidence_to_occurrence[finding.evidence_ids[0]]
                findings.append({'finding': finding.to_dict(), 'witness': witness})
            executions.append({'source_module': module, 'analysis_id': result.analysis_id,
                               'source_projection_fingerprint': result.graph_fingerprint,
                               'rule_execution': execution.to_dict()})
        if considered == 0:
            issues.append({'kind': 'required_rule_not_applicable', 'reason': 'no_internal_dependency_observations'})
        fingerprint = graph_fingerprint(graph)
        policy_fingerprint = graph_fingerprint(policy_graph)
        manifest_hash = sha(canonical(manifest))
        source_digest = sha(canonical({'manifest_sha256': manifest_hash,
                                       'included': [[p, hashlib.sha256(sources[p]).hexdigest()] for p in sorted(sources)]}))
        policy_hash = hashlib.sha256(policy_bytes).hexdigest()
        config = {'lifecycle': dict(sorted(lifecycle.items())), 'excludes': sorted(excludes),
                  'policy_sha256': policy_hash, 'python_ast_version': f'{sys.version_info.major}.{sys.version_info.minor}', 'version': VERSION}
        run_id = 'ae01-' + sha(canonical([source_digest, config]))[:32]
        report = {'schema': 'ae01/report/v1', 'run_id': run_id,
                  'execution_status': 'completed',
                  'assurance_completeness': 'complete_within_declared_scope' if not issues else 'inconclusive',
                  'rule_status': 'executed' if considered else 'not_applicable',
                  'verified_compliance': not issues and not findings and considered > 0,
                  'source_manifest_sha256': manifest_hash, 'source_digest': source_digest,
                  'graph_fingerprint': fingerprint, 'policy_graph_fingerprint': policy_fingerprint,
                  'policy_sha256': policy_hash,
                  'applicable_observations': considered, 'findings': findings,
                  'issues': issues, 'counts': {'imports': len(imports), 'calls': len(calls),
                    'functions': len(functions), 'source_files': len(sources), 'verified_findings': len(findings)}}
        artifacts = {'manifest.json': manifest, 'source_facts.json': {'imports': imports, 'calls': calls, 'functions': functions},
                     'graph.json': graph.to_dict(), 'policy_graph.json': policy_graph.to_dict(),
                     'rule_executions.json': executions,
                     'policy.json': {'sha256': policy_hash, 'rule': policy.to_dict(), 'configuration': config},
                     'report.json': report}
        verified = publish(output_root, run_id, artifacts)
        return {'report': report, 'publication': verified}
