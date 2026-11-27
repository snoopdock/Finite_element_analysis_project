#!/usr/bin/env python3
"""Read-only AE-32D schema and cross-record consistency validator."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator
FILES={"case_schema":"evaluation/ae32d/case.schema.json","manifest_schema":"evaluation/ae32d/manifest.schema.json","rubric_schema":"evaluation/ae32d/scoring-rubric.schema.json","pilot_schema":"evaluation/ae32d/pilot-plan.schema.json","manifest":"evaluation/ae32d/manifest.json","rubric":"evaluation/ae32d/scoring-rubric.json","pilot":"evaluation/ae32d/pilot-plan.json"}
def load(root,rel,errors):
 try:return json.loads((root/rel).read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as exc:
  errors.append(f"{rel}:load_failed:{type(exc).__name__}");return None
def validate(schema,value,label,errors):
 try:Draft202012Validator.check_schema(schema)
 except Exception as exc:
  errors.append(f"{label}:invalid_schema:{type(exc).__name__}");return
 for err in Draft202012Validator(schema).iter_errors(value):
  loc="/".join(str(x) for x in err.absolute_path);errors.append(f"{label}:schema:{loc}:{err.message}")
def check_case_gate(case,entry,manifest_status,rubric,pilot):
 errors=[];ev=case.get("evaluation",{});gt=case.get("ground_truth",{});rv=case.get("review",{});mv=case.get("machine_verification")
 eligible=ev.get("primary_benchmark_eligible") is True
 if entry.get("case_id")!=case.get("case_id"):errors.append("manifest_case_id_mismatch")
 if entry.get("status")!=case.get("case_status"):errors.append("manifest_case_status_mismatch")
 if entry.get("primary_benchmark_eligible") is not eligible:errors.append("manifest_primary_eligibility_mismatch")
 if gt.get("label")=="pending_adjudication" and eligible:errors.append("pending_ground_truth_cannot_be_primary_eligible")
 if rv.get("status")!="adjudicated" and eligible:errors.append("unadjudicated_case_cannot_be_primary_eligible")
 if eligible:
  if case.get("case_status")!="adjudicated":errors.append("primary_case_status_must_be_adjudicated")
  if not rv.get("adjudication") or len(rv.get("reviewers",[]))<rv.get("required_independent_reviewers",2):errors.append("primary_case_missing_review_record")
  if ev.get("exclusion_reason"):errors.append("primary_case_has_exclusion_reason")
  if manifest_status!="frozen" or rubric.get("status")!="frozen" or pilot.get("status")!="frozen":errors.append("primary_scoring_requires_frozen_records")
 if mv is not None:
  if mv.get("primary_benchmark_eligible") is not False:errors.append("machine_verification_cannot_grant_primary_eligibility")
  if eligible and (gt.get("label")=="pending_adjudication" or rv.get("status")!="adjudicated"):
   errors.append("machine_verification_not_substitute_for_gold_adjudication")
  if mv.get("candidate_source_commit")!=case.get("source",{}).get("source_commit_sha"):errors.append("machine_source_commit_mismatch")
  if mv.get("human_independent_adjudication")!="not_performed":errors.append("machine_record_must_not_claim_human_adjudication")
  if case.get("case_status")=="machine_verified_regression" and mv.get("machine_adjudication")!="confirmed_fixture_runtime_defect":errors.append("machine_regression_requires_confirmed_machine_result")
 return errors
def validate_repository(root):
 errors=[];data={k:load(root,v,errors) for k,v in FILES.items()}
 if any(v is None for v in data.values()):return errors
 schemas={k:data[k] for k in ("case_schema","manifest_schema","rubric_schema","pilot_schema")}
 for k,s in schemas.items():
  try:Draft202012Validator.check_schema(s)
  except Exception as exc:errors.append(f"{k}:invalid_schema:{type(exc).__name__}")
 validate(schemas["manifest_schema"],data["manifest"],"manifest",errors);validate(schemas["rubric_schema"],data["rubric"],"rubric",errors);validate(schemas["pilot_schema"],data["pilot"],"pilot",errors)
 manifest,rubric,pilot=data["manifest"],data["rubric"],data["pilot"];ids=set();paths=set();count=0;eligible_count=0
 for entry in manifest.get("cases",[]):
  rel=entry.get("path","");p=Path(rel)
  if not rel or p.is_absolute() or ".." in p.parts:errors.append("unsafe_manifest_case_path:"+str(rel));continue
  case_rel="evaluation/ae32d/"+rel;case=load(root,case_rel,errors)
  if case is None:continue
  count+=1;validate(schemas["case_schema"],case,case_rel,errors);cid=case.get("case_id")
  if cid in ids:errors.append("duplicate_case_id:"+str(cid))
  if rel in paths:errors.append("duplicate_case_path:"+rel)
  ids.add(cid);paths.add(rel)
  errors.extend(f"{case_rel}:{e}" for e in check_case_gate(case,entry,manifest.get("status"),rubric,pilot))
  eligible_count+=int(case.get("evaluation",{}).get("primary_benchmark_eligible") is True)
 current=pilot.get("current_case_status",{})
 if current.get("candidate_count")!=count:errors.append("pilot_candidate_count_mismatch")
 if current.get("primary_score_eligible_count")!=eligible_count:errors.append("pilot_primary_count_mismatch")
 return errors
def main(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument("--repository",type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument("--output",type=Path);args=parser.parse_args(argv)
 errors=validate_repository(args.repository.resolve());report={"schema_version":"ae32d/validation-report/v1","status":"valid" if not errors else "invalid","errors":errors}
 if args.output:
  args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(report,indent=2));return 0 if not errors else 1
if __name__=="__main__":raise SystemExit(main())
