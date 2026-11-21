#!/usr/bin/env python3
"""M7.3 independent verification of detached M7.2 backend artifacts."""
from __future__ import annotations
import argparse, hashlib, json, re
from collections import defaultdict
from pathlib import Path
from tools import gb06_task_suitability_campaign as m72

BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")
WORKFLOW = "AE-32C M7.2 Task-Suitability Workload Campaign"
ARTIFACT_RE = re.compile(r"^m7-2-task-suitability-(networkx|scipy|igraph|graph-tool|snap)-(\d+)-(\d+)$")
KEYS = {"schema_version","status","backend","native_query_mode","task_scope","configuration","cases","environment","provenance","authority","interpretation","report_sha256"}

class DossierError(ValueError): pass

def require(ok, code):
    if not ok: raise DossierError(code)

def read_json(path):
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc: raise DossierError("invalid_json:"+path.name) from exc
    require(isinstance(value,dict),"json_root_invalid:"+path.name)
    return value

def file_sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def last_json(path):
    lines=[x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    require(bool(lines),"empty_verify_log:"+path.name)
    try: value=json.loads(lines[-1])
    except Exception as exc: raise DossierError("verify_log_not_json:"+path.name) from exc
    require(isinstance(value,dict),"verify_log_root_invalid")
    return value

def index_artifacts(manifest,run_id,attempt):
    require(manifest.get("run_id")==run_id,"manifest_run_id_mismatch")
    items=manifest.get("artifacts")
    require(isinstance(items,list) and len(items)==5,"manifest_requires_five_artifacts")
    out={}
    ids=set()
    controller=set()
    for item in items:
        require(isinstance(item,dict),"manifest_entry_invalid")
        match=ARTIFACT_RE.fullmatch(item.get("name",""))
        require(match is not None,"artifact_name_invalid")
        backend,nrun,nattempt=match.groups()
        require(int(nrun)==run_id and int(nattempt)==attempt,"artifact_name_run_attempt_mismatch")
        require(backend not in out,"duplicate_backend_artifact")
        aid=item.get("id")
        require(type(aid) is int and aid>0 and aid not in ids,"artifact_id_invalid")
        ids.add(aid)
        require(item.get("expired") is False,"artifact_expired")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}",item.get("digest","")) is not None,"artifact_digest_invalid")
        wr=item.get("workflow_run",{})
        require(wr.get("id")==run_id and wr.get("head_branch")=="main","artifact_run_binding_invalid")
        require(re.fullmatch(r"[0-9a-f]{40}",wr.get("head_sha","")) is not None,"controller_sha_invalid")
        controller.add(wr["head_sha"])
        out[backend]=item
    require(set(out)==set(BACKENDS),"backend_artifact_set_incomplete")
    require(len(controller)==1,"mixed_controller_revisions")
    return out

