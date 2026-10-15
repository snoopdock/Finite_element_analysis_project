"""AE-15 independent control/data-flow oracles; never assertions of feasible execution."""
import hashlib
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae01.source import inventory
from audit_engine.semantic_audit.ae15 import analyze_snapshot, FlowLimitExceeded
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint


def check(tmp_path, code, *, path='app.py', **limits):
    root=tmp_path/'src'
    root.mkdir(exist_ok=True)
    file=root/path
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(code,encoding='utf8')
    manifest,sources=inventory(root)
    return analyze_snapshot(sources,manifest,**limits)


def scope(report,name):
    return next(s for s in report['scopes'] if s['scope']==name)


def use(s,name,number=0):
    return [u for u in s['uses'] if u['name']==name][number]


def names(s,u):
    return {next(d for d in s['definitions'] if d['id']==did)['line'] for did in u['may_definitions']}


def test_branch_join_has_two_possible_definitions(tmp_path):
    report,graph=check(tmp_path,'def f(flag):\n x=1\n if flag:\n  x=2\n else:\n  x=3\n return x\n')
    s=scope(report,'app.f')
    assert names(s,use(s,'x'))=={4,6}
    assert use(s,'x')['status']=='may_reach_definitions'
    assert any(e.relation_type=='MAY_REACH' for e in graph.edges)
    assert not any(e.relation_type in ('EXECUTED_CALL','RESOLVED_CALLEE','CALLS') for e in graph.edges)


def test_branch_without_else_is_possibly_unbound(tmp_path):
    report,_=check(tmp_path,'def f(flag):\n if flag:\n  x=1\n return x\n')
    s=scope(report,'app.f')
    assert use(s,'x')['status']=='possibly_unbound'
    assert names(s,use(s,'x'))=={3}


def test_deletion_kills_definition(tmp_path):
    report,_=check(tmp_path,'def f():\n x=1\n del x\n return x\n')
    s=scope(report,'app.f')
    assert use(s,'x')['may_definitions']==[] and use(s,'x')['status']=='possibly_unbound'


def test_parameter_is_entry_definition(tmp_path):
    report,_=check(tmp_path,'def f(x):\n return x\n')
    s=scope(report,'app.f')
    assert use(s,'x')['status']=='may_reach_definitions'
    assert names(s,use(s,'x'))=={0}


def test_zero_iteration_loop_does_not_guarantee_body_assignment(tmp_path):
    report,_=check(tmp_path,'def f(seq):\n for item in seq:\n  x=item\n return x\n')
    s=scope(report,'app.f')
    assert use(s,'x')['status']=='possibly_unbound'
    assert 3 in names(s,use(s,'x'))


def test_while_has_loop_backedge_and_zero_iteration(tmp_path):
    report,_=check(tmp_path,'def f(flag):\n while flag:\n  value=3\n  flag=False\n return value\n')
    s=scope(report,'app.f')
    assert any(e['condition']=='next_iteration' for e in s['may_flow'])
    assert use(s,'value')['status']=='possibly_unbound'


def test_early_return_has_no_fallthrough(tmp_path):
    report,_=check(tmp_path,'def f():\n return 1\n x=2\n return x\n')
    s=scope(report,'app.f')
    assert use(s,'x')['status']=='unreachable_on_modeled_paths'
    assert not any(e['from']==next(p['id'] for p in s['control_points'] if p['kind']=='Return' and p['line']==2)
                   and e['condition']=='possible_next' for e in s['may_flow'])


def test_break_skips_loop_else(tmp_path):
    report,_=check(tmp_path,'def f(seq):\n for x in seq:\n  break\n else:\n  value=1\n return value\n')
    s=scope(report,'app.f')
    assert use(s,'value')['status']=='possibly_unbound'
    assert any(l['condition']=='break' for l in s['may_flow'])


def test_nested_function_is_separate_scope(tmp_path):
    report,graph=check(tmp_path,'x=100\ndef outer():\n x=1\n def inner():\n  x=2\n  return x\n return x\n')
    outer=scope(report,'app.outer');inner=scope(report,'app.outer.inner')
    assert names(outer,use(outer,'x'))=={3}
    assert names(inner,use(inner,'x'))=={5}
    assert set(d['id'] for d in inner['definitions']).isdisjoint(d['id'] for d in outer['definitions'])


