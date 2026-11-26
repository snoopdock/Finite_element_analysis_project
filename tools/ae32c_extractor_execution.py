#!/usr/bin/env python3
"""Build and replay M7.5.13 extractor execution evidence."""
import argparse,json
from pathlib import Path
from audit_engine.semantic_audit.epistemic.source_inventory import build_source_extractor_inventory
from audit_engine.semantic_audit.epistemic.extractor_execution import build_extractor_execution_report,verify_extractor_execution_report
def read(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def write(p,x):
 t=Path(p); t.parent.mkdir(parents=True,exist_ok=True); q=t.with_name(t.name+".tmp")
 q.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); q.replace(t)
def main():
 p=argparse.ArgumentParser(description=__doc__); s=p.add_subparsers(dest="cmd",required=True)
 e=s.add_parser("execute"); e.add_argument("--repository",default="."); e.add_argument("--source-manifest",required=True); e.add_argument("--inventory-output",required=True); e.add_argument("--report-output",required=True)
 v=s.add_parser("verify"); v.add_argument("--repository",default="."); v.add_argument("--source-manifest",required=True); v.add_argument("--inventory",required=True); v.add_argument("--report",required=True)
 a=p.parse_args(); src=read(a.source_manifest)
 if a.cmd=="execute":
  inv=build_source_extractor_inventory(src); report=build_extractor_execution_report(src,inv,a.repository)
  write(a.inventory_output,inv); write(a.report_output,report)
  print(json.dumps({"execution_status":report["execution_status"],"candidate_count":report["candidate_count"],"outcome_count":report["outcome_count"],"outcome_counts":report["outcome_counts"],"report_sha256":report["report_sha256"]},sort_keys=True))
 else: print(json.dumps(verify_extractor_execution_report(src,read(a.inventory),read(a.report),a.repository),sort_keys=True))
 return 0
if __name__=="__main__": raise SystemExit(main())
