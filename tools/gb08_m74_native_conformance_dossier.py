#!/usr/bin/env python3
"""Detached SHA-256 and semantic verifier for M7 E.8.5/E.8.8 artifacts."""
from __future__ import annotations
import argparse, hashlib, json, re, stat, sys, zipfile
from pathlib import Path

RUN, ATTEMPT = 45395352748, 1
SOURCE = "51d025fd328b00a59988a05fe72d9092262434f5"
WORKFLOW = "AE-32C Native Graph Backend Conformance (E.8.5 / E.8.8)"
BACKENDS = ("networkx", "scipy", "igraph", "graph-tool", "snap")
ARTIFACTS = {"networkx":"e85-networkx-conformance", "scipy":"e85-scipy-conformance",
 "igraph":"e85-igraph-conformance", "graph-tool":"e85-graph-tool-conformance",
 "snap":"e85-e88-snap-isolated-worker"}
MODES = {"networkx":"networkx_successor_predecessor_adjacency", "scipy":"scipy_csr_csc_adjacency",
 "igraph":"igraph_incident_edge_ids", "graph-tool":"graph_tool_vertex_edge_iterators",
 "snap":"snap_isolated_worker_tneanet_edge_ids"}
VERSIONS = {"networkx":"3.6.1", "scipy":"1.17.1", "igraph":"1.0.0", "graph-tool":"3.9", "snap":"6.0.0"}
CASES = ("outgoing_all", "incoming_all", "bidirectional_all", "relation_filter", "depth_bound", "visited_node_bound", "step_bound")
E85_FP = "graph:c6146d2473910927d9c7f113d92a4400"
REPO = {"evidence_index_status":"complete", "graph_edge_count":41,
 "graph_fingerprint":"graph:1aca2caea6acabcf695a6118f7202b6e", "graph_node_count":26,
 "indexed_file_count":9, "source_manifest_sha256":"5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf"}
READS = {"main.py":(11,"3282daf42d3e9a4eaccb836df33c569863853afd01c4176c532906c5e433f475"),
 "tests/checks.py":(8,"cedb1c8e442aceb32d87722d2718ee9a80d8b676b7cb660f4c7bca3d8a81a75a")}
SNAP_IMAGE = "sha256:a3ab78cf8512048adfc3570bff591772c1542dfb09226363142c6779934f59a5"
SNAP_POLICY = {"capabilities":"all_dropped", "cpu_limit":1, "ipc":"none", "memory_limit":"512m",
 "network":"none", "pid_limit":64, "provider_credentials_passed":False, "repository_mount":False,
 "root_filesystem":"read_only", "writable_mounts":[]}

class DossierError(ValueError): pass

def need(ok, code):
    if not ok: raise DossierError(code)

def sha(data): return hashlib.sha256(data).hexdigest()
def file_sha(path): return sha(Path(path).read_bytes())
def load_json(raw, name):
    try: obj=json.loads(raw)
    except Exception as e: raise DossierError("invalid_json:"+name) from e
    need(isinstance(obj,dict), "json_root_invalid:"+name); return obj

def identity(r,b,schema,label,run_id=RUN,source_revision=SOURCE):
    need(r.get("schema_version")==schema, f"schema_mismatch:{b}:{label}")
    need(r.get("backend")==b, f"backend_mismatch:{b}:{label}")
    need(r.get("source_revision")==source_revision, f"source_sha_mismatch:{b}:{label}")
    need(str(r.get("workflow_run_id"))==str(run_id), f"run_id_mismatch:{b}:{label}")
    need(str(r.get("workflow_run_attempt"))==str(ATTEMPT), f"attempt_mismatch:{b}:{label}")
    need(r.get("workflow_name")==WORKFLOW and r.get("status")=="passed", f"workflow_or_status_mismatch:{b}:{label}")

