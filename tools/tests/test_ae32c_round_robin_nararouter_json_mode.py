from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ae32c-round-robin-evaluation.yml"
VERIFIER = ROOT / "tools" / "verify_ae32c_batch_acceptance.py"


def test_round_robin_workflow_enables_json_object_mode_for_nararouter_only():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    nararouter = workflow.split("                nararouter)\n", 1)[1].split(
        "                openrouter)", 1
    )[0]
    cloudflare = workflow.split("                cloudflare)\n", 1)[1].split(
        "                nararouter)", 1
    )[0]
    openrouter = workflow.split("                openrouter)\n", 1)[1].split(
        "              esac", 1
    )[0]

    assert '"FEA_NARAROUTER_JSON_OBJECT_MODE=1"' in nararouter
    assert "FEA_NARAROUTER_JSON_OBJECT_MODE" not in cloudflare
    assert "FEA_NARAROUTER_JSON_OBJECT_MODE" not in openrouter


def test_round_robin_workflow_calls_the_installed_v3_verifier():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "python tools/verify_ae32c_batch_acceptance.py" in workflow
    assert VERIFIER.is_file()


def test_workflow_remains_manual_and_live_consent_gated():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert '"$CONFIRMED" == "true"' in workflow
    assert "providers=(cloudflare nararouter openrouter)" in workflow
