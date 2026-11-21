"""M7.3 detached five-backend campaign dossier integrity tests."""
from copy import deepcopy
import json

import pytest

from tools import gb06_task_suitability_campaign as m72
from tools import gb07_campaign_dossier as m73

RUN_ID = 123456789
ATTEMPT = 1
SOURCE = "1" * 40
CONTROLLER = "2" * 40


def _rehash(report):
    report["report_sha256"] = m72._digest({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    return report


@pytest.fixture()
def detached_campaign(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    base = m72.make_report(
        "networkx", seeds=[101, 102], repeats=3, warmup=1,
        workload_ids=list(m72.WORKLOADS),
    )
    manifest = {"run_id": RUN_ID, "artifacts": []}
    for index, backend in enumerate(m73.BACKENDS, start=1):
        report = deepcopy(base)
        report["backend"] = backend
        report["native_query_mode"] = m72.NATIVE_MODES[backend]
        for case in report["cases"]:
            case["native_execution"]["native_query_mode"] = m72.NATIVE_MODES[backend]
            case["environment"]["backend_library"] = backend
            case["environment"]["backend_library_version"] = "test"
            case["environment"]["projection_type"] = "test-native-graph"
            if backend == "snap":
                case["environment"]["worker"] = {
                    "python_version": "3.9.25", "snap_version": "6.0.0"
                }
        report["provenance"] = {
            "source_revision": SOURCE,
            "workflow_run_id": str(RUN_ID),
            "workflow_run_attempt": str(ATTEMPT),
            "workflow_name": m73.WORKFLOW,
        }
        _rehash(report)
        (artifact_dir / f"m7-2-{backend}.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        (artifact_dir / f"m7-2-{backend}-run.log").write_text(
            json.dumps({
                "status": "verified", "backend": backend,
                "report_sha256": report["report_sha256"],
            }) + "\n", encoding="utf-8"
        )
        (artifact_dir / f"m7-2-{backend}-verify.log").write_text(
            json.dumps({
                "status": "verified", "backend": backend,
                "report_sha256": report["report_sha256"],
            }) + "\n", encoding="utf-8"
        )
        manifest["artifacts"].append({
            "id": index,
            "name": f"m7-2-task-suitability-{backend}-{RUN_ID}-{ATTEMPT}",
            "expired": False,
            "digest": "sha256:" + f"{index:064x}",
            "workflow_run": {
                "id": RUN_ID, "head_branch": "main", "head_sha": CONTROLLER
            },
        })
    (artifact_dir / "runner-environment.txt").write_text(
        "detached campaign fixture\n", encoding="utf-8"
    )
    return artifact_dir, manifest


def test_five_backend_detached_campaign_verifies(detached_campaign):
    artifact_dir, manifest = detached_campaign
    dossier = m73.verify_campaign(
        artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE
    )
    assert dossier["status"] == "verified"
    assert dossier["campaign"]["backends"] == list(m73.BACKENDS)
    assert dossier["campaign"]["case_count_per_backend"] == 10
    assert dossier["campaign"]["query_records_per_backend"] == 50
    assert dossier["campaign"]["timed_observations_total"] == 750
    assert dossier["campaign"]["warmup_observations_total"] == 250
    assert dossier["interpretation"]["production_approval"] is False
    assert dossier["interpretation"]["cross_environment_timing_ranking_permitted"] is False


def test_missing_backend_artifact_is_rejected(detached_campaign):
    artifact_dir, manifest = detached_campaign
    manifest["artifacts"].pop()
    with pytest.raises(m73.DossierError, match="manifest_requires_five"):
        m73.verify_campaign(artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE)


def test_expired_or_unbound_artifact_is_rejected(detached_campaign):
    artifact_dir, manifest = detached_campaign
    manifest["artifacts"][0]["expired"] = True
    with pytest.raises(m73.DossierError, match="artifact_expired"):
        m73.verify_campaign(artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE)


def test_mixed_source_revision_is_rejected(detached_campaign):
    artifact_dir, manifest = detached_campaign
    path = artifact_dir / "m7-2-scipy.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["provenance"]["source_revision"] = "3" * 40
    _rehash(report)
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(m73.DossierError, match="source_revision_mismatch"):
        m73.verify_campaign(artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE)


def test_cross_backend_configuration_mismatch_is_rejected(detached_campaign):
    artifact_dir, manifest = detached_campaign
    path = artifact_dir / "m7-2-igraph.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["configuration"]["warmup"] = 2
    _rehash(report)
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(m72.BenchmarkError):
        m73.verify_campaign(artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE)


def test_authority_escalation_is_rejected(detached_campaign):
    artifact_dir, manifest = detached_campaign
    path = artifact_dir / "m7-2-snap.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["authority"]["production_approval"] = True
    _rehash(report)
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(m72.BenchmarkError, match="task_scope_or_authority"):
        m73.verify_campaign(artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE)


def test_injected_top_level_selection_field_is_rejected(detached_campaign):
    artifact_dir, manifest = detached_campaign
    path = artifact_dir / "m7-2-networkx.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["recommended_backend"] = "networkx"
    _rehash(report)
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(m73.DossierError, match="report_schema_keys_invalid"):
        m73.verify_campaign(artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE)


def test_detached_verification_log_must_match_report(detached_campaign):
    artifact_dir, manifest = detached_campaign
    path = artifact_dir / "m7-2-graph-tool-verify.log"
    path.write_text(json.dumps({
        "status": "verified", "backend": "graph-tool",
        "report_sha256": "0" * 64,
    }) + "\n", encoding="utf-8")
    with pytest.raises(m73.DossierError, match="detached_verify_log_mismatch"):
        m73.verify_campaign(artifact_dir, manifest, RUN_ID, ATTEMPT, SOURCE)