def verify_e85(r,b,run_id=RUN,source_revision=SOURCE,snap_image=SNAP_IMAGE):
    identity(r,b,"ae32c/e85-native-backend-conformance/v1","e85",run_id,source_revision)
    need(r.get("backend_native_query_mode")==MODES[b], "e85_native_mode:"+b)
    need(str(r.get("native_library_version"))==VERSIONS[b], "e85_library_version:"+b)
    need(r.get("case_count")==7 and r.get("repeated_query_count")==14, "e85_case_counts:"+b)
    cases=r.get("conformance_cases",[]); need(len(cases)==7 and {c.get("name") for c in cases}==set(CASES), "e85_case_set:"+b)
    for c in cases:
        need(c.get("status")=="passed" and c.get("reference_parity") is True and c.get("repeat_deterministic") is True, "e85_case_parity:"+b)
        if c["name"]=="visited_node_bound": need(c.get("truncated") is True and c.get("stop_reason")=="max_visited_nodes", "e85_visited_bound:"+b)
        elif c["name"]=="step_bound": need(c.get("truncated") is True and c.get("stop_reason")=="max_traversal_steps", "e85_step_bound:"+b)
        else: need(c.get("truncated") is False and c.get("stop_reason") is None, "e85_unexpected_truncation:"+b)
        need(c.get("graph_fingerprint")==E85_FP, "e85_graph_fingerprint:"+b)
    x=r.get("backend_execution",{})
    for k,v in {"queries_attempted":14,"queries_succeeded":14,"queries_failed":0,"parity_verified_queries":14,
                "parity_failures":0,"native_adjacency_lookups":34,"native_edge_occurrences_read":96}.items():
        need(x.get(k)==v, "e85_telemetry:"+b+":"+k)
    p=r.get("projection_round_trip",{})
    need(p.get("status")=="passed" and p.get("exact") is True and (p.get("node_count"),p.get("edge_occurrence_count"),
        p.get("parallel_edge_occurrences"),p.get("self_loop_occurrences"))==(5,8,3,1), "e85_projection:"+b)
    need(p.get("round_trip_sha256")=="a2c0d12aed407f322c425c5c557ef58d7e52b2814b9e2e83ef01ff859ca77ab3", "e85_projection_sha:"+b)
    need(r.get("filesystem_mutations")==r.get("network_calls")==r.get("provider_calls")==0 and r.get("repository_code_executed") is False,
         "e85_side_effects:"+b)
    loss=r.get("backend_loss_assessment")
    if b=="networkx": need(loss is None, "networkx_loss_assessment_unexpected")
    elif b=="scipy":
        d=loss.get("details",{}) if isinstance(loss,dict) else {}
        need(loss.get("lossless") is False and d.get("scope")=="hybrid_csr_plus_exact_semantic_side_channels" and
             "native_per_edge_relation_and_metadata_columns_inside_csr_matrix" in d.get("lost",[]) and
             {"exact_edge_occurrences_in_side_channel","relation_labels_in_side_channel","node_and_edge_attributes_in_side_channel",
              "node_and_edge_metadata_in_side_channel"}.issubset(set(d.get("preserved",[]))), "scipy_hybrid_representation:"+b)
    else: need(loss.get("lossless") is True and loss.get("details",{}).get("lost")==[], "e85_loss_assessment:"+b)
    w=r.get("native_worker")
    if b=="snap":
        need(w.get("container_image_id")==snap_image and w.get("snap_version")=="6.0.0" and w.get("python_version")=="3.9.25" and
             w.get("request_timeout_enforced") is True and w.get("request_timeout_seconds")==120.0, "snap_e85_worker:")
    else: need(w is None, "unexpected_e85_worker:"+b)
    return {"case_count":7,"queries":14,"parity_verified":14,"native_adjacency_lookups":34,"native_edge_occurrences_read":96}

