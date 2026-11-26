import unittest
from unittest.mock import patch

from tools.ae32c_publisher_preflight import evaluate, run


def protection():
    return {
        "required_pull_request_reviews": {"required_approving_review_count": 1},
        "enforce_admins": {"enabled": True},
        "required_status_checks": {"contexts": ["AE-32C GitHub Source and Graph Snapshot"]},
    }


def ruleset():
    return [{
        "id": 12,
        "name": "AE-32C publication ref only",
        "enforcement": "active",
        "conditions": {"ref_name": {
            "include": ["refs/heads/ae32c-publication-state"],
            "exclude": [],
        }},
        "rules": [{"type": name} for name in ("update", "deletion", "non_fast_forward")],
        "bypass_actors": [{
            "actor_id": 12345, "actor_type": "Integration", "bypass_mode": "always"
        }],
    }]


def environment():
    return {
        "protection_rules": [{
            "type": "required_reviewers",
            "reviewers": [{"type": "Team", "id": 77}],
        }],
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
    }


class PublisherPreflightTests(unittest.TestCase):
    def test_all_repository_controls_pass_but_app_installation_remains_unverified(self):
        result = evaluate(
            repository="owner/repo", default_branch="main",
            branch_protection_status=200, branch_protection=protection(),
            rulesets_status=200, rulesets=ruleset(),
            environment_status=200, environment=environment(),
            app_client_id_present=True, app_private_key_present=True, publisher_app_id=12345,
        )
        self.assertEqual(result["checks"]["default_branch_protection"]["status"], "PASS")
        self.assertEqual(result["checks"]["publication_ref_ruleset"]["status"], "PASS")
        self.assertEqual(result["checks"]["protected_environment"]["status"], "PASS")
        self.assertEqual(result["checks"]["publisher_app_credentials"]["status"], "PRESENT_UNVERIFIED")
        self.assertFalse(result["activation_ready"])
        self.assertIn("app_installation", result["blocking_checks"])
        self.assertFalse(result["authority"]["credentials_minted"])

    def test_missing_branch_protection_blocks(self):
        result = evaluate(
            repository="owner/repo", default_branch="main",
            branch_protection_status=404, branch_protection={},
            rulesets_status=200, rulesets=ruleset(),
            environment_status=200, environment=environment(),
            app_client_id_present=True, app_private_key_present=True, publisher_app_id=12345,
        )
        self.assertEqual(result["checks"]["default_branch_protection"]["status"], "BLOCKED")

    def test_api_permission_failure_is_unverified_not_pass(self):
        result = evaluate(
            repository="owner/repo", default_branch="main",
            branch_protection_status=403, branch_protection={},
            rulesets_status=403, rulesets={},
            environment_status=403, environment={},
            app_client_id_present=False, app_private_key_present=False, publisher_app_id=None,
        )
        self.assertEqual(result["checks"]["default_branch_protection"]["status"], "UNVERIFIED")
        self.assertEqual(result["checks"]["publication_ref_ruleset"]["status"], "UNVERIFIED")
        self.assertEqual(result["checks"]["protected_environment"]["status"], "UNVERIFIED")
        self.assertFalse(result["activation_ready"])

    def test_ruleset_with_broad_bypass_is_rejected(self):
        unsafe = ruleset()
        unsafe[0]["bypass_actors"].append({
            "actor_id": 5, "actor_type": "OrganizationAdmin", "bypass_mode": "always"
        })
        result = evaluate(
            repository="owner/repo", default_branch="main",
            branch_protection_status=200, branch_protection=protection(),
            rulesets_status=200, rulesets=unsafe,
            environment_status=200, environment=environment(),
            app_client_id_present=True, app_private_key_present=True, publisher_app_id=12345,
        )
        self.assertEqual(result["checks"]["publication_ref_ruleset"]["status"], "BLOCKED")

    def test_wildcard_or_wrong_ref_ruleset_is_not_accepted(self):
        unsafe = ruleset()
        unsafe[0]["conditions"]["ref_name"]["include"] = ["refs/heads/*"]
        result = evaluate(
            repository="owner/repo", default_branch="main",
            branch_protection_status=200, branch_protection=protection(),
            rulesets_status=200, rulesets=unsafe,
            environment_status=200, environment=environment(),
            app_client_id_present=True, app_private_key_present=True, publisher_app_id=12345,
        )
        self.assertEqual(result["checks"]["publication_ref_ruleset"]["status"], "BLOCKED")

    def test_ruleset_that_also_targets_other_refs_is_rejected(self):
        unsafe = ruleset()
        unsafe[0]["conditions"]["ref_name"]["include"].append("refs/heads/main")
        result = evaluate(
            repository="owner/repo", default_branch="main",
            branch_protection_status=200, branch_protection=protection(),
            rulesets_status=200, rulesets=unsafe,
            environment_status=200, environment=environment(),
            app_client_id_present=True, app_private_key_present=True, publisher_app_id=12345,
        )
        self.assertEqual(result["checks"]["publication_ref_ruleset"]["status"], "BLOCKED")

    def test_malformed_bypass_entry_fails_closed(self):
        unsafe = ruleset()
        unsafe[0]["bypass_actors"] = [None]
        result = evaluate(
            repository="owner/repo", default_branch="main",
            branch_protection_status=200, branch_protection=protection(),
            rulesets_status=200, rulesets=unsafe,
            environment_status=200, environment=environment(),
            app_client_id_present=True, app_private_key_present=True, publisher_app_id=12345,
        )
        self.assertEqual(result["checks"]["publication_ref_ruleset"]["status"], "BLOCKED")

    def test_run_queries_only_read_endpoints(self):
        responses = [
            (200, {"default_branch": "main"}),
            (404, {}),
            (200, []),
            (404, {}),
        ]
        with patch("tools.ae32c_publisher_preflight.api_get", side_effect=responses) as get:
            result = run(
                "https://api.github.com", "read-token", "owner/repo",
                False, False, None,
            )
        self.assertEqual(get.call_count, 4)
        self.assertFalse(result["activation_ready"])
        self.assertTrue(all(call.args[2].startswith("/repos/") for call in get.call_args_list))
        self.assertFalse(result["authority"]["repository_settings_mutated"])
        self.assertFalse(result["authority"]["publication_ref_created_or_updated"])


if __name__ == "__main__":
    unittest.main()
