"""Fail-closed cross-record eligibility tests."""
import unittest
from tools.ae32d_validate_benchmark import check_case_gate
class BenchmarkGateTests(unittest.TestCase):
 def base(self):
  c={"case_id":"AE32D-CANDIDATE-001","case_status":"machine_verified_regression","source":{"source_commit_sha":"a"*40},"ground_truth":{"label":"pending_adjudication"},"review":{"status":"pending","required_independent_reviewers":2,"reviewers":[],"adjudication":None},"evaluation":{"primary_benchmark_eligible":False,"exclusion_reason":"not gold"},"machine_verification":{"primary_benchmark_eligible":False,"candidate_source_commit":"a"*40,"human_independent_adjudication":"not_performed","machine_adjudication":"confirmed_fixture_runtime_defect"}}
  e={"case_id":c["case_id"],"status":c["case_status"],"primary_benchmark_eligible":False}
  return c,e,{"status":"draft_pending_approval"},{"status":"draft_pending_approval"}
 def test_machine_verified_regression_is_valid_but_not_gold(self):
  c,e,r,p=self.base();self.assertEqual(check_case_gate(c,e,"design_only",r,p),[])
 def test_pending_ground_truth_cannot_be_primary_eligible(self):
  c,e,r,p=self.base();c["evaluation"]["primary_benchmark_eligible"]=True;e["primary_benchmark_eligible"]=True
  errors=check_case_gate(c,e,"design_only",r,p);self.assertIn("pending_ground_truth_cannot_be_primary_eligible",errors);self.assertIn("unadjudicated_case_cannot_be_primary_eligible",errors)
 def test_machine_verification_cannot_grant_primary_eligibility(self):
  c,e,r,p=self.base();c["evaluation"]["primary_benchmark_eligible"]=True;e["primary_benchmark_eligible"]=True;c["ground_truth"]["label"]="confirmed_defect";c["review"]["status"]="adjudicated";c["case_status"]="adjudicated";e["status"]="adjudicated"
  errors=check_case_gate(c,e,"frozen",{"status":"frozen"},{"status":"frozen"});self.assertIn("machine_verification_cannot_grant_primary_eligibility",errors)
 def test_manifest_status_mismatch_is_rejected(self):
  c,e,r,p=self.base();e["status"]="candidate_not_adjudicated";self.assertIn("manifest_case_status_mismatch",check_case_gate(c,e,"design_only",r,p))
if __name__=="__main__":unittest.main()