def verify_e88(r,b,run_id=RUN,source_revision=SOURCE,snap_image=SNAP_IMAGE):
    identity(r,b,"ae32c/repository-backend-conformance/v1","e88",run_id,source_revision)
    need(r.get("backend_library")==b and str(r.get("backend_library_version"))==VERSIONS[b] and
         r.get("backend_native_query_mode")==MODES[b], "e88_backend_identity:"+b)
    x=r.get("backend_execution",{})
    for k,v in {"queries_attempted":43,"queries_succeeded":43,"queries_failed":0,"parity_verified_queries":43,
                "parity_failures":0,"native_adjacency_lookups":45,"native_edge_occurrences_read":86}.items():
        need(x.get(k)==v, "e88_telemetry:"+b+":"+k)
    need(r.get("repository_snapshot")==REPO, "e88_repository_snapshot:"+b)
    q=r.get("backend_queries",{})
    for k in ("find_related_tests","graph_neighbors","graph_path"):
        need(q.get(k)=="selected_backend_and_reference_parity_verified", "e88_query_parity:"+b+":"+k)
    tele={"find_workflow_context":16,"trace_execution_context":7,"trace_execution_context.workflow_context":16}
    actual=r.get("context_operation_telemetry",{})
    need(set(actual)==set(tele), "e88_context_telemetry_keys:"+b)
    for k,n in tele.items():
        v=actual[k]; need(v.get("adjacency_queries_attempted")==n and v.get("adjacency_queries_succeeded")==n and
          v.get("adjacency_queries_failed")==0 and v.get("parity_verified")==n and v.get("parity_failures")==0,
          "e88_context_telemetry:"+b+":"+k)
    follow=r.get("graph_to_repository_follow_through",{})
    need(follow.get("status")=="passed" and follow.get("verified_read_count")==2, "e88_follow_through:"+b)
    reads=follow.get("reads",[]); need(len(reads)==2, "e88_source_reads:"+b)
    for row in reads:
        need(READS.get(row.get("path"))==(row.get("line_count"),row.get("source_sha256")) and row.get("source_range_complete") is True,
             "e88_source_read_hash:"+b)
    need({x.get("path") for x in reads}==set(READS), "e88_source_read_set:"+b)
    required=r.get("required_graph_query",{})
    need(required.get("coverage_status")=="complete_for_query" and required.get("direction")=="incoming" and
         required.get("target")=="symbol:pipeline.extractor::extract" and
         set(required.get("source_paths",[]))=={"main.py","pipeline/extractor.py","tests/checks.py"} and
         r.get("graph_path",{}).get("path_found") is True and r.get("related_tests",{}).get("candidate_count")==1 and
         r.get("related_tests",{}).get("returned_count")==1, "e88_required_queries:"+b)
    effects={"network_calls_performed":False,"provider_calls_made":False,"repository_code_executed":False,
             "source_files_modified":False,"tests_executed_by_backend":False}
    need(r.get("side_effects")==effects, "e88_side_effects:"+b)
    w=r.get("native_worker")
    if b=="snap":
        need(w.get("container_image_id")==SNAP_IMAGE and w.get("snap_version")=="6.0.0" and w.get("python_version")=="3.9.25" and
             w.get("request_timeout_enforced") is True and w.get("request_timeout_seconds")==30.0 and
             w.get("container_policy")==SNAP_POLICY and w.get("graph_fingerprint")==REPO["graph_fingerprint"] and
             w.get("node_count")==26 and w.get("edge_occurrence_count")==41, "snap_e88_isolation:")
    else: need(w is None, "unexpected_e88_worker:"+b)
    return {"queries":43,"parity_verified":43,"native_adjacency_lookups":45,"native_edge_occurrences_read":86,
            "context_operations":tele,"verified_source_reads":{k:v[1] for k,v in READS.items()}}