def test_closure_is_external_not_locally_proved(tmp_path):
    report,_=check(tmp_path,'def outer():\n x=1\n def inner():\n  return x\n')
    s=scope(report,'app.outer.inner')
    assert use(s,'x')['status']=='external_or_unknown_binding'


def test_unsupported_try_marks_partial_and_cannot_report_clean(tmp_path):
    report,_=check(tmp_path,'def f():\n try:\n  x=1\n finally:\n  x=2\n return x\n')
    s=scope(report,'app.f')
    assert report['assurance']=='partial' and s['completeness']=='partial'
    assert any('Try_control_semantics_unsupported'==x['kind'] for x in s['gaps'])
    assert use(s,'x')['status']=='partial_unsupported_control'


def test_async_and_yield_are_marked_not_claimed_complete(tmp_path):
    report,_=check(tmp_path,'async def f(fetch):\n result=await fetch()\n return result\n')
    assert scope(report,'app.f')['completeness']=='partial'
    report,_=check(tmp_path,'def f():\n yield 1\n')
    assert report['assurance']=='partial'


def test_source_binding_rejects_changed_hash_and_source_membership(tmp_path):
    root=tmp_path/'src';root.mkdir();(root/'a.py').write_text('x=1\n')
    manifest,sources=inventory(root)
    with pytest.raises(ValueError,match='checksum'):
        analyze_snapshot({'a.py':b'x=2\n'},manifest)
    with pytest.raises(ValueError,match='membership'):
        analyze_snapshot({},manifest)
    assert analyze_snapshot(sources,manifest)[0]['sources']['a.py']==hashlib.sha256(sources['a.py']).hexdigest()


def test_budget_denial_never_returns_partial_graph(tmp_path):
    with pytest.raises(FlowLimitExceeded):
        check(tmp_path,'\n'.join('x=%d'%i for i in range(10))+'\n',max_points_per_scope=4)
    with pytest.raises(FlowLimitExceeded):
        check(tmp_path,'\n'.join('x=%d'%i for i in range(10))+'\n',max_total_points=5)


def test_repeat_is_deterministic_and_source_change_changes_identity(tmp_path):
    report,graph=check(tmp_path,'def f(x):\n y=x\n return y\n')
    report2,graph2=check(tmp_path,'def f(x):\n y=x\n return y\n')
    assert report==report2 and graph_fingerprint(graph)==graph_fingerprint(graph2)
    changed,_=check(tmp_path,'def f(x):\n y=x\n return y\n# revision\n')
    assert report['graph_fingerprint']!=changed['graph_fingerprint']


def test_source_scope_graph_integrity(tmp_path):
    report,graph=check(tmp_path,'def f(x):\n if x:\n  y=1\n return x\n')
    ids=[node.node_id for node in graph.nodes]
    assert len(ids)==len(set(ids))
    assert {e.source_id for e in graph.edges}|{e.target_id for e in graph.edges} <=set(ids)
    assert any(e.relation_type=='HAS_FLOW_SCOPE' for e in graph.edges)


def test_duplicate_same_named_functions_have_disjoint_occurrence_ids(tmp_path):
    report,_=check(tmp_path,'def f():\n x=1\ndef f():\n x=2\n')
    same=[s for s in report['scopes'] if s['scope']=='app.f']
    assert len(same)==2 and same[0]['scope_occurrence']!=same[1]['scope_occurrence']
    assert set(p['id'] for p in same[0]['control_points']).isdisjoint(p['id'] for p in same[1]['control_points'])


def test_no_execution_of_untrusted_source(tmp_path):
    marker=tmp_path/'executed'
    report,_=check(tmp_path, f'open({str(marker)!r},"w").write("bad")\n')
    assert not marker.exists()
    assert report['assurance']=='bounded_may_flow_only'


def test_sealed_report_replay_and_tamper(tmp_path):
    from audit_engine.semantic_audit.ae15.publication import audit_flow_repository, verify_flow_repository
    root=tmp_path/'src';root.mkdir();(root/'a.py').write_text('def f(x):\n if x:\n  y=3\n return x\n')
    output=tmp_path/'out'
    pub=audit_flow_repository(root,output)
    assert pub['verification']=='source_replayed_observations_only'
    assert verify_flow_repository(root,output)==pub
    generation=output/'generations'/pub['generation']
    blob=generation/'flow_report.json'
    blob.write_text(blob.read_text().replace('unverified_observation','validated'))
    with pytest.raises(ValueError,match='checksum'):verify_flow_repository(root,output)


