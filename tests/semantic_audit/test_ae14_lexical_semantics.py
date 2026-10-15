"""Independent lexical counterexamples from Audit Engine deep review Pass 3.

Static candidates never prove actual Python runtime execution.
"""
from pathlib import Path
import hashlib
import json

import pytest

from audit_engine.semantic_audit.ae01.source import extract, inventory
from audit_engine.semantic_audit.ae01.pipeline import _graph
from audit_engine.semantic_audit.ae01.publication import verify


def facts(tmp_path, source, path='sample.py'):
    root=tmp_path/'src'
    root.mkdir(exist_ok=True)
    file=root/path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source,encoding='utf-8')
    manifest, files=inventory(root)
    imports,calls,functions,issues=extract(files,manifest,{})
    return imports,calls,functions,issues,manifest,files


def call(calls, spelling, occurrence=0):
    matches=[x for x in calls if x['spelling']==spelling]
    assert len(matches)>occurrence, (spelling,calls)
    return matches[occurrence]


def test_locally_shadowed_name_never_binds_module_function(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'def target(): pass\ndef f():\n target=lambda: 1\n return target()\n')
    c=call(calls,'target')
    assert c['resolution']=='unresolved' and c['candidates']==[]
    assert c['binding_reason']=='local_or_enclosing_shadow' and c['scope']=='sample.f'


def test_function_local_binding_prevents_false_global_even_before_assignment(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'def target(): pass\ndef f():\n target()\n target=lambda:2\n')
    assert call(calls,'target')['resolution']=='unresolved'


def test_nested_definition_uses_closest_lexical_identity(tmp_path):
    _,calls,functions,_,_,_=facts(tmp_path,'def target(): pass\ndef parent():\n def target(): pass\n target()\n')
    c=call(calls,'target')
    assert c['resolution']=='candidate' and c['candidates']==['sample.parent.target']
    assert {f['qualified_name'] for f in functions}=={'sample.target','sample.parent','sample.parent.target'}
    inner=next(f for f in functions if f['qualified_name']=='sample.parent.target')
    assert inner['owner_scope']=='sample.parent'


def test_distinct_same_named_class_methods_not_file_global_callees(tmp_path):
    _,calls,funcs,_,m,s=facts(tmp_path,'class A:\n def run(self):pass\nclass B:\n def run(self):pass\nobj.run()\n')
    assert {f['qualified_name'] for f in funcs}=={'sample.A.run','sample.B.run'}
    assert call(calls,'obj.run')['resolution']=='unresolved'
    g=_graph(m,s,[],calls,funcs,{})
    defs=[e for e in g.edges if e.relation_type=='DEFINES']
    assert len({e.source_id for e in defs})==2
    assert any('sample.A@' in e.source_id for e in defs)
    assert any('sample.B@' in e.source_id for e in defs)
    assert not any(e.relation_type=='CALLS' for e in g.edges)


def test_class_scope_is_not_inherited_implicitly_into_method(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'def target(): pass\nclass Box:\n def target(): pass\n def f(self): return target()\n')
    assert call(calls,'target')['candidates']==['sample.target']


def test_global_and_nonlocal_bindings(tmp_path):
    text='def target():pass\ndef outer():\n def target():pass\n def inner():\n  nonlocal target\n  return target()\ndef other():\n global target\n return target()\n'
    _,calls,_,_,_,_=facts(tmp_path,text)
    assert call(calls,'target',0)['candidates']==['sample.outer.target']
    assert call(calls,'target',1)['candidates']==['sample.target']


def test_lambda_parameter_and_comprehension_scope_do_not_escape(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'def func(): pass\nx=lambda func:func()\ny=[func() for func in (lambda:1,)]\nfunc()\n')
    assert call(calls,'func',0)['resolution']=='unresolved'
    assert call(calls,'func',1)['resolution']=='unresolved'
    assert call(calls,'func',2)['candidates']==['sample.func']


def test_alias_reassignment_invalidates_dynamic_import_heuristic(tmp_path):
    imps,calls,_,_,_,_=facts(tmp_path,'import importlib as lib\nlib=object()\nlib.import_module("fake.module")\n')
    assert call(calls,'lib.import_module')['dynamic_import'] is False
    assert not any(i['form']=='dynamic_literal' for i in imps)


def test_original_import_module_alias_literal_is_recognized(tmp_path):
    imps,calls,_,_,_,_=facts(tmp_path,'import importlib as lib\nlib.import_module("pkg.child")\n')
    assert call(calls,'lib.import_module')['dynamic_import'] is True
    assert any(i['form']=='dynamic_literal' and i['module']=='pkg.child' for i in imps)


def test_import_from_alias_and_shadow(tmp_path):
    imports,calls,_,_,_,_=facts(tmp_path,'from importlib import import_module as load\nload("pkg.child")\ndef f(load):\n load("somewhere")\n')
    assert call(calls,'load',0)['dynamic_import'] is True
    assert call(calls,'load',1)['dynamic_import'] is False
    assert len([i for i in imports if i['form']=='dynamic_literal'])==1


