"""AE-17: bounded investigation of verified *source replay*, never root-cause proof.

Consumes AE-16 operational observations only after independently replaying their
source and output. Competing explanations are generated from issue classifications,
not from a model's authority. G3.3 executes/plans ONLY existing verification
obligations supplied explicitly, not these hypotheses. No code execution, LLM,
network, or workflow writes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae16.operations import build_report as ae16_build
from audit_engine.semantic_audit.ae16.publication import verify_observation as ae16_verify
from audit_engine.semantic_audit.evolution.memory import AuditLongTermMemory
from audit_engine.semantic_audit.orchestration.service import AuditOrchestrationService

SCHEMA = 'ae17/bounded_investigation/v1'
MAX_CASES = 80
MAX_CONTEXT = 64
MAX_HISTORY = 40

# Not a causal classifier: alternatives and questions that a human/independent
# experiment can discriminate. Unknown issue types remain explicitly unsupported.
HYPOTHESES: dict[str, tuple[tuple[str, str, str], ...]] = {
    'missing_evidence_file': (
        ('evidence_not_retained', 'The declared artifact was not retained at the supplied evidence location', 'Examine the producing step and retention/upload contract'),
        ('evidence_location_mismatch', 'The evidence may exist under a different path or snapshot', 'Inspect authenticated file manifest and checkout identity'),
    ),
    'required_check_not_executed': (
        ('required_check_skipped', 'The mandatory check may not have been scheduled', 'Compare the authoritative check schedule to the observed step record'),
        ('required_check_unreported', 'The check may have run but its result was omitted', 'Obtain independent per-step check outcomes'),
    ),
    'required_check_not_satisfied': (
        ('unsatisfied_oracle', 'A required check may have failed or lacked usable witnesses', 'Independently rerun the check with expected positive and negative controls'),
        ('partial_telemetry', 'The check result may be incomplete', 'Review captured test IDs, log evidence and execution status'),
    ),
    'producer_consumer_content_mismatch': (
        ('wrong_producer_bytes', 'The producer may have supplied different artifact bytes', 'Hash authenticated producer output at its producing step'),
        ('stale_consumer_bytes', 'The consumer may have retrieved stale or unrelated bytes', 'Compare source run, checkout, transport and consumer digest'),
    ),
    'missing_producer_job_dependency': (
        ('dependency_not_declared', 'The consuming job may lack a required job dependency', 'Check actual job DAG and artifact transfer configuration'),
        ('unmodeled_transfer', 'An external transfer mechanism may not be described', 'Collect authenticated transfer provenance or declare it unsupported'),
    ),
    'consumer_without_declared_producer': (
        ('missing_producer', 'The run declaration may omit a producing step', 'Locate the artifact producer and exact source snapshot'),
        ('external_artifact', 'The consumed artifact may come from outside this run', 'Collect a source-run and content-addressed provenance record'),
    ),
    'claimed_success_without_zero_exit': (
        ('exit_status_mismatch', 'The declared step outcome and exit status differ', 'Retrieve the authenticated step exit status'),
        ('nested_status_confusion', 'A nested command result may have been mistaken for step outcome', 'Separate nested test, step and job results'),
    ),
    'declared_run_status_inconsistent_with_jobs': (
        ('job_failure_misclassified', 'The run status may not reflect its declared job outcomes', 'Compare authenticated overall run status and per-job results'),
        ('incomplete_job_reporting', 'Some job outcome records may be missing or malformed', 'Obtain complete required job manifest'),
    ),
    'nested_test_outcome_mismatch': (
        ('unexpected_test_outcome', 'The nested test result differs from the expected oracle', 'Independently execute the test with exact expected outcome'),
        ('oracle_metadata_error', 'The recorded expected test outcome may be incorrect', 'Review test specification separate from its execution result'),
    ),
    'no_required_check_contract': (
        ('absent_coverage_contract', 'No authoritative required-check contract was supplied', 'Obtain and approve a versioned required-check inventory'),
    ),
}
FALLBACK = (
    ('declared_inconsistency', 'The supplied execution declaration contains an unresolved inconsistency', 'Inspect authenticated context and independently reproduce the observation'),
    ('incomplete_evidence', 'The supplied declaration may omit evidence relevant to the observation', 'Retrieve source-bound independent witnesses'),
)


def _bound_int(value: Any, field: str, limit: int) -> int:
    if type(value) is not int or not 1 <= value <= limit:
        raise ValueError(f'{field} must be a positive integer at most {limit}')
    return value


def _context(graph:dict, subject:str, files:dict, cap:int) -> dict:
    """Deterministic bounded one-hop graph retrieval, not execution inference."""
    nodes={n['id']:n for n in graph['nodes']}
    all_edges=[e for e in graph['edges'] if e['source']==subject or e['target']==subject]
    # Missing evidence can be addressed by a file path rather than a node ID.
    paths=([{'path':subject,'digest':files[subject]['sha256'], 'state':files[subject]['state']}]
           if subject in files else [])
    edges=sorted(all_edges,key=lambda e:canonical(e))
    selected=edges[:cap]
    node_ids={subject} if subject in nodes else set()
    for e in selected:node_ids.update((e['source'],e['target']))
    return {'subject_found_in_graph':subject in nodes,
            'nodes':[nodes[k] for k in sorted(node_ids) if k in nodes],
            'relationships':selected,
            'file_witnesses':paths,
            'truncated':len(edges)>cap,
            'total_matching_relationships':len(edges)}


def build_investigation(declaration_file:Path|str,evidence_root:Path|str,ae16_output:Path|str,*,
                        max_cases:int=MAX_CASES,max_context:int=MAX_CONTEXT,
                        ae01_output:Path|str|None=None,source_root:Path|str|None=None)->dict:
    """Reverify upstream AE-16 and derive nonauthoritative investigation steps.

    Replaying actual source bytes is mandatory; a caller-provided AE-16 report,
    graph fingerprint or memory entry cannot be used as proof on its own.
    """
    max_cases=_bound_int(max_cases,'max_cases',MAX_CASES)
    max_context=_bound_int(max_context,'max_context',MAX_CONTEXT)
    upstream=ae16_verify(declaration_file,evidence_root,ae16_output,ae01_output=ae01_output,source_root=source_root)
    source_report,source_graph=ae16_build(declaration_file,evidence_root,ae01_output=ae01_output,source_root=source_root)
    if not isinstance(upstream['generation'],str) or not upstream['generation'].startswith('ae16-'):
        raise ValueError('Upstream generation identity malformed')
    if source_report['verified_findings'] or source_report['source_authority']!='untrusted_execution_declaration_not_github_authenticated':
        raise ValueError('AE-16 observations may not be promoted into authority')
    issues=source_report['issues']
    selected=issues[:max_cases]
    report_identity={'ae16_generation':upstream['generation'],'declaration_sha256':source_report['declaration_sha256'],
                     'graph_fingerprint':source_report['graph_fingerprint']}
    snapshot=sha(canonical(report_identity))
    cases=[]
    for issue in selected:
        kind=issue['kind']; subject=issue['subject']
        case_id='case-'+sha(canonical({'snapshot':snapshot,'issue':issue}))[:24]
        related=_context(source_graph,subject,source_report['files'],max_context)
        hypotheses=[]
        for code,statement,experiment in HYPOTHESES.get(kind,FALLBACK):
            hypotheses.append({'id':'hyp-'+sha(canonical({'case':case_id,'alternative':code}))[:24],
                               'kind':code,'statement':statement,
                               'epistemic_status':'unverified_possible_explanation',
                               'evidence_to_seek':experiment,
                               'required_independent_action':'human_authorized_read_only_check',
                               'source_issue':case_id})
        parts=subject.split(':')
        correlations=[]
        if parts and parts[0] in ('job','step','check','test') and len(parts)>=2:
            for record in source_report['source_correlations']:
                if record['job']==parts[1] and (parts[0]=='job' or (len(parts)>=3 and record['step']==parts[2])):
                    correlations.append(record)
        cases.append({'id':case_id,'issue':issue,'context':related,
                      'source_correlations':correlations[:max_context],
                      'correlations_truncated':len(correlations)>max_context,
                      'retrieval_scope':'bounded_one_hop_source_graph',
                      'alternatives':hypotheses,
                      'disposition':'unresolved_requires_independent_verification'})
    return {'schema':SCHEMA,'scope':'declared_execution_issues_only',
            'snapshot_id':snapshot,'input_binding':report_identity,
            'source_authority':source_report['source_authority'],
            'evidence_authority':'source_replayed_supplied_bytes_not_authenticated_execution',
            'epistemic_status':'investigation_hypotheses_only',
            'verified_findings':[],'verified_root_causes':[],
            'bounds':{'max_cases':max_cases,'max_context':max_context},
            'observed_issues':len(issues), 'selected_issues':len(cases),
            'investigation_status':'unresolved_cases' if cases else 'no_ae16_issue_not_a_clean_audit',
            'truncated':len(issues)>max_cases,
            'coverage':source_report['coverage_summary'],
            'cases':cases,
            'next_step':'supply_independent_evidence_and_registered_verification_obligations',
            'verification_execution':'not_performed'}


def record_investigation(memory:AuditLongTermMemory, report:dict):
    """Archive hypothesis context, not a verified finding; no filesystem writes."""
    if not isinstance(memory,AuditLongTermMemory):raise TypeError('Expected existing AuditLongTermMemory')
    if report.get('schema')!=SCHEMA or report.get('verified_findings')!=[] or report.get('verified_root_causes')!=[]:
        raise ValueError('Only AE-17 hypothesis reports may be recorded')
    return memory.append_artifact(artifact_type='ae17_hypothesis_context',
                                  artifact_id=sha(canonical(report)),
                                  snapshot_id=report['snapshot_id'],payload=report)


def retrieve_snapshot_history(memory:AuditLongTermMemory,snapshot_id:str,*,limit:int=MAX_HISTORY)->dict:
    """Retrieve history only for a requested snapshot; NEVER proof of currency."""
    if not isinstance(memory,AuditLongTermMemory):raise TypeError('Expected AuditLongTermMemory')
    _bound_int(limit,'limit',MAX_HISTORY)
    selected=[r for r in memory.records_for_snapshot(snapshot_id)
              if r.artifact_type=='ae17_hypothesis_context']
    selected.sort(key=lambda r:r.record_id)
    return {'snapshot_id':snapshot_id,'historical_not_current_evidence':True,
            'records':[r.to_dict() for r in selected[:limit]],'truncated':len(selected)>limit}


def plan_registered_verification(*,obligations,objectives,registry,profiles,budget,policy=None):
    """Delegate to the EXISTING G3.3 verifier planner; do not invent verifiers.

    Callers must supply actual G3.1 obligations backed by admitted analysis,
    not unverified AE-17 hypotheses. This function NEVER executes a verifier.
    """
    if not obligations or not objectives:raise ValueError('Explicit registered obligations and objectives are required')
    return AuditOrchestrationService().plan(obligations=obligations,objectives=objectives,
                                            registry=registry,profiles=profiles,budget=budget,policy=policy)