def test_observation_publication_fails_closed_when_source_changes(tmp_path):
    from audit_engine.semantic_audit.ae15.publication import audit_flow_repository, verify_flow_repository
    root=tmp_path/'src';root.mkdir();file=root/'a.py';file.write_text('x=1\n')
    output=tmp_path/'out';audit_flow_repository(root,output)
    file.write_text('x=2\n')
    with pytest.raises(ValueError,match='source changed'):verify_flow_repository(root,output)


def test_no_output_inside_source_and_incomplete_input_has_failure_marker(tmp_path):
    from audit_engine.semantic_audit.ae15.publication import audit_flow_repository
    root=tmp_path/'src';root.mkdir();(root/'a.py').write_text('x=1\n')
    with pytest.raises(ValueError,match='outside'):audit_flow_repository(root,root/'output')
    empty=tmp_path/'empty';empty.mkdir();out=tmp_path/'out'
    with pytest.raises(ValueError,match='incomplete or empty'):audit_flow_repository(empty,out)
    assert json.loads((out/'LATEST.json').read_text())['status']=='failed'


def test_sealed_replay_fails_if_graph_semantics_forged_with_matching_hashes(tmp_path):
    # Rehashed malicious artifact is rejected through recomputation from source,
    # not simply an internal consistency check.
    from audit_engine.semantic_audit.ae15.publication import audit_flow_repository, verify_flow_repository
    from audit_engine.semantic_audit.ae01.publication import canonical, sha
    root=tmp_path/'src';root.mkdir();(root/'a.py').write_text('x=1\n')
    output=tmp_path/'out';pub=audit_flow_repository(root,output)
    folder=output/'generations'/pub['generation'];graphfile=folder/'graph.json'
    graph=json.loads(graphfile.read_text());graph['edges']=[]
    graphfile.write_bytes(canonical(graph))
    seal=json.loads((folder/'SEAL.json').read_bytes());seal['artifacts']['graph.json']=sha(graphfile.read_bytes())
    seal_bytes=canonical(seal);(folder/'SEAL.json').write_bytes(seal_bytes)
    latest=json.loads((output/'LATEST.json').read_text());latest['seal_sha256']=sha(seal_bytes)
    (output/'LATEST.json').write_bytes(canonical(latest))
    with pytest.raises(ValueError,match='graph replay'):verify_flow_repository(root,output)


def test_annotation_without_value_does_not_prove_binding(tmp_path):
    report,_=check(tmp_path,'def f():\n x: int\n return x\n')
    s=scope(report,'app.f')
    assert use(s,'x')['status']=='possibly_unbound'
    assert use(s,'x')['may_definitions']==[]


def test_augmented_assignment_reads_prior_binding(tmp_path):
    report,_=check(tmp_path,'def f():\n x+=1\n return x\n')
    s=scope(report,'app.f')
    assert use(s,'x',0)['status']=='possibly_unbound'
    assert names(s,use(s,'x',1))=={2}


def test_import_star_forces_incompleteness(tmp_path):
    report,_=check(tmp_path,'from values import *\nprint(value)\n')
    assert report['assurance']=='partial'
    assert any(i['kind']=='star_import_bindings_unresolved' for i in scope(report,'app')['gaps'])


def test_dynamic_exec_cannot_yield_clean_data_flow(tmp_path):
    report,_=check(tmp_path,'def f(command):\n exec(command)\n return value\n')
    s=scope(report,'app.f')
    assert report['assurance']=='partial'
    assert 'dynamic_namespace_or_reflection_unsupported' in {g['kind'] for g in s['gaps']}
    assert use(s,'value')['status']=='external_or_unknown_binding'


def test_async_for_is_not_claimed_to_be_synchronous_flow(tmp_path):
    report,_=check(tmp_path,'async def f(source):\n async for item in source:\n  print(item)\n')
    s=scope(report,'app.f')
    assert report['assurance']=='partial'
    assert 'AsyncFor_suspension_and_scheduler_unsupported' in {g['kind'] for g in s['gaps']}
