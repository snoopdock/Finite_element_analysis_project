"""Snapshot-bound extractor execution evidence for M7.5.13."""
from __future__ import annotations
import ast, hashlib, json
from pathlib import Path
from collections.abc import Mapping
from typing import Any
from ..extractors.ast_extractor import ASTExtractor
from ..extractors.workflow_extractor import WorkflowLexicalExtractor
from .source_inventory import verify_source_extractor_inventory, SourceExtractorInventoryError
SCHEMA="ae32c/extractor-execution-report/v1"
class ExtractorExecutionError(ValueError): pass
def _canonical(x): return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def _hash(x): return hashlib.sha256(_canonical(x)).hexdigest()
def _raw_hash(x): return hashlib.sha256(x).hexdigest()
def extractor_executor_registry():
    p={"schema":"ae32c/extractor-executor-registry/v1","registry_id":"ae32c-built-in-extractor-executor-registry","version":"1.0.0","executors":[
    {"extractor_id":"python_ast","candidate_version":"1.0.0","implementation":"ASTExtractor.extract_source","implementation_version":"1.0.0","contract":"parse exact hashed bytes; never execute source"},
    {"extractor_id":"workflow_static_scan","candidate_version":"1.0.0","implementation":"WorkflowLexicalExtractor.extract_source","implementation_version":"1.0.0","contract":"UTF-8 lexical observations only; no YAML semantic validation"}]}
    return {**p,"registry_sha256":_hash(p)}
def _json(x):
    if hasattr(x,"__dataclass_fields__"): return {k:_json(v) for k,v in vars(x).items()}
    if isinstance(x,(tuple,list)): return [_json(v) for v in x]
    if isinstance(x,dict): return {str(k):_json(v) for k,v in x.items()}
    return x
def _outcome(c,root,max_bytes,max_nodes):
    base={k:c[k] for k in ("candidate_id","source_snapshot_id","source_path","source_content_sha256","extractor_id","extractor_version")}
    def done(status,code,diagnostic=None,result=None):
        row={**base,"status":status,"diagnostic_code":code,"diagnostic":diagnostic,"result":result,"result_sha256":_hash(result) if result is not None else None}
        return {**row,"outcome_id":_hash(row)}
    if c.get("status")=="DECLARED_EXCLUDED": return done("SKIPPED_EXPLICIT_EXCLUSION","declared_scope_exclusion",c.get("exclusion_reason"))
    path=c["source_path"]; parts=path.split("/")
    if not path or path.startswith("/") or "\\" in path or any(p in {"",".",".."} for p in parts): return done("UNSUPPORTED_INPUT","unsafe_relative_source_path")
    target=root.joinpath(*parts)
    try:
        if target.is_symlink(): return done("UNSUPPORTED_INPUT","symbolic_link_source_not_followed")
        resolved=target.resolve(strict=True); resolved.relative_to(root)
        if not resolved.is_file(): return done("UNSUPPORTED_INPUT","source_not_regular_file")
        raw=resolved.read_bytes()
    except (OSError,ValueError): return done("UNSUPPORTED_INPUT","source_unavailable_or_outside_checkout")
    if len(raw)>max_bytes: return done("RESOURCE_LIMIT","source_byte_limit_exceeded")
    if _raw_hash(raw)!=c["source_content_sha256"]: return done("FAILED","source_content_digest_mismatch")
    try:
        if c["extractor_id"]=="python_ast" and c["extractor_version"]=="1.0.0":
            imports,symbols=ASTExtractor().extract_source(raw,path); tree=ast.parse(raw,filename=path)
            count=sum(1 for _ in ast.walk(tree))
            if count>max_nodes: return done("RESOURCE_LIMIT","ast_node_limit_exceeded")
            result={"imports":_json(imports),"symbols":_json(symbols),"ast_node_count":count}
        elif c["extractor_id"]=="workflow_static_scan" and c["extractor_version"]=="1.0.0":
            result={"observations":WorkflowLexicalExtractor().extract_source(raw,path),"interpretation_boundary":"lexical_only_not_yaml_validation"}
        else: return done("UNSUPPORTED_EXECUTOR","no_compatible_executor_registered")
    except SyntaxError as exc: return done("FAILED","source_parse_failed",{"exception_type":"SyntaxError","line":exc.lineno,"offset":exc.offset,"message":exc.msg})
    except UnicodeDecodeError: return done("UNSUPPORTED_INPUT","source_encoding_unsupported")
    except Exception as exc: return done("FAILED","extractor_exception",{"exception_type":type(exc).__name__})
    return done("EXECUTED",None,None,result)