def test_unbound_and_rebound_builtin_import(tmp_path):
    imp,calls,_,_,_,_=facts(tmp_path,'__import__("pkg")\ndef f(__import__):\n __import__("bad")\n')
    assert call(calls,'__import__',0)['dynamic_import']
    assert not call(calls,'__import__',1)['dynamic_import']
    assert len([x for x in imp if x['form']=='dynamic_literal'])==1


def test_type_checking_must_be_actual_typing_import(tmp_path):
    text='TYPE_CHECKING=True\nif TYPE_CHECKING:\n import alpha\nfrom typing import TYPE_CHECKING as TC\nif TC:\n import beta\n'
    imps,_,_,_,_,_=facts(tmp_path,text)
    alpha=next(x for x in imps if x['module']=='alpha')
    beta=next(x for x in imps if x['module']=='beta')
    assert alpha['context']==['conditional']
    assert beta['context']==['type_checking']


def test_type_checking_import_rebinding_invalidates_guard(tmp_path):
    text='from typing import TYPE_CHECKING\nTYPE_CHECKING=True\nif TYPE_CHECKING:\n import alpha\n'
    imps,_,_,_,_,_=facts(tmp_path,text)
    assert next(x for x in imps if x['module']=='alpha')['context']==['conditional']


def test_typing_module_alias_guard_supported(tmp_path):
    imps,_,_,_,_,_=facts(tmp_path,'import typing as t\nif t.TYPE_CHECKING:\n import ghost\n')
    assert next(x for x in imps if x['module']=='ghost')['context']==['type_checking']


def test_namespace_parent_not_mislabeled_external(tmp_path):
    root=tmp_path/'src';(root/'ns').mkdir(parents=True)
    (root/'ns'/'child.py').write_text('x=1\n')
    (root/'consumer.py').write_text('import ns\nfrom ns import child\n')
    m,s=inventory(root)
    imps,_,_,issues=extract(s,m,{})
    assert imps[0]['status']=='unresolved' and imps[0]['reason']=='possible_namespace_package'
    assert imps[1]['status']=='internal' and imps[1]['target']=='ns.child'
    assert any(i['kind']=='unresolved_import' for i in issues)


def test_conditional_import_alias_does_not_claim_stable_callee(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'if condition:\n import importlib as alias\nalias.import_module("pkg")\n')
    assert not call(calls,'alias.import_module')['dynamic_import']


def test_pattern_target_shadows_function(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'def target():pass\nmatch obj:\n case target: pass\ntarget()\n')
    assert call(calls,'target')['resolution']=='unresolved'


def test_multiple_bindings_are_ambiguous(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'def task():pass\ndef task():pass\ntask()\n')
    c=call(calls,'task')
    assert c['resolution']=='unresolved' and c['binding_reason']=='ambiguous_or_conditional_binding'


def test_source_graph_has_scope_ownership_and_no_runtime_edge(tmp_path):
    i,c,f,_,m,s=facts(tmp_path,'def outer():\n def inner(): pass\n inner()\n')
    graph=_graph(m,s,i,c,f,{})
    fn=next(x for x in f if x['name']=='inner')
    owner=next(n.node_id for n in graph.nodes if n.entity_type=='LexicalScope' and n.attributes.get('qualified_name')=='sample.outer')
    assert any(e.relation_type=='DEFINES' and e.source_id==owner and e.target_id==fn['id'] for e in graph.edges)
    assert any(e.relation_type=='HAS_CALL' and e.source_id==owner for e in graph.edges)
    assert not any(e.relation_type in ('CALLS','EXECUTED_CALL') for e in graph.edges)


def test_deterministic_extraction_and_revision_sensitive_source(tmp_path):
    i,c,f,issues,m,s=facts(tmp_path,'def outer():\n def inner():pass\n inner()\n')
    assert (i,c,f,issues)==extract(s,m,{})
    assert len({x['id'] for x in [*i,*c,*f]})==len([*i,*c,*f])
    source=tmp_path/'src'/'sample.py'
    oldhash=hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text(source.read_text()+'# changed\n')
    m2,s2=inventory(tmp_path/'src')
    assert m2['files'][0]['sha256']!=oldhash