def verify(artifact_dir, manifest, *, expected_run_id=RUN, expected_source_revision=SOURCE, expected_snap_image=SNAP_IMAGE):
    need(manifest.get("run_id")==expected_run_id and manifest.get("run_attempt")==ATTEMPT and manifest.get("source_revision")==expected_source_revision and
         manifest.get("head_branch")=="stage1/section-uuids" and manifest.get("workflow_name")==WORKFLOW,
         "manifest_identity_mismatch")
    items=manifest.get("artifacts",[]); need(len(items)==5, "manifest_requires_five_artifacts")
    by={}
    ids=set()
    for item in items:
        b=next((k for k,v in ARTIFACTS.items() if item.get("name")==v),None)
        need(b is not None and b not in by, "artifact_name_or_duplicate_backend")
        aid=item.get("id"); need(type(aid) is int and aid>0 and aid not in ids, "artifact_id_invalid"); ids.add(aid)
        need(item.get("expired") is False and re.fullmatch(r"sha256:[0-9a-f]{64}",item.get("digest","")) is not None,
             "artifact_expired_or_digest_invalid")
        wr=item.get("workflow_run",{})
        need(wr.get("id")==expected_run_id and wr.get("head_branch")=="stage1/section-uuids" and wr.get("head_sha")==expected_source_revision and
             wr.get("repository_id")==1346375418 and wr.get("head_repository_id")==1346375418, "artifact_source_binding:"+b)
        need(type(item.get("size_in_bytes")) is int and item["size_in_bytes"]>0, "artifact_size_invalid")
        by[b]=item
    need(set(by)==set(BACKENDS), "backend_artifact_set_incomplete")
    records=[]
    for b in BACKENDS:
        p=Path(artifact_dir)/(b.replace("-","_")+".zip"); need(p.is_file(), "artifact_missing:"+b)
        raw=p.read_bytes(); item=by[b]
        need(len(raw)==item["size_in_bytes"] and "sha256:"+sha(raw)==item["digest"], "artifact_archive_digest_or_size:"+b)
        try:
            with zipfile.ZipFile(p) as z:
                infos=z.infolist(); names=[x.filename for x in infos]
                expected={f"e85-{b}.json",f"e88-{b}-repository.json"}
                need(len(names)==len(set(names)) and set(names)==expected, "zip_member_set:"+b)
                for info in infos:
                    mode=(info.external_attr>>16)&0xffff
                    need(not info.is_dir() and not stat.S_ISLNK(mode) and info.file_size<=2_000_000, "zip_member_safety:"+b)
                raw_e85=z.read(f"e85-{b}.json")
                raw_e88=z.read(f"e88-{b}-repository.json")
                e85=load_json(raw_e85,b+":e85")
                e88=load_json(raw_e88,b+":e88")
        except zipfile.BadZipFile as e: raise DossierError("zip_invalid:"+b) from e
        a=verify_e85(e85,b,expected_run_id,expected_source_revision,expected_snap_image); c=verify_e88(e88,b,expected_run_id,expected_source_revision,expected_snap_image)
        records.append({"backend":b,"artifact_id":item["id"],"artifact_name":item["name"],
          "artifact_archive_sha256":item["digest"],"artifact_archive_size_bytes":len(raw),
          "e85_report_sha256":sha(raw_e85), "e88_report_sha256":sha(raw_e88),
          "native_query_mode":MODES[b],"library_version":VERSIONS[b],"e85":a,"e88":c})
    return {"schema_version":"ae32c/m7.4-e85-e88-detached-dossier/v1","status":"verified",
      "campaign":{"workflow_run_id":expected_run_id,"workflow_run_attempt":ATTEMPT,"source_revision":expected_source_revision,
       "source_branch":"stage1/section-uuids","backends":list(BACKENDS),"workflow_name":WORKFLOW},
      "artifacts":records,"cross_backend_invariants":{"e85_graph_fingerprint":E85_FP,"e88_repository_snapshot":REPO,
       "backend_specific_native_modes_verified":True},
      "interpretation":{"computational_options_not_competitors":True,"performance_winner_established":False,
       "task_suitability_decision_established":False,"backend_auto_selection_permitted":False,
       "production_approval":False,"scope":"artifact identity and declared E.8.5/E.8.8 evidence; not historical re-execution or physical-runner attestation"}}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact-dir",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--output",type=Path)
    ap.add_argument("--expected-run-id",type=int,default=RUN)
    ap.add_argument("--expected-source-revision",default=SOURCE)
    ap.add_argument("--expected-snap-image",default=SNAP_IMAGE)
    a=ap.parse_args()
    try:
        manifest=load_json(a.manifest.read_bytes(),a.manifest.name)
        result=verify(a.artifact_dir,manifest,expected_run_id=a.expected_run_id,expected_source_revision=a.expected_source_revision,expected_snap_image=a.expected_snap_image)
        result["verifier"]={"implementation":"tools/gb08_m74_native_conformance_dossier.py",
          "implementation_sha256":file_sha(Path(__file__)),"manifest_sha256":file_sha(a.manifest),"python_version":sys.version.split()[0]}
        rendered=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if a.output: a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(rendered,encoding="utf-8")
        print(rendered,end=""); return 0
    except (OSError,DossierError) as e:
        print(json.dumps({"status":"failed","error":str(e)},sort_keys=True),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
