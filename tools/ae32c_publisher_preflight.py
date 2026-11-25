"""Read-only AE-32C trusted-publisher activation preflight.

This tool inspects GitHub configuration and reports blockers. It never writes
repository settings, creates tokens, changes refs, or publishes audit results.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


PUBLICATION_BRANCH = "ae32c-publication-state"
ENVIRONMENT_NAME = "ae32c-publication"
REQUIRED_RULES = {"update", "deletion", "non_fast_forward"}


def api_get(api_url: str, token: str, path: str) -> tuple[int, Any]:
    request = urllib.request.Request(
        api_url.rstrip("/") + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AE-32C-publisher-preflight",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {}
        return exc.code, payload
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"message": type(exc).__name__}


def _check(status: str, detail: str) -> dict[str, str]:
    return {"status": status, "detail": detail}


def evaluate(
    *,
    repository: str,
    default_branch: str,
    branch_protection_status: int,
    branch_protection: Any,
    rulesets_status: int,
    rulesets: Any,
    environment_status: int,
    environment: Any,
    app_client_id_present: bool,
    app_private_key_present: bool,
    publisher_app_id: int | None,
) -> dict[str, Any]:
    checks: dict[str, dict[str, str]] = {}

    if branch_protection_status != 200 or not isinstance(branch_protection, dict):
        state = "BLOCKED" if branch_protection_status == 404 else "UNVERIFIED"
        checks["default_branch_protection"] = _check(
            state, f"GitHub API returned HTTP {branch_protection_status}; protection could not be confirmed."
        )
    else:
        reviews = branch_protection.get("required_pull_request_reviews")
        approvals = reviews.get("required_approving_review_count", 0) if isinstance(reviews, dict) else 0
        admins = branch_protection.get("enforce_admins")
        admins_enforced = admins is True or (isinstance(admins, dict) and admins.get("enabled") is True)
        status_checks = branch_protection.get("required_status_checks")
        contexts = status_checks.get("contexts", []) if isinstance(status_checks, dict) else []
        if approvals >= 1 and admins_enforced and isinstance(contexts, list) and contexts:
            checks["default_branch_protection"] = _check(
                "PASS", f"{default_branch} requires at least one approval, enforces rules for administrators, and requires status checks."
            )
        else:
            checks["default_branch_protection"] = _check(
                "BLOCKED",
                "Required controls incomplete: need >=1 required approval, administrator enforcement, and at least one required status check."
            )

    if rulesets_status != 200 or not isinstance(rulesets, list):
        state = "BLOCKED" if rulesets_status == 200 else "UNVERIFIED"
        checks["publication_ref_ruleset"] = _check(
            state, f"GitHub rulesets API returned HTTP {rulesets_status}; scoped ref ruleset could not be confirmed."
        )
    else:
        expected_refs = {
            f"refs/heads/{PUBLICATION_BRANCH}",
            PUBLICATION_BRANCH,
        }
        matches = []
        for ruleset in rulesets:
            if not isinstance(ruleset, dict) or ruleset.get("enforcement") != "active":
                continue
            conditions = ruleset.get("conditions")
            ref_condition = conditions.get("ref_name") if isinstance(conditions, dict) else None
            includes = ref_condition.get("include", []) if isinstance(ref_condition, dict) else []
            excludes = ref_condition.get("exclude", []) if isinstance(ref_condition, dict) else []
            if isinstance(includes, list) and any(x in expected_refs for x in includes) and not excludes:
                matches.append(ruleset)
        valid = []
        for ruleset in matches:
            rules = ruleset.get("rules", [])
            names = {item.get("type") for item in rules if isinstance(item, dict)}
            bypass = ruleset.get("bypass_actors", [])
            # A single integration bypass is required for the publisher App;
            # broad role/team/user bypasses are rejected.
            app_bypass = (
                isinstance(bypass, list) and len(bypass) == 1
                and isinstance(bypass[0], dict)
                and bypass[0].get("actor_type") == "Integration"
                and bypass[0].get("bypass_mode") == "always"
                and isinstance(bypass[0].get("actor_id"), int)
                and publisher_app_id is not None
                and bypass[0].get("actor_id") == publisher_app_id
            )
            if REQUIRED_RULES.issubset(names) and app_bypass:
                valid.append(ruleset)
        if len(valid) == 1:
            checks["publication_ref_ruleset"] = _check(
                "PASS", "Exactly one active ruleset targets only the publication ref, requires update/deletion/non-fast-forward controls, and grants bypass only to one GitHub App integration."
            )
        elif not matches:
            checks["publication_ref_ruleset"] = _check(
                "BLOCKED", f"No active ruleset exactly targets {PUBLICATION_BRANCH}."
            )
        else:
            checks["publication_ref_ruleset"] = _check(
                "BLOCKED", "Publication-ref ruleset is ambiguous or lacks required protections / single-App bypass."
            )

    if environment_status != 200 or not isinstance(environment, dict):
        state = "BLOCKED" if environment_status == 404 else "UNVERIFIED"
        checks["protected_environment"] = _check(
            state, f"GitHub environment API returned HTTP {environment_status}; required reviewers could not be confirmed."
        )
    else:
        protections = environment.get("protection_rules", [])
        reviewers = [
            item for item in protections
            if isinstance(item, dict) and item.get("type") == "required_reviewers"
            and item.get("reviewers")
        ]
        branch_policy = environment.get("deployment_branch_policy")
        branch_restricted = (
            isinstance(branch_policy, dict)
            and branch_policy.get("protected_branches") is True
            and branch_policy.get("custom_branch_policies") is False
        )
        if reviewers and branch_restricted:
            checks["protected_environment"] = _check(
                "PASS", "Environment has required reviewers and is restricted to protected branches."
            )
        else:
            checks["protected_environment"] = _check(
                "BLOCKED", "Environment must require at least one reviewer and restrict deployments to protected branches."
            )

    if app_client_id_present and app_private_key_present:
        checks["publisher_app_credentials"] = _check(
            "PRESENT_UNVERIFIED", "Client ID and private-key secret are present; installation identity and token issuance have not been tested."
        )
    else:
        checks["publisher_app_credentials"] = _check(
            "BLOCKED", "Publisher App client ID variable and private-key secret must both be configured."
        )

    # A preflight never mints a credential. App installation/token validation
    # is intentionally a separate, approval-gated controlled test.
    checks["app_installation"] = _check(
        "UNVERIFIED", "No App JWT or installation token was created by this read-only preflight."
    )
    blocking = [name for name, item in checks.items() if item["status"] in {"BLOCKED", "UNVERIFIED", "PRESENT_UNVERIFIED"}]
    return {
        "schema_version": "ae32c/publisher-preflight/v1",
        "repository": repository,
        "default_branch": default_branch,
        "publication_branch": PUBLICATION_BRANCH,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checks": checks,
        "blocking_checks": blocking,
        "activation_ready": not blocking,
        "authority": {
            "repository_settings_mutated": False,
            "credentials_minted": False,
            "publication_ref_created_or_updated": False,
            "audit_result_published": False,
        },
    }


def run(api_url: str, token: str, repository: str, app_client_id_present: bool,
        app_private_key_present: bool, publisher_app_id: int | None) -> dict[str, Any]:
    if not token or not repository or "/" not in repository:
        raise ValueError("github_read_context_missing")
    repo_status, repo = api_get(api_url, token, "/repos/" + repository)
    if repo_status != 200 or not isinstance(repo, dict):
        raise RuntimeError(f"repository_metadata_unavailable_http_{repo_status}")
    default_branch = repo.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise RuntimeError("repository_default_branch_missing")
    branch = urllib.parse.quote(default_branch, safe="")
    protection_status, protection = api_get(
        api_url, token, f"/repos/{repository}/branches/{branch}/protection"
    )
    rulesets_status, rulesets = api_get(api_url, token, f"/repos/{repository}/rulesets?per_page=100")
    env_name = urllib.parse.quote(ENVIRONMENT_NAME, safe="")
    environment_status, environment = api_get(
        api_url, token, f"/repos/{repository}/environments/{env_name}"
    )
    return evaluate(
        repository=repository,
        default_branch=default_branch,
        branch_protection_status=protection_status,
        branch_protection=protection,
        rulesets_status=rulesets_status,
        rulesets=rulesets,
        environment_status=environment_status,
        environment=environment,
        app_client_id_present=app_client_id_present,
        app_private_key_present=app_private_key_present,
        publisher_app_id=publisher_app_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="ae32c-publisher-preflight.json")
    args = parser.parse_args()
    try:
        result = run(
            api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            token=os.environ.get("PREFLIGHT_READ_TOKEN") or os.environ.get("GITHUB_TOKEN", ""),
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            app_client_id_present=os.environ.get("AE32C_APP_CLIENT_ID_PRESENT") == "true",
            app_private_key_present=os.environ.get("AE32C_APP_PRIVATE_KEY_PRESENT") == "true",
            publisher_app_id=(
                int(os.environ["AE32C_PUBLISHER_APP_ID"])
                if os.environ.get("AE32C_PUBLISHER_APP_ID", "").isdigit()
                else None
            ),
        )
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
        print(json.dumps({
            "activation_ready": result["activation_ready"],
            "blocking_checks": result["blocking_checks"],
            "report": args.output,
        }, sort_keys=True))
        return 0 if result["activation_ready"] else 1
    except (ValueError, RuntimeError) as exc:
        print("AE32C publisher preflight incomplete: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
