#!/usr/bin/env python3

import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import preflight_retrieval_experiment as preflight
import runtime_contract as runtime


SKILL_ROOT = Path(__file__).resolve().parents[1]


class RuntimeContractTests(unittest.TestCase):
    def test_runtime_contract_is_valid_and_uses_one_ranked_list(self):
        self.assertEqual([], runtime.validate_runtime_contract(runtime.RUNTIME_CONTRACT))
        self.assertTrue(runtime.OUTPUT_CONTRACT["single_ranked_list"])
        self.assertEqual(6, runtime.DEFAULT_MAX_SOURCES)
        self.assertEqual(6, runtime.PROFILE_CONTRACTS["recovery"]["max_sources"])
        recovery = runtime.PROFILE_CONTRACTS["recovery"]
        self.assertEqual(6, recovery["budget"]["query_records"])
        self.assertEqual(60, recovery["completion_policy"]["reserve_finalization_seconds"])

    def test_runtime_contract_rejects_divergent_recovery_limit(self):
        mutated = copy.deepcopy(runtime.RUNTIME_CONTRACT)
        mutated["profiles"]["recovery"]["max_sources"] = 5
        self.assertTrue(any("default_max_sources" in item for item in runtime.validate_runtime_contract(mutated)))

    def test_runtime_contract_rejects_missing_finalization_reserve(self):
        mutated = copy.deepcopy(runtime.RUNTIME_CONTRACT)
        del mutated["profiles"]["recovery"]["completion_policy"]
        self.assertTrue(any("completion_policy" in item for item in runtime.validate_runtime_contract(mutated)))

    def test_runtime_contract_rejects_nonfinalizing_deadline(self):
        mutated = copy.deepcopy(runtime.RUNTIME_CONTRACT)
        mutated["profiles"]["recovery"]["completion_policy"]["finalize_from_verified_ledger_on_deadline"] = False
        self.assertTrue(any("verified ledger" in item for item in runtime.validate_runtime_contract(mutated)))

    def test_runtime_contract_requires_gap_probe_inside_query_budget(self):
        mutated = copy.deepcopy(runtime.RUNTIME_CONTRACT)
        mutated["profiles"]["recovery"]["completion_policy"]["gap_probe_counts_toward_query_records"] = False
        self.assertTrue(any("gap probe" in item for item in runtime.validate_runtime_contract(mutated)))

    def test_runtime_contract_rejects_negative_query_budget(self):
        mutated = copy.deepcopy(runtime.RUNTIME_CONTRACT)
        mutated["profiles"]["recovery"]["budget"]["query_records"] = -1
        self.assertTrue(any("non-negative integers" in item for item in runtime.validate_runtime_contract(mutated)))

    def test_runtime_contract_rejects_inverted_network_timeouts(self):
        mutated = copy.deepcopy(runtime.RUNTIME_CONTRACT)
        mutated["profiles"]["recovery"]["network_policy"]["soft_timeout_seconds"] = 30
        self.assertTrue(any("network_policy values" in item for item in runtime.validate_runtime_contract(mutated)))

    def test_preflight_passes_current_release_contract(self):
        result = preflight.run_preflight(SKILL_ROOT)
        self.assertEqual("PASS", result["status"])
        self.assertTrue(result["live_run_allowed"])
        self.assertRegex(result["contract_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertTrue(result["fingerprint_files"])

    def test_preflight_catches_legacy_contract_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                SKILL_ROOT,
                root,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".mypy_cache", ".ruff_cache"),
            )
            with (root / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("\nLegacy marker: two-bucket\n")
            result = preflight.run_preflight(root)
            self.assertEqual("FAIL", result["status"])
            self.assertFalse(result["live_run_allowed"])

    def test_preflight_blocks_runner_target_version_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                SKILL_ROOT,
                root,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".mypy_cache", ".ruff_cache"),
            )
            with (root / "scripts" / "discovery_plan.py").open("a", encoding="utf-8") as handle:
                handle.write("\n# simulated installed-version drift\n")
            result = preflight.run_preflight(root)
            self.assertEqual("FAIL", result["status"])
            self.assertTrue(any(item["name"] == "runner_target_parity" for item in result["checks"]))


if __name__ == "__main__":
    unittest.main()
