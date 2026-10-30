from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_nararouter_json_probe_is_manual_explicit_and_single_request():
    workflow = (ROOT/'.github/workflows/ae32c-nararouter-json-capability-probe.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in workflow
    assert 'confirm_live_provider_calls:' in workflow
    assert 'default: false' in workflow
    assert 'FEA_LLM_RETRY_ATTEMPTS: "1"' in workflow
    assert '--request-mode json_object' in workflow
    assert 'providers=(cloudflare nararouter openrouter)' not in workflow
    assert 'schedule:' not in workflow
    assert 'push:' not in workflow
