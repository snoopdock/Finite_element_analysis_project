"""AE-32D executable-fixture boundary tests; no provider calls or external dependencies."""
from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.ae32d_machine_verify_candidate import (
    FIXTURE_RELATIVE_PATH,
    resolve_fixture,
    run_check,
    main,
)


class AE32DMachineVerifierBoundaryTests(unittest.TestCase):
    def _repository(self, root: Path) -> Path:
        fixture = root / FIXTURE_RELATIVE_PATH
        (fixture / "pipeline").mkdir(parents=True)
        (fixture / "providers").mkdir()
        (fixture / "tests").mkdir()
        (fixture / "pipeline" / "extractor.py").write_text(
            "def extract(provider):\n    return provider.total_calls\n",
            encoding="utf-8",
        )
        (fixture / "providers" / "adapter.py").write_text(
            "class ProviderAdapter:\n"
            "    def __init__(self):\n"
            "        self.calls = 0\n",
            encoding="utf-8",
        )
        (fixture / "providers" / "factory.py").write_text(
            "from providers.adapter import ProviderAdapter\n"
            "def build_provider():\n"
            "    return ProviderAdapter()\n",
            encoding="utf-8",
        )
        (fixture / "main.py").write_text(
            "from pipeline.extractor import extract\n"
            "from providers.factory import build_provider\n"
            "def main():\n"
            "    return extract(build_provider())\n"
            "if __name__ == '__main__':\n"
            "    main()\n",
            encoding="utf-8",
        )
        (fixture / "tests" / "checks.py").write_text(
            "def check():\n    return True\n", encoding="utf-8"
        )
        return fixture

    def test_fixed_fixture_is_resolved_and_expected_failure_is_reproduced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._repository(root)
            self.assertEqual(resolve_fixture(root), fixture.resolve())
            report = run_check(root)
            self.assertTrue(report["passed"], report["errors"])
            self.assertEqual(
                report["fixture_path"],
                "tests/semantic_audit/fixtures/ae32c_provider_interface_incident",
            )
            self.assertTrue(
                report["runtime"]["expected_attribute_error_observed"]
            )
            self.assertEqual(
                report["runtime"]["status"], "EXPECTED_FAILURE_REPRODUCED"
            )

    def test_fixture_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = self._repository(root)
            expected = root / FIXTURE_RELATIVE_PATH
            moved = root / "moved-fixture"
            target.rename(moved)
            try:
                expected.symlink_to(moved, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("host does not permit directory symlinks: " + str(exc))
            with self.assertRaisesRegex(ValueError, "fixture_component_symlink_rejected"):
                resolve_fixture(root)

    def test_required_file_symlink_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._repository(root)
            target = root / "outside-extractor.py"
            target.write_text(
                "def extract(provider):\n    return provider.total_calls\n",
                encoding="utf-8",
            )
            source = fixture / "pipeline" / "extractor.py"
            source.unlink()
            try:
                source.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("host does not permit file symlinks: " + str(exc))
            report = run_check(root)
            self.assertFalse(report["passed"])
            self.assertIn(
                "required_file_symlink_rejected:pipeline/extractor.py",
                report["errors"],
            )
            self.assertNotIn("runtime", report)

    def test_repository_root_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            real_root = base / "real"
            self._repository(real_root)
            alias = base / "alias"
            try:
                alias.symlink_to(real_root, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("host does not permit directory symlinks: " + str(exc))
            with self.assertRaisesRegex(ValueError, "repository_root_symlink_rejected"):
                resolve_fixture(alias)

    def test_runtime_process_does_not_inherit_actions_tokens_or_arbitrary_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            expected = SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="AttributeError: 'ProviderAdapter' object has no attribute 'total_calls'",
            )
            with patch.dict(
                os.environ,
                {"GITHUB_TOKEN": "test-token", "AE32D_TEST_SECRET": "test-secret"},
            ):
                with patch(
                    "tools.ae32d_machine_verify_candidate.subprocess.run",
                    return_value=expected,
                ) as run:
                    report = run_check(root)
            self.assertTrue(report["passed"], report["errors"])
            args, kwargs = run.call_args
            self.assertIn("-I", args[0])
            self.assertIn("-B", args[0])
            self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
            self.assertNotIn("AE32D_TEST_SECRET", kwargs["env"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["timeout"], 15)

    def test_cli_does_not_accept_a_fixture_path_argument(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.json"
            with patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as raised:
                    main(["--fixture", str(Path(temp) / "attacker-controlled"), "--output", str(output)])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.exists())


    def test_unrelated_attribute_access_does_not_satisfy_provider_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._repository(root)
            (fixture / "pipeline" / "extractor.py").write_text(
                "def extract(provider):\n    return wrapper.total_calls\n", encoding="utf-8"
            )
            report = run_check(root)
            self.assertFalse(report["passed"])
            self.assertIn("structural_provider_type_contract_missing", report["errors"])
            self.assertIn("structural_provider_total_calls_read_missing", report["errors"])
            self.assertNotIn("runtime", report)

    def test_dynamic_getattr_prevents_negative_member_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._repository(root)
            (fixture / "providers" / "adapter.py").write_text(
                "class ProviderAdapter:\n"
                "    def __init__(self): self.calls = 0\n"
                "    def chat(self, messages): self.calls += 1\n"
                "    def __getattr__(self, name): return self.calls\n", encoding="utf-8"
            )
            report = run_check(root)
            self.assertFalse(report["passed"])
            self.assertIn("structural_dynamic_attribute_hook_present", report["errors"])

    def test_counter_in_unrelated_class_does_not_satisfy_adapter_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._repository(root)
            (fixture / "providers" / "adapter.py").write_text(
                "class ProviderAdapter: pass\n"
                "class Other:\n"
                "    def __init__(self): self.calls = 0\n"
                "    def chat(self, messages): self.calls += 1\n", encoding="utf-8"
            )
            report = run_check(root)
            self.assertFalse(report["passed"])
            self.assertIn("structural_adapter_calls_initialization_missing", report["errors"])


if __name__ == "__main__":
    unittest.main()
