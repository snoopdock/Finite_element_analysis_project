"""Provider-free cost-estimator contract tests."""
import ast
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32c.cost_estimation import build_live_cost_estimator


def test_registered_cloudflare_profile_has_bounded_conservative_estimator():
    estimator = build_live_cost_estimator("cloudflare", "@cf/qwen/qwen3.8-27b")
    assert estimator is not None
    assert estimator.pricing_metadata["cached_input_discount_assumed"] is False
    assert estimator.pricing_metadata["output_reservation_multiplier"] == 2
    assert estimator.pricing_metadata["uncertainty_margin"] == 0.15
    assert estimator("cloudflare", "@cf/qwen/qwen3.8-27b", 400, 100) > 0


@pytest.mark.parametrize(
    ("prompt_chars", "output_tokens"),
    [(True, 1), (-1, 1), (1, False), (1, -1), (1.5, 1), (1, 2.5)],
)
def test_estimator_rejects_invalid_usage_values(prompt_chars, output_tokens):
    estimator = build_live_cost_estimator("cloudflare", "@cf/qwen/qwen3.8-27b")
    with pytest.raises(ValueError, match="invalid_cost_estimator_input"):
        estimator("cloudflare", "@cf/qwen/qwen3.8-27b", prompt_chars, output_tokens)


def test_estimator_module_has_no_provider_or_live_evaluation_imports():
    source = Path(__file__).parents[2] / "audit_engine" / "semantic_audit" / "ae32c" / "cost_estimation.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(name == "providers" or name.startswith("providers.") for name in imported)
    assert not any("live_evaluation" in name for name in imported)
