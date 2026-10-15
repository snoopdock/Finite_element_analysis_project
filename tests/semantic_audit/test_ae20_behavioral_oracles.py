"""Independent CPython behavior controls alongside conservative AE-14/15 facts.

These are curated synthetic examples, NOT historical repository defect cases.
The interpreter's behavior, not the analyzer's output, is the reference oracle.
"""
import symtable
from pathlib import Path
import pytest
from audit_engine.semantic_audit.ae01.source import inventory, extract
from audit_engine.semantic_audit.ae15.flow import analyze_snapshot


def _facts(tmp_path, code):
    root=tmp_path/'src';root.mkdir();(root/'sample.py').write_text(code,encoding='utf-8')
    manifest,sources=inventory(root)
    imports,calls,funcs,issues=extract(sources,manifest,{})
    return calls, analyze_snapshot(sources,manifest)[0]


def test_local_shadowing_observed_behavior_and_conservative_callee(tmp_path):
    code='def target():\n return 1\ndef work():\n target=lambda:2\n return target()\n'
    ns={};exec(compile(code,'controlled.py','exec'),ns)
    assert ns['target']()==1 and ns['work']()==2
    table=symtable.symtable(code,'controlled.py','exec')
    work=next(child for child in table.get_children() if child.get_name()=='work')
    assert work.lookup('target').is_local()
    calls,_=_facts(tmp_path,code)
    actual=next(c for c in calls if c['spelling']=='target')
    assert actual['resolution']=='unresolved' and actual['candidates']==[]


def test_python_shadowed_type_checking_executes_branch_without_false_type_guard(tmp_path):
    code='TYPE_CHECKING=True\nseen=[]\nif TYPE_CHECKING:\n seen.append(1)\n'
    state={};exec(compile(code,'controlled.py','exec'),state)
    assert state['seen']==[1]
    root=tmp_path/'src';root.mkdir();(root/'sample.py').write_text('TYPE_CHECKING=True\nif TYPE_CHECKING:\n import synthetic_dependency\n')
    m,s=inventory(root);imports,_,_,_=extract(s,m,{})
    target=next(i for i in imports if i['module']=='synthetic_dependency')
    assert target['context']==['conditional']


def test_possibly_unbound_variable_is_real_on_false_path(tmp_path):
    code='def calculate(flag):\n if flag:\n  x=1\n return x\n'
    ns={};exec(compile(code,'controlled.py','exec'),ns)
    assert ns['calculate'](True)==1
    with pytest.raises(UnboundLocalError): ns['calculate'](False)
    _, flow=_facts(tmp_path,code)
    scope=next(x for x in flow['scopes'] if x['scope']=='sample.calculate')
    candidate=next(x for x in scope['uses'] if x['name']=='x')
    assert candidate['status']=='possibly_unbound'
    assert flow['verified_findings']==[] if 'verified_findings' in flow else flow['assurance'] in ('bounded_may_flow_only','partial')


def test_corrected_branch_has_no_unbound_execution(tmp_path):
    code='def calculate(flag):\n if flag:\n  x=1\n else:\n  x=0\n return x\n'
    state={};exec(compile(code,'controlled.py','exec'),state)
    assert (state['calculate'](True),state['calculate'](False))==(1,0)
    _,flow=_facts(tmp_path,code)
    scope=next(x for x in flow['scopes'] if x['scope']=='sample.calculate')
    candidate=next(x for x in scope['uses'] if x['name']=='x')
    assert candidate['status']=='may_reach_definitions'


def test_loop_unknown_is_not_executable_proof(tmp_path):
    code='def first(values):\n for item in values:\n  result=item\n return result\n'
    state={};exec(compile(code,'controlled.py','exec'),state)
    assert state['first']([4])==4
    with pytest.raises(UnboundLocalError): state['first']([])
    _,flow=_facts(tmp_path,code)
    scope=next(x for x in flow['scopes'] if x['scope']=='sample.first')
    assert next(x for x in scope['uses'] if x['name']=='result')['status']=='possibly_unbound'


def test_unsupported_exception_flow_remains_partial(tmp_path):
    code='def calculate():\n try:\n  x=1\n finally:\n  x=2\n return x\n'
    state={};exec(compile(code,'controlled.py','exec'),state)
    assert state['calculate']()==2
    _,flow=_facts(tmp_path,code)
    assert flow['assurance']=='partial'
    assert any(s['completeness']=='partial' for s in flow['scopes'])
