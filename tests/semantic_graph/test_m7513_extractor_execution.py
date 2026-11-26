"""M7.5.13 structural and behavioral tests."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from audit_engine.semantic_audit.epistemic.source_inventory import build_source_extractor_inventory
from audit_engine.semantic_audit.epistemic.extractor_execution import ExtractorExecutionError,build_extractor_execution_report,extractor_executor_registry,verify_extractor_execution_report
def seal(x): return hashlib.sha256((json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()).hexdigest()
def manifest(entries):
 entries=sorted(entries,key=lambda x:x["path"].encode()); inv={"schema":"ae32c/source-inventory/v1","entry_count":len(entries),"entries":entries,"sha256":seal(entries)}
 x={"manifest_schema":"ae32c/source-snapshot-manifest/v1","status":"VERIFIED","source_snapshot_id":"snapshot:m7513-test","source":{"commit_oid":"a"*40},"source_inventory":inv,"verification":{"status":"VERIFIED"},"authority":{"atomic_repository_snapshot_established":False}}; x["manifest_sha256"]=seal(x); return x
class ExtractorExecutionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.py=b"import os\nos.getenv('X')\nfrom pathlib import Path\nPath('should_not_run').write_text('bad')\n"; self.yml=b"name: CI\non: push\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n      - run: echo ok\n"
  (self.root/"src").mkdir(); (self.root/"src/app.py").write_bytes(self.py); (self.root/".github/workflows").mkdir(parents=True); (self.root/".github/workflows/ci.yml").write_bytes(self.yml)
  self.source=manifest([{"path":"src/app.py","mode":"100644","object_type":"blob","content_sha256":hashlib.sha256(self.py).hexdigest()},{"path":".github/workflows/ci.yml","mode":"100644","object_type":"blob","content_sha256":hashlib.sha256(self.yml).hexdigest()}]); self.inv=build_source_extractor_inventory(self.source)
 def tearDown(self): self.tmp.cleanup()
 def run_report(self,**kw): return build_extractor_execution_report(self.source,self.inv,self.root,**kw)
 def test_executor_registry_digest(self):
  r=extractor_executor_registry(); self.assertEqual(r["registry_sha256"],seal({k:v for k,v in r.items() if k!="registry_sha256"}))
 def test_every_candidate_has_one_executed_outcome(self):
  r=self.run_report(); self.assertEqual((r["candidate_count"],r["outcome_count"]),(2,2)); self.assertEqual(r["execution_status"],"ALL_EXECUTED")
 def test_ast_extractor_emits_imports_and_calls_without_running_source(self):
  r=self.run_report(); o=next(x for x in r["outcomes"] if x["extractor_id"]=="python_ast")
  self.assertTrue(any(x["module"]=="os" for x in o["result"]["imports"])); self.assertTrue(any(x["symbol"]=="getenv" for x in o["result"]["symbols"])); self.assertFalse((self.root/"should_not_run").exists())
 def test_workflow_scanner_is_lexical_only(self):
  r=self.run_report(); o=next(x for x in r["outcomes"] if x["extractor_id"]=="workflow_static_scan"); keys=[x["key"] for x in o["result"]["observations"]]
  self.assertIn("uses",keys); self.assertIn("run",keys); self.assertEqual(o["result"]["interpretation_boundary"],"lexical_only_not_yaml_validation")
 def test_source_digest_mismatch_is_failed(self):
  (self.root/"src/app.py").write_bytes(b"print('changed')"); r=self.run_report(); o=next(x for x in r["outcomes"] if x["extractor_id"]=="python_ast")
  self.assertEqual(o["status"],"FAILED"); self.assertEqual(o["diagnostic_code"],"source_content_digest_mismatch"); self.assertEqual(r["execution_status"],"PARTIAL")
 def test_syntax_failure_is_recorded(self):
  bad=b"def broken(:\n pass\n"; (self.root/"src/app.py").write_bytes(bad)
  src=manifest([{"path":"src/app.py","mode":"100644","object_type":"blob","content_sha256":hashlib.sha256(bad).hexdigest()},{"path":".github/workflows/ci.yml","mode":"100644","object_type":"blob","content_sha256":hashlib.sha256(self.yml).hexdigest()}]); inv=build_source_extractor_inventory(src); r=build_extractor_execution_report(src,inv,self.root)
  o=next(x for x in r["outcomes"] if x["extractor_id"]=="python_ast"); self.assertEqual(o["diagnostic_code"],"source_parse_failed")
 def test_byte_limit_is_explicit(self): self.assertIn("RESOURCE_LIMIT",self.run_report(max_source_bytes=5)["outcome_counts"])
 def test_explicit_exclusion_is_skipped(self):
  inv=build_source_extractor_inventory(self.source,scope_exclusions={"src/app.py":"outside scope"}); r=build_extractor_execution_report(self.source,inv,self.root); o=next(x for x in r["outcomes"] if x["extractor_id"]=="python_ast"); self.assertEqual(o["status"],"SKIPPED_EXPLICIT_EXCLUSION")
 def test_symlink_is_not_followed(self):
  target=self.root/"src/target.py"; target.write_bytes(self.py); (self.root/"src/app.py").unlink(); (self.root/"src/app.py").symlink_to(target); r=self.run_report(); o=next(x for x in r["outcomes"] if x["extractor_id"]=="python_ast"); self.assertEqual(o["status"],"UNSUPPORTED_INPUT")
 def test_report_replay_passes(self):
  r=self.run_report(); v=verify_extractor_execution_report(self.source,self.inv,r,self.root); self.assertTrue(v["semantic_integrity"]); self.assertTrue(v["replay_matches"])
 def test_rehashed_result_tampering_fails(self):
  r=self.run_report(); f=dict(r); f["outcomes"]=[dict(x) for x in r["outcomes"]]; f["outcomes"][0]["result"]={"forged":True}; f["outcomes"][0]["result_sha256"]=seal({"forged":True}); o=f["outcomes"][0]; o.pop("outcome_id"); o["outcome_id"]=seal({k:v for k,v in o.items() if k!="outcome_id"}); f.pop("report_sha256"); f["report_sha256"]=seal(f)
  with self.assertRaisesRegex(ExtractorExecutionError,"semantic_replay_mismatch"): verify_extractor_execution_report(self.source,self.inv,f,self.root)
 def test_missing_outcome_fails_replay(self):
  r=self.run_report(); f=dict(r); f["outcomes"]=r["outcomes"][:-1]; f["outcome_count"]=len(f["outcomes"]); f.pop("report_sha256"); f["report_sha256"]=seal(f)
  with self.assertRaisesRegex(ExtractorExecutionError,"semantic_replay_mismatch"): verify_extractor_execution_report(self.source,self.inv,f,self.root)
 def test_candidate_tampering_is_rejected(self):
  f=dict(self.inv); f["extractor_candidates"]=[dict(x) for x in self.inv["extractor_candidates"]]; f["extractor_candidates"][0]["extractor_version"]="99"; f.pop("inventory_sha256"); f["inventory_sha256"]=seal(f)
  with self.assertRaisesRegex(ExtractorExecutionError,"source_inventory_verification_failed"): build_extractor_execution_report(self.source,f,self.root)
 def test_invalid_limits_fail_closed(self):
  with self.assertRaisesRegex(ExtractorExecutionError,"positive_integer"): self.run_report(max_source_bytes=0)
if __name__=="__main__": unittest.main()