def verify_campaign(artifact_dir,manifest,run_id,attempt,source_revision):
    require(re.fullmatch(r"[0-9a-f]{40}",source_revision or "") is not None,"source_revision_invalid")
    artifacts=index_artifacts(manifest,run_id,attempt)
    reports={}
    records=[]
    for backend in BACKENDS:
        item=artifacts[backend]
        backend_dir = artifact_dir/backend if (artifact_dir/backend).is_dir() else artifact_dir
        report_root = backend_dir/"reports" if (backend_dir/"reports").is_dir() else backend_dir
        rp=report_root/f"m7-2-{backend}.json"
        lp=report_root/f"m7-2-{backend}-run.log"
        vp=report_root/f"m7-2-{backend}-verify.log"
        ep=report_root/"runner-environment.txt"
        for p in (rp,lp,vp,ep): require(p.is_file(),"artifact_file_missing:"+backend+":"+p.name)
        report=read_json(rp)
        require(set(report)==KEYS,"report_schema_keys_invalid:"+backend)
        require(report.get("backend")==backend,"backend_identity_mismatch:"+backend)
        prov=report.get("provenance",{})
        require(prov.get("source_revision")==source_revision,"source_revision_mismatch:"+backend)
        require(str(prov.get("workflow_run_id"))==str(run_id),"report_run_id_mismatch:"+backend)
        require(str(prov.get("workflow_run_attempt"))==str(attempt),"report_attempt_mismatch:"+backend)
        require(prov.get("workflow_name")==WORKFLOW,"workflow_name_mismatch:"+backend)
        verified=m72.verify_report(report)
        run_result=last_json(lp)
        log=last_json(vp)
        for evidence_log in (run_result,log):
            require(evidence_log.get("status")=="verified" and evidence_log.get("backend")==backend and evidence_log.get("report_sha256")==report.get("report_sha256"),"detached_run_or_verify_log_mismatch:"+backend)
        require(verified.get("report_sha256")==report.get("report_sha256"),"report_verification_mismatch:"+backend)
        cfg=report["configuration"]
        require(cfg.get("workload_ids")==list(m72.WORKLOADS),"workload_coverage_incomplete:"+backend)
        require(cfg.get("case_count")==len(m72.WORKLOADS)*len(cfg.get("seeds",[])),"case_matrix_incomplete:"+backend)
        reports[backend]=report
        backend_env=report["cases"][0]["environment"]
        records.append({"backend":backend,"artifact_id":item["id"],"artifact_name":item["name"],"artifact_sha256":item["digest"][7:],"report_sha256":report["report_sha256"],"report_file_sha256":file_sha(rp),"verify_log_sha256":file_sha(vp),"run_log_sha256":file_sha(lp),"backend_library":backend_env.get("backend_library"),"backend_library_version":backend_env.get("backend_library_version"),"projection_type":backend_env.get("projection_type"),"worker":backend_env.get("worker")})
    base=reports[BACKENDS[0]]
    cfg=base["configuration"]
    maps={}
    env_groups=defaultdict(list)
    for backend,report in reports.items():
        require(report["configuration"]==cfg,"cross_backend_configuration_mismatch:"+backend)
        require(report["task_scope"]==base["task_scope"],"cross_backend_scope_mismatch:"+backend)
        require(report["authority"]==m72.AUTHORITY,"authority_boundary_invalid:"+backend)
        require(report["native_query_mode"]==m72.NATIVE_MODES[backend],"native_mode_invalid:"+backend)
        require(report["provenance"]["source_revision"]==source_revision,"mixed_source_revision:"+backend)
        mapping={}
        for case in report["cases"]:
            key=(case["workload"]["id"],case["workload"]["seed"])
            require(key not in mapping,"duplicate_case:"+backend)
            mapping[key]=case
        maps[backend]=mapping
        env=report["environment"]
        ekey=json.dumps({k:env.get(k) for k in ("python","platform","machine")},sort_keys=True)
        env_groups[ekey].append(backend)
    expected={(w,s) for w in cfg["workload_ids"] for s in cfg["seeds"]}
    for backend,mapping in maps.items(): require(set(mapping)==expected,"workload_seed_matrix_mismatch:"+backend)
    parity_cases=parity_queries=native_queries=timed=warmup=0
    for backend in BACKENDS:
        for key in sorted(expected):
            case=maps[backend][key]
            base_case=maps[BACKENDS[0]][key]
            wm=case["workload"]; bw=base_case["workload"]
            require(wm["graph_sha256"]==bw["graph_sha256"] and wm["graph_fingerprint"]==bw["graph_fingerprint"],"cross_backend_graph_identity_mismatch:"+backend)
            bq={q["query_id"]:q["result_sha256"] for q in base_case["measurements"]["queries"]}
            for q in case["measurements"]["queries"]:
                require(q["result_sha256"]==bq.get(q["query_id"]),"cross_backend_result_mismatch:"+backend)
                n=q["native_metrics_delta"].get("native_adjacency_lookups")
                require(type(n) is int and n>=cfg["repeats"],"native_telemetry_missing:"+backend)
                native_queries+=1
                timed+=q["measured_calls"]; warmup+=q["warmup_calls"]
            ex=case["native_execution"]
            require(ex["native_query_mode"]==m72.NATIVE_MODES[backend],"case_native_mode_mismatch:"+backend)
            require(ex["preflight_parity_failures"]==0,"parity_failure:"+backend)
            require(ex["preflight_parity_queries"]==5,"parity_query_count_invalid:"+backend)
            parity_cases+=1; parity_queries+=ex["preflight_parity_queries"]
    query_count=len(expected)*5
    require(timed==query_count*cfg["repeats"]*5,"timed_observation_total_mismatch")
    require(warmup==query_count*cfg["warmup"]*5,"warmup_observation_total_mismatch")
    controller_sha=next(iter(artifacts.values()))["workflow_run"]["head_sha"]
    return {
      "schema_version":"ae32c/m7-campaign-dossier/v1","status":"verified",
      "campaign":{"workflow_run_id":run_id,"workflow_run_attempt":attempt,"workflow_name":WORKFLOW,"source_revision":source_revision,"workflow_controller_revision":controller_sha,"backends":list(BACKENDS),"seeds":cfg["seeds"],"repeats_per_query":cfg["repeats"],"warmup_calls_per_query":cfg["warmup"],"workload_ids":cfg["workload_ids"],"case_count_per_backend":len(expected),"query_records_per_backend":query_count,"timed_observations_total":timed,"warmup_observations_total":warmup,"preflight_parity_cases":parity_cases,"preflight_parity_queries":parity_queries,"native_query_records":native_queries},
      "environment_strata":[{"environment":json.loads(k),"backends":sorted(v)} for k,v in sorted(env_groups.items())],
      "artifacts":records,
      "interpretation":{"computational_options_not_competitors":True,"cross_environment_timing_ranking_permitted":False,"performance_winner_established":False,"task_suitability_decision_established":False,"backend_auto_selection_permitted":False,"scientific_approval_permitted":False,"graph_mutation_permitted":False,"production_approval":False,"scope":"bounded semantic graph traversal only"}
    }

