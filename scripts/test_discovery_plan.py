#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import discovery_plan as plan


class DiscoveryPlanTests(unittest.TestCase):
    def test_computing_plan_selects_code_and_paper_ecosystems(self):
        result = plan.build_plan({
            "question": "auditable temporal memory for GUI agents",
            "domain": "computing",
            "constraints": ["no remote browser"],
        })
        self.assertEqual("computing", result["domain"])
        self.assertIn("github", result["lanes"][0]["ecosystems"])
        self.assertIn("arxiv", result["lanes"][0]["ecosystems"])
        self.assertEqual(20, result["candidate_pool"]["max"])
        self.assertEqual(12, result["shortlist"]["max_sources"])
        self.assertTrue(result["shortlist"]["single_ranked_list"])
        self.assertEqual("recovery", result["budget_profile"])

    def test_fast_profile_has_adaptive_stop_and_network_fallback(self):
        result = plan.build_plan({
            "question": "auditable temporal memory for GUI agents",
            "domain": "computing",
            "budget_profile": "fast",
        })
        self.assertEqual("fast", result["budget_profile"])
        self.assertEqual(2, result["budget"]["batched_search_calls"])
        self.assertEqual(5, result["budget"]["query_records"])
        self.assertEqual(1, result["budget"]["targeted_opens"])
        self.assertEqual(4, result["shortlist"]["max_sources"])
        self.assertEqual(3, result["early_stop"]["minimum_discovery_lanes"])
        self.assertTrue(result["early_stop"]["stop_after_first_batch_when_covered"])
        self.assertEqual(0, result["network_policy"]["same_query_retries"])
        self.assertEqual("record_gap_and_continue", result["network_policy"]["on_timeout"])
        self.assertEqual([], result["recovery_query_strategy"])

    def test_recovery_profile_prioritizes_missed_source_discovery(self):
        result = plan.build_plan({
            "question": "graph memory and workflow skills for mobile agents",
            "domain": "computing",
            "budget_profile": "recovery",
        })
        self.assertEqual("recovery", result["budget_profile"])
        self.assertEqual(20, result["candidate_pool"]["max"])
        self.assertEqual(12, result["shortlist"]["max_sources"])
        self.assertEqual(2, result["budget"]["batched_search_calls"])
        self.assertEqual(6, result["budget"]["query_records"])
        self.assertEqual(4, result["early_stop"]["minimum_discovery_lanes"])
        self.assertEqual(5, result["early_stop"]["min_identity_valid_candidates"])
        self.assertTrue(result["early_stop"]["stop_after_first_batch_when_covered"])
        self.assertEqual(60, result["completion_policy"]["reserve_finalization_seconds"])
        self.assertEqual(210, result["completion_policy"]["stop_new_discovery_after_seconds"])
        self.assertTrue(result["completion_policy"]["finalize_from_verified_ledger_on_deadline"])
        self.assertEqual(4, result["route_policy"]["mechanism_expansion"]["minimum_attempted_families"])
        self.assertIn("mechanism_neighbor", result["route_policy"]["mechanism_expansion"]["required_families"])
        self.assertIn("attention", result["route_policy"]["required_lanes"])
        strategy = result["recovery_query_strategy"]
        self.assertEqual(6, len(strategy))
        self.assertEqual(
            ["anchor", "mechanism_vocabulary", "candidate_reservoir", "contrast_or_failure", "anchor_expansion", "coverage_probe"],
            [item["kind"] for item in strategy],
        )
        self.assertIn("sibling candidates", strategy[2]["purpose"])

    def test_unknown_budget_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            plan.build_plan({
                "question": "memory consolidation",
                "domain": "computing",
                "budget_profile": "unbounded",
            })

    def test_humanities_plan_does_not_force_github(self):
        result = plan.build_plan({
            "question": "provenance of translated oral history archives",
            "domain": "humanities",
        })
        ecosystems = {item for lane in result["lanes"] for item in lane["ecosystems"]}
        self.assertIn("library_catalogs", ecosystems)
        self.assertIn("h_net", ecosystems)
        self.assertNotIn("github", ecosystems)
        self.assertTrue(any(lane["lane"] == "adjacent" for lane in result["lanes"]))

    def test_known_leads_are_recovery_targets_not_hidden_preferences(self):
        result = plan.build_plan({
            "question": "graph memory for agents",
            "domain": "computing",
            "known_leads": ["AlphaMemory", "BetaMemory", "AlphaMemory"],
        })
        self.assertEqual(["AlphaMemory", "BetaMemory"], result["known_leads"])
        self.assertEqual("recovery_targets_only", result["known_leads_runtime_role"])

    def test_plan_exposes_ecosystem_specific_routes_and_declared_gaps(self):
        result = plan.build_plan({
            "question": "provenance for reproducible digital archives",
            "domain": "humanities",
            "available_ecosystems": ["library_catalogs", "h_net"],
        })
        self.assertEqual("declared", result["availability_status"])
        self.assertIn("institutional_repositories", result["uncovered_ecosystems"])
        self.assertIn("query_records", result["lanes"][0])
        self.assertTrue(any(item["ecosystem"] == "library_catalogs" for item in result["lanes"][0]["query_records"]))
        self.assertEqual(3, result["route_policy"]["minimum_distinct_ecosystems"])

    def test_empty_or_unknown_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            plan.build_plan({"question": "", "domain": "computing"})
        with self.assertRaises(ValueError):
            plan.build_plan({"question": "a question", "domain": "astrology"})

    def test_cli_writes_json_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "plan.json"
            input_path.write_text(json.dumps({"question": "memory consolidation", "domain": "business"}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(Path(plan.__file__).resolve()), "--input", str(input_path), "--output", str(output_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(output_path.is_file())
            rendered = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("business", rendered["domain"])
            self.assertEqual("recovery", rendered["budget_profile"])
            self.assertEqual("plan_ready", json.loads(completed.stdout)["status"])

    def test_cli_can_override_budget_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "plan.json"
            input_path.write_text(json.dumps({"question": "memory consolidation", "domain": "business"}), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(plan.__file__).resolve()),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--budget-profile",
                    "fast",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            rendered = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fast", rendered["budget_profile"])


if __name__ == "__main__":
    unittest.main()