def test_end_to_end_type_checking_shadow_not_incorrectly_tagged(tmp_path):
    from audit_engine.semantic_audit.ae01.pipeline import audit_repository
    from audit_engine.semantic_audit.ae01.publication import verify
    repo=tmp_path/'src';repo.mkdir()
    (repo/'prod.py').write_text('TYPE_CHECKING=True\nif TYPE_CHECKING:\n import exp\n')
    (repo/'exp.py').write_text('')
    policy=Path(__file__).parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
    assert policy.is_file(), str(policy)
    output=tmp_path/'output'
    result=audit_repository(repo,output,lifecycle={'prod':'production','exp':'experimental'},policy_file=policy)
    assert result['report']['assurance_completeness']=='inconclusive'
    rows=json.loads((output/'generations'/result['report']['run_id']/'source_facts.json').read_text())
    assert next(x for x in rows['imports'] if x['module']=='exp')['context']==['conditional']
    assert not any(i['kind']=='type_checking_only_dependency' for i in result['report']['issues'])
    assert verify(output)['generation']==result['report']['run_id']


def test_function_local_import_is_deferred_not_unconditional(tmp_path):
    imps,calls,_,_,_,_=facts(tmp_path,'def unused():\n import sample_internal\n')
    assert next(i for i in imps if i['module']=='sample_internal')['context']==['deferred_function']


def test_decorator_and_default_are_definition_time_expressions(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'@decorate()\ndef f(value=compute()):\n return execute()\n')
    assert call(calls,'decorate')['context']==[]
    assert call(calls,'compute')['context']==[]
    assert call(calls,'execute')['context']==['deferred_function']


def test_lambda_default_vs_body_phase(tmp_path):
    _,calls,_,_,_,_=facts(tmp_path,'f=lambda x=choose(): evaluate(x)\n')
    assert call(calls,'choose')['context']==[]
    assert call(calls,'evaluate')['context']==['deferred_lambda']


def test_scoping_matches_cpython_symbol_table(tmp_path):
    import symtable
    text='''value=1\ndef f(x):\n    value=x\n    def g():\n        return value\n    return g()\n'''
    st=symtable.symtable(text,'sample.py','exec')
    f=next(c for c in st.get_children() if c.get_name()=='f')
    g=next(c for c in f.get_children() if c.get_name()=='g')
    assert f.lookup('value').is_local() and g.lookup('value').is_free()
    _,calls,funcs,_,_,_=facts(tmp_path,text)
    assert call(calls,'g')['candidates']==['sample.f.g']
    assert next(x for x in funcs if x['name']=='g')['owner_scope']=='sample.f'


def test_unexecuted_function_import_prevents_false_clean_report(tmp_path):
    from audit_engine.semantic_audit.ae01.pipeline import audit_repository
    policy=Path(__file__).parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
    source=tmp_path/'src'; source.mkdir()
    (source/'prod.py').write_text('def optional():\n import stable\n')
    (source/'stable.py').write_text('')
    result=audit_repository(source,tmp_path/'out',lifecycle={'prod':'production','stable':'stable'},policy_file=policy)
    assert result['report']['verified_compliance'] is False
    assert result['report']['assurance_completeness']=='inconclusive'
    assert any(i['kind']=='conditional_dependency' for i in result['report']['issues'])


def test_implicit_namespace_import_yields_inconclusive_not_external_clean(tmp_path):
    from audit_engine.semantic_audit.ae01.pipeline import audit_repository
    policy=Path(__file__).parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
    source=tmp_path/'src'; (source/'ns').mkdir(parents=True)
    (source/'ns'/'child.py').write_text('')
    (source/'prod.py').write_text('import ns\n')
    r=audit_repository(source,tmp_path/'out',lifecycle={'prod':'production','ns.child':'stable'},policy_file=policy)['report']
    assert r['assurance_completeness']=='inconclusive'
    assert not r['verified_compliance']
    assert any(x['kind']=='unresolved_import' for x in r['issues'])


def test_new_lexical_version_changes_source_audit_identity(tmp_path):
    from audit_engine.semantic_audit.ae01.pipeline import audit_repository
    policy=Path(__file__).parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
    source=tmp_path/'src'; source.mkdir()
    (source/'prod.py').write_text('import stable\n')
    (source/'stable.py').write_text('')
    report=audit_repository(source,tmp_path/'out',lifecycle={'prod':'production','stable':'stable'},policy_file=policy)['report']
    cfg=json.loads((tmp_path/'out'/'generations'/report['run_id']/'policy.json').read_text())['configuration']
    assert cfg['version']=='ae01/v1+ae14-lexical-1'
    from audit_engine.semantic_audit.ae01.publication import canonical, sha
    older=dict(cfg,version='ae01/v1')
    assert ('ae01-'+sha(canonical([report['source_digest'],older]))[:32])!=report['run_id']


def test_redefined_class_occurrences_are_distinct_graph_scopes(tmp_path):
    i,c,f,_,m,s=facts(tmp_path,'class A:\n def run(self):pass\nclass A:\n def run(self):pass\n')
    graph=_graph(m,s,i,c,f,{})
    definitions=[e for e in graph.edges if e.relation_type=='DEFINES']
    assert len(definitions)==2
    assert len({e.source_id for e in definitions})==2
    assert all('sample.A@' in e.source_id for e in definitions)
    assert len({x['id'] for x in f})==2