def build_extractor_execution_report(source_manifest:Mapping[str,Any],inventory:Mapping[str,Any],repository_root:str|Path,*,max_source_bytes:int=1_000_000,max_ast_nodes:int=100_000):
    for name,value in (("max_source_bytes",max_source_bytes),("max_ast_nodes",max_ast_nodes)):
        if isinstance(value,bool) or not isinstance(value,int) or value<1: raise ExtractorExecutionError(name+"_must_be_positive_integer")
    try: verify_source_extractor_inventory(source_manifest,inventory)
    except SourceExtractorInventoryError as exc: raise ExtractorExecutionError("source_inventory_verification_failed:"+str(exc)) from exc
    root=Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ExtractorExecutionError("repository_root_not_directory")
    registry=extractor_executor_registry()
    if registry["registry_sha256"]!=_hash({k:v for k,v in registry.items() if k!="registry_sha256"}): raise ExtractorExecutionError("executor_registry_integrity_failure")
    candidates=[{**x,"source_snapshot_id":source_manifest["source_snapshot_id"]} for x in inventory["extractor_candidates"]]
    outcomes=sorted([_outcome(x,root,max_source_bytes,max_ast_nodes) for x in candidates],key=lambda x:(x["source_path"],x["extractor_id"],x["candidate_id"]))
    ids=[x["candidate_id"] for x in candidates]; got=[x["candidate_id"] for x in outcomes]
    reconciled=len(ids)==len(got) and len(set(ids))==len(ids) and sorted(ids)==sorted(got)
    counts={}
    for x in outcomes: counts[x["status"]]=counts.get(x["status"],0)+1
    executed=counts.get("EXECUTED",0); total=len(candidates)
    state="NO_CANDIDATES" if not total else "ALL_EXECUTED" if executed==total else "PARTIAL" if executed else "NONE_EXECUTED"
    p={"schema":SCHEMA,"source_snapshot_id":source_manifest["source_snapshot_id"],"source_manifest_sha256":source_manifest["manifest_sha256"],"inventory_sha256":inventory["inventory_sha256"],"executor_registry_id":registry["registry_id"],"executor_registry_version":registry["version"],"executor_registry_sha256":registry["registry_sha256"],"limits":{"max_source_bytes":max_source_bytes,"max_ast_nodes":max_ast_nodes},"candidate_count":total,"outcome_count":len(outcomes),"outcome_counts":dict(sorted(counts.items())),"outcomes":outcomes,"reconciliation":{"status":"RECONCILED" if reconciled else "UNRECONCILED","every_candidate_has_exactly_one_outcome":reconciled},"execution_status":state,"authority":{"source_code_executed":False,"extractor_code_executed":True,"all_candidates_successfully_executed":state=="ALL_EXECUTED","yaml_semantics_validated":False,"graph_completeness_established":False,"proposition_truth_established":False,"audit_decision_authority":False,"production_approval":False}}
    return {**p,"report_sha256":_hash(p)}
def verify_extractor_execution_report(source_manifest,inventory,report,repository_root):
    if not isinstance(report,Mapping): raise ExtractorExecutionError("execution_report_must_be_an_object")
    submitted=dict(report); digest=submitted.get("report_sha256"); p={k:v for k,v in submitted.items() if k!="report_sha256"}
    if not isinstance(digest,str) or digest!=_hash(p): raise ExtractorExecutionError("execution_report_digest_mismatch")
    limits=submitted.get("limits")
    if not isinstance(limits,Mapping): raise ExtractorExecutionError("execution_report_limits_missing")
    expected=build_extractor_execution_report(source_manifest,inventory,repository_root,max_source_bytes=limits.get("max_source_bytes"),max_ast_nodes=limits.get("max_ast_nodes"))
    if _canonical(expected)!=_canonical(submitted): raise ExtractorExecutionError("execution_report_semantic_replay_mismatch")
    return {"report_sha256":digest,"semantic_integrity":True,"replay_performed":True,"replay_matches":True,"candidate_count":expected["candidate_count"],"outcome_count":expected["outcome_count"],"execution_status":expected["execution_status"],"outcome_counts":expected["outcome_counts"],"all_candidates_accounted_for":expected["reconciliation"]["every_candidate_has_exactly_one_outcome"],"source_code_executed":False}
