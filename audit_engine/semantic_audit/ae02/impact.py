"""AE-02.1 conservative source-to-dependent audit impact assessment.

Inputs are ONLY independently verified AE-01 generations. The historical and
current internal import graphs both participate: removals can invalidate an
old dependent just as additions can affect a current dependent. This is a
review-planning upper bound over *observed static import edges*, not a claim
of complete Python dependency or runtime influence analysis.

The existing G3 semantic graph delta is used as an independent structural
observation. Evidence is linked to occurrence IDs and AE-01 generation seals.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae01.source import module_name
from audit_engine.semantic_audit.evolution.impact import changes_from_delta
from audit_engine.semantic_audit.evolution.delta import GraphDelta
from .delta import compare_snapshots
from .snapshots import VerifiedGeneration


@dataclass(frozen=True)
class ReviewTask:
    module: str
    depth: int
    reasons: tuple[str, ...]
    source_files: tuple[str, ...]
    supporting_occurrences: tuple[str, ...]
    action: str = 'reverify_architecture_policy'

    def to_dict(self) -> dict[str, Any]:
        return {'module': self.module, 'depth': self.depth, 'reasons': list(self.reasons),
                'source_files': list(self.source_files),
                'supporting_occurrences': list(self.supporting_occurrences), 'action': self.action}


def _module_files(g: VerifiedGeneration) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in g.manifest['files']:
        if row['status'] == 'included':
            mapping[module_name(row['path'])].add(row['path'])
    return mapping


def _internal_edges(g: VerifiedGeneration) -> list[tuple[str, str, str]]:
    return sorted((module_name(imp['file']), imp['target'], imp['id'])
                  for imp in g.facts['imports'] if imp['status'] == 'internal')


def build_impact_plan(before: VerifiedGeneration, after: VerifiedGeneration,
                      graph_delta: GraphDelta, *, max_depth: int = 32,
                      max_tasks: int = 2500) -> dict[str, Any]:
    """Plan human-supervised rechecks. A truncated/incomplete scan fails closed.

    max_depth and max_tasks are *output/analysis budgets*, never silent
    justifications for declaring non-affected modules safe.
    """
    if not isinstance(before, VerifiedGeneration) or not isinstance(after, VerifiedGeneration):
        raise TypeError('Impact planning requires sealed AE-01 generations')
    if not isinstance(graph_delta, GraphDelta):
        raise TypeError('Impact planning requires a G3 GraphDelta')
    if not 0 <= max_depth <= 10000 or not 1 <= max_tasks <= 100000:
        raise ValueError('Invalid impact analysis budget')
    delta = compare_snapshots(before, after)
    old_map, new_map = _module_files(before), _module_files(after)
    all_maps = {k: old_map.get(k, set()) | new_map.get(k, set()) for k in old_map.keys() | new_map.keys()}
    reverse: dict[str, set[tuple[str, str]]] = defaultdict(set)
    all_edges = _internal_edges(before) + _internal_edges(after)
    for src, target, occurrence in all_edges:
        reverse[target].add((src, occurrence))
    cause: dict[str, set[str]] = defaultdict(set)
    direct_evidence: dict[str, set[str]] = defaultdict(set)
    for path in delta.added_files:
        cause[module_name(path)].add('source_file_added')
    for path in delta.removed_files:
        cause[module_name(path)].add('source_file_removed')
    for path in delta.modified_files:
        cause[module_name(path)].add('source_bytes_changed')
    for imp in delta.added_dependencies:
        cause[module_name(imp['file'])].add('import_occurrence_added_or_changed')
        cause[imp['target']].add('incoming_import_changed')
        direct_evidence[module_name(imp['file'])].add(imp['id'])
        direct_evidence[imp['target']].add(imp['id'])
    for imp in delta.removed_dependencies:
        cause[module_name(imp['file'])].add('import_occurrence_removed_or_changed')
        cause[imp['target']].add('incoming_import_changed')
        direct_evidence[module_name(imp['file'])].add(imp['id'])
        direct_evidence[imp['target']].add(imp['id'])
    prior_lifecycle = before.policy['configuration']['lifecycle']
    next_lifecycle = after.policy['configuration']['lifecycle']
    changed_labels = sorted(k for k in prior_lifecycle.keys() | next_lifecycle.keys()
                            if prior_lifecycle.get(k) != next_lifecycle.get(k))
    for module in changed_labels:
        cause[module].add('lifecycle_classification_changed')
    atoms = changes_from_delta(graph_delta)
    # Critical disagreement: graph observations and source byte changes are
    # separate authorities. We never infer unchanged source from a graph noop.
    full_recheck_reasons = []
    if (before.report['assurance_completeness'] != 'complete_within_declared_scope' or
            after.report['assurance_completeness'] != 'complete_within_declared_scope'):
        full_recheck_reasons.append('incomplete_ae01_assurance_scope')
    if before.policy['sha256'] != after.policy['sha256']:
        full_recheck_reasons.append('policy_definition_or_configuration_changed')
    # When a lifecycle mapping alone changes, the full rule scope may shift:
    # do not use the dependency closure as a completeness certificate.
    if changed_labels and 'policy_definition_or_configuration_changed' not in full_recheck_reasons:
        full_recheck_reasons.append('lifecycle_mapping_changed')
    if any(row['status'] != 'included' and row['status'] != 'excluded' for row in after.manifest['files']):
        full_recheck_reasons.append('unresolved_source_inventory')
    # A versioned graph policy delta is an independent change atom source.
    if any(atom.kind.value == 'semantic_context_changed' for atom in atoms):
        full_recheck_reasons.append('graph_semantic_context_changed')
    full = bool(full_recheck_reasons)
    # Source-byte edits may retain unchanged imports. Include source-bound
    # occurrences from those edited modules as supporting review witnesses.
    directly_changed = {module_name(path) for path in (delta.added_files + delta.removed_files + delta.modified_files)}
    for generation in (before, after):
        for imp in generation.facts['imports']:
            if module_name(imp['file']) in directly_changed and imp['status'] == 'internal':
                direct_evidence[module_name(imp['file'])].add(imp['id'])
    depths: dict[str, int] = {module: 0 for module in cause}
    paths: dict[str, set[str]] = defaultdict(set)
    for module, supporting in direct_evidence.items():
        paths[module].update(supporting)
    frontier = deque(sorted(depths))
    depth_truncated = False
    while frontier:
        changed = frontier.popleft()
        if depths[changed] >= max_depth:
            if reverse.get(changed) and any(src not in depths for src, _ in reverse[changed]):
                depth_truncated = True
            continue
        for dependent, occurrence in sorted(reverse.get(changed, ())):
            next_depth = depths[changed] + 1
            if dependent not in depths or next_depth < depths[dependent]:
                depths[dependent] = next_depth
                frontier.append(dependent)
                cause[dependent].add('transitive_static_import_dependent')
            if dependent in depths:
                paths[dependent].add(occurrence)
    # A complete-scope recheck adds all modules *after* local propagation,
    # preserving concrete dependency-chain evidence and depth where present.
    if full:
        for module in all_maps:
            cause[module].add('full_scope_recheck_required')
            depths.setdefault(module, 0)
    sorted_modules = sorted(depths, key=lambda m: (depths[m], m))
    task_truncated = len(sorted_modules) > max_tasks
    tasks = tuple(ReviewTask(module, depths[module], tuple(sorted(cause[module])),
                             tuple(sorted(all_maps.get(module, ()))),
                             tuple(sorted(paths.get(module, ()))))
                  for module in sorted_modules[:max_tasks])
    truncated = depth_truncated or task_truncated
    # The same stable source occurrence may appear in both generations with
    # different source bytes. Bind every task witness to its own sealed input.
    referenced = {identifier for task in tasks for identifier in task.supporting_occurrences}
    evidence_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for generation in (before, after):
        source_hashes = {row['path']: row['sha256'] for row in generation.manifest['files']
                         if row['status'] == 'included'}
        for imp in generation.facts['imports']:
            if imp['id'] in referenced and imp['status'] == 'internal':
                evidence_index[imp['id']].append({
                    'generation_id': generation.snapshot.generation_id,
                    'seal_sha256': generation.snapshot.publication_seal_hash,
                    'source_file': imp['file'], 'source_sha256': source_hashes[imp['file']],
                    'line': imp['line'], 'column': imp['column'],
                    'source_module': module_name(imp['file']), 'target_module': imp['target'],
                })
    state = ('full_review_required' if full or truncated else
             'incremental_review_required' if tasks else 'no_detected_change')
    record = {
        'schema': 'ae02/impact_plan/v1',
        'previous_generation': before.snapshot.generation_id,
        'current_generation': after.snapshot.generation_id,
        'previous_seal_sha256': before.snapshot.publication_seal_hash,
        'current_seal_sha256': after.snapshot.publication_seal_hash,
        'g3_graph_delta_id': graph_delta.delta_id,
        'g3_change_atoms': [a.to_dict() for a in atoms],
        'source_digest_changed': delta.source_changed,
        'policy_changed': delta.policy_changed,
        'completeness': state,
        'full_recheck_reasons': sorted(set(full_recheck_reasons + (
            ['budget_exhausted'] if truncated else []))),
        'budgets': {'max_depth': max_depth, 'max_tasks': max_tasks},
        'truncated': truncated,
        'total_detected_modules': len(sorted_modules),
        'tasks': [task.to_dict() for task in tasks],
        'evidence_index': {key: sorted(value, key=lambda item: (item['generation_id'], item['source_sha256']))
                           for key, value in sorted(evidence_index.items())},
        'interpretation': 'Conservative static-import impact and reviewer tasks; no automatic fixes, no runtime or whole-program correctness claim.',
    }
    record['plan_sha256'] = sha(canonical(record))
    return record