def markdown(d):
    c=d["campaign"]
    out=["# AE-32C M7.3 — Independent Campaign Evidence Dossier","",f"Status: {d['status']}",f"Campaign run: https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/{c['workflow_run_id']}",f"Attempt: {c['workflow_run_attempt']}",f"Stage1 source: {c['source_revision']}",f"Workflow controller: {c['workflow_controller_revision']}","","## Campaign contract",f"- Backends: {', '.join(c['backends'])}",f"- Workloads: {', '.join(c['workload_ids'])}",f"- Seeds: {c['seeds']}",f"- Repetitions / warm-up: {c['repeats_per_query']} / {c['warmup_calls_per_query']}",f"- Cases per backend: {c['case_count_per_backend']}",f"- Query records per backend: {c['query_records_per_backend']}",f"- Timed observations total: {c['timed_observations_total']}",f"- Warm-up observations total: {c['warmup_observations_total']}",f"- Preflight parity: {c['preflight_parity_cases']} cases, {c['preflight_parity_queries']} queries, zero failures","","## Environment strata","","| Backends | Python | Platform | Machine |","|---|---|---|---|"]
    for g in d["environment_strata"]:
        e=g["environment"]; out.append(f"| {', '.join(g['backends'])} | {e['python']} | {e['platform']} | {e['machine']} |")
    out += ["","Runner environments are disclosed separately. Timings are descriptive and are not pooled or ranked across backends.","","## Artifact identities","","| Backend | Artifact ID | Artifact SHA-256 | Report SHA-256 |","|---|---:|---|---|"]
    for a in d["artifacts"]: out.append(f"| {a['backend']} | {a['artifact_id']} | {a['artifact_sha256']} | {a['report_sha256']} |")
    out += ["","## Conclusions","",
      "- All five expected artifacts were present, unexpired and bound to the campaign run, attempt and one workflow-controller revision.",
      "- Each report passed the M7.2 verifier; detached verification logs agreed with report digests.",
      "- All reports used the same Stage1 source, seeds, workloads, repetitions and warm-up configuration.",
      "- Graph digests/fingerprints and corresponding query-result digests matched across all five backends.",
      "- Preflight parity failures were zero; native query modes and adjacency telemetry were present.",
      "- Timing aggregates and sample counts were checked by the per-report verifier.",
      "- The libraries remain computational options, not competitors. No universal winner, global ranking or automatic selector is established.",
      "",
      "Scope is bounded semantic graph traversal only. This does not qualify sparse numerical linear algebra, solvers, centrality, community detection, ontology reasoning or end-to-end repository evidence reconstruction.",
      "",
      "production_approval=false; scientific approval, graph mutation and task-suitability decisions remain unauthorized.",""]
    return "\n".join(out)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-dir",type=Path,required=True); p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--run-id",type=int,required=True); p.add_argument("--attempt",type=int,required=True)
    p.add_argument("--source-revision",required=True); p.add_argument("--output-dir",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        d=verify_campaign(a.artifact_dir,read_json(a.manifest),a.run_id,a.attempt,a.source_revision)
        a.output_dir.mkdir(parents=True,exist_ok=True)
        (a.output_dir/"m7-3-dossier.json").write_text(json.dumps(d,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        (a.output_dir/"m7-3-dossier.md").write_text(markdown(d),encoding="utf-8")
        print(json.dumps({"status":"verified","run_id":a.run_id,"source_revision":a.source_revision},sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__,"error":str(exc)},sort_keys=True))
        return 1

if __name__=="__main__": raise SystemExit(main())
