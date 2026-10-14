#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import discovery_plan as plan
import radar_feedback as radar


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
        self.assertEqual(20, result["candidate_pool"]["min"])
        self.assertEqual(60, result["candidate_pool"]["max"])
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
        self.assertEqual(20, result["candidate_pool"]["min"])
        self.assertEqual(60, result["candidate_pool"]["max"])
        self.assertEqual(12, result["shortlist"]["max_sources"])
        self.assertEqual(3, result["budget"]["batched_search_calls"])
        self.assertEqual(10, result["budget"]["query_records"])
        self.assertEqual(6, result["budget"]["targeted_opens"])
        self.assertEqual(6, result["early_stop"]["minimum_discovery_lanes"])
        self.assertEqual(10, result["early_stop"]["min_identity_valid_candidates"])
        self.assertFalse(result["early_stop"]["stop_after_first_batch_when_covered"])
        self.assertEqual(30, result["network_policy"]["soft_timeout_seconds"])
        self.assertEqual(90, result["network_policy"]["hard_timeout_seconds"])
        self.assertEqual(60, result["completion_policy"]["reserve_finalization_seconds"])
        self.assertIsNone(result["completion_policy"]["stop_new_discovery_after_seconds"])
        self.assertEqual("per_round", result["completion_policy"]["budget_scope"])
        self.assertEqual(3, result["completion_policy"]["max_discovery_rounds"])
        self.assertTrue(result["completion_policy"]["finalize_from_verified_ledger_on_deadline"])
        self.assertEqual(6, result["route_policy"]["mechanism_expansion"]["minimum_attempted_families"])
        self.assertIn("mechanism_neighbor", result["route_policy"]["mechanism_expansion"]["required_families"])
        self.assertIn("attention", result["route_policy"]["required_lanes"])
        strategy = result["recovery_query_strategy"]
        self.assertEqual(7, len(strategy))
        self.assertEqual(
            ["anchor", "mechanism_vocabulary", "candidate_reservoir", "contrast_or_failure", "anchor_expansion",
             "coverage_probe", "reuse_or_successor"],
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

    def test_bridge_source_domain_aliases_select_native_ecosystems(self):
        cases = {
            "finance": "financial_quant", "biology": "life_science",
            "law": "law_policy", "social science": "social_science",
            "SOCIAL-SCIENCE": "social_science", "queueing theory": "queueing theory",
        }
        for alias, canonical in cases.items():
            with self.subTest(alias=alias):
                bridge = {"bridge_id": "B1", "source_domain": alias,
                          "search_terms": ["feedback control"], "breaks_when": ["delayed observations"],
                          "status": "hypothesis"}
                # Isolate planner routing from the independently maintained bridge gate.
                with mock.patch.object(plan, "validate_bridge", side_effect=dict):
                    result = plan.build_plan({"question": "adherence measurement", "domain": "health",
                                              "mechanism_bridges": [bridge]})
                self.assertEqual(canonical, result["mechanism_bridges"][0]["source_domain"])
                expected = plan.DOMAINS.get(canonical, plan.DOMAINS["multidisciplinary"])["ecosystems"]
                adjacent = [item for item in result["queries"] if item["lane"] == "adjacent"]
                self.assertTrue(adjacent)
                for query in adjacent:
                    self.assertEqual(list(expected), query["ecosystems"])
                    self.assertTrue(query["query"].startswith(canonical + " "))

    FRAME = {
        "bottleneck": "estimating time-varying effects of repeated prompts",
        "outputs": ["proximal effect estimates"],
        "mechanism_terms": ["sequential randomization", "causal excursion effect"],
        "evidence_refs": ["fixture"],
    }

    def reuse_queries(self, result, family=None):
        return [q for q in result["queries"] if q["lane"] == "reuse" and (family is None or q.get("family") == family)]

    def test_reuse_lane_asks_who_already_built_it_from_the_frame(self):
        result = plan.build_plan({"question": "prompt timing study", "domain": "health", "project_frame": self.FRAME})
        implementations = self.reuse_queries(result, "existing_implementation")
        self.assertEqual({"project_frame.mechanism_terms[0]", "project_frame.mechanism_terms[1]", "project_frame.outputs[0]"},
                         {ref for q in implementations for ref in q["derived_from"]})
        for query in implementations:
            self.assertIn("package_registries", query["ecosystems"])
        self.assertEqual(1, len(self.reuse_queries(result, "current_version")))
        lane = next(item for item in result["lanes"] if item["lane"] == "reuse")
        self.assertEqual("planned", lane["status"])
        self.assertTrue(result["consumption"]["project_frame.outputs[0]"]["used_by"])

    def test_humanities_reuse_stays_domain_native(self):
        result = plan.build_plan({"question": "provenance of oral history archives", "domain": "humanities",
                                  "project_frame": {"mechanism_terms": ["provenance chain"]}})
        ecosystems = {eco for q in self.reuse_queries(result) for eco in q["ecosystems"]}
        self.assertIn("dh_venues", ecosystems)
        self.assertNotIn("github", ecosystems)

    def test_foundation_sources_generate_one_hop_successor_checks(self):
        payload = {"question": "prompt timing study", "domain": "health", "project_frame": self.FRAME,
                   "foundation_sources": [
                       {"identity": "doi:10.0000/method", "title": "A design for repeated randomization",
                        "kind": "method", "authors": ["Author A", "Author B"]},
                       {"identity": "doi:10.0000/checklist", "title": "A reporting checklist", "kind": "standard"},
                       {"identity": "url:https://example.org/theory", "title": "A behaviour theory", "kind": "theory"},
                   ]}
        result = plan.build_plan(payload)
        by_ref = {}
        for query in self.reuse_queries(result):
            for ref in query["derived_from"]:
                by_ref.setdefault(ref, set()).add(query.get("family"))
        self.assertEqual({"successor_citation", "existing_implementation", "current_version", "author_artifact"},
                         by_ref["foundation_sources[0]"])
        self.assertEqual({"successor_citation", "existing_implementation", "current_version"}, by_ref["foundation_sources[1]"])
        self.assertEqual({"successor_citation", "existing_implementation"}, by_ref["foundation_sources[2]"])
        citing = [q for q in self.reuse_queries(result, "successor_citation") if q["anchor"] == "doi:10.0000/method"][0]
        self.assertEqual(("forward_citations", "last_24_months"), (citing["operation"], citing["window"]))
        self.assertEqual(plan.CITATION_INDEXES, citing["ecosystems"])
        self.assertEqual(3, len(result["foundation_sources"]))
        self.assertFalse(any("foundation_sources" in action for action in result["host_actions"]))

    def test_missing_foundation_sources_prompt_a_rerun(self):
        result = plan.build_plan({"question": "prompt timing study", "domain": "health", "project_frame": self.FRAME})
        self.assertTrue(any("foundation_sources" in action for action in result["host_actions"]))
        self.assertEqual([], self.reuse_queries(result, "successor_citation"))

    def test_foundation_sources_are_validated(self):
        base = {"question": "q", "domain": "health"}
        with self.assertRaisesRegex(ValueError, "kind must be one of"):
            plan.build_plan({**base, "foundation_sources": [{"identity": "x", "title": "t", "kind": "paper-ish"}]})
        with self.assertRaisesRegex(ValueError, "at most 8"):
            plan.build_plan({**base, "foundation_sources": [{"identity": f"i{n}", "title": "t"} for n in range(9)]})
        with self.assertRaisesRegex(ValueError, r"foundation_sources\[0\] must be an object"):
            plan.build_plan({**base, "foundation_sources": ["doi:10.0000/x"]})

    def test_usefulness_policy_reserves_budget_and_states_selection_rules(self):
        for profile in ("fast", "standard", "recovery"):
            for bridges in (False, True):
                with self.subTest(profile=profile, bridges=bridges):
                    bridge = {"bridge_id": "B1", "source_domain": "computing", "search_terms": ["feedback control"],
                              "breaks_when": ["no feedback signal"], "status": "hypothesis"}
                    with mock.patch.object(plan, "validate_bridge", side_effect=dict):
                        result = plan.build_plan({"question": "q", "domain": "health", "budget_profile": profile,
                                                  "mechanism_bridges": [bridge] if bridges else []})
                    policy = result["usefulness_policy"]
                    minimums = policy["per_round_minimums"]
                    self.assertLessEqual(sum(minimums.values()), result["budget"]["query_records"])
                    self.assertGreaterEqual(minimums["reuse"], 1)
                    self.assertGreaterEqual(minimums["attention"], 1)
                    if profile == "recovery":
                        self.assertEqual(2, minimums["reuse"])
                        self.assertEqual(1 if bridges else 0, minimums["adjacent"])
        policy = plan.build_plan({"question": "q", "domain": "health"})["usefulness_policy"]
        self.assertTrue(policy["age_is_not_exclusion"])
        self.assertEqual(["existing_implementation", "current_version", "successor_citation"], policy["required_query_families"])
        self.assertEqual(["first_published", "version_or_edition", "observed_at", "attention_event"], policy["date_fields"])
        self.assertEqual({"why_invest", "saves_work", "next_action"}, set(policy["top_investment"]["required_fields"]))
        self.assertIn("formal record", policy["identity_conflict"])

    def test_no_round_specific_answers_are_hardcoded(self):
        root = Path(plan.__file__).resolve().parents[1]
        texts = [Path(plan.__file__).read_text(encoding="utf-8"),
                 (root / "SKILL.md").read_text(encoding="utf-8"),
                 (root / "references" / "usefulness-first-discovery.md").read_text(encoding="utf-8")]
        for name in ("MRTAnalysis", "CONSORT", "AAPOR", "HeartSteps", "AdhereR", "COREQ"):
            for text in texts:
                self.assertNotIn(name, text)

    def test_legacy_ecosystem_records_preserve_canonical_query_ids(self):
        result = plan.build_plan({"question": "archive provenance", "domain": "humanities"})
        canonical = {item["query_id"]: item for item in result["queries"]}
        self.assertEqual(len(result["queries"]), len(canonical))
        self.assertEqual(2, result["schema_version"])
        for lane in result["lanes"]:
            expected = {(item["query_id"], eco) for item in result["queries"]
                        if item["lane"] == lane["lane"] for eco in item["ecosystems"]}
            actual = {(item["query_id"], item["ecosystem"]) for item in lane["query_records"]}
            self.assertEqual(expected, actual)
            self.assertEqual(len(actual), len(lane["query_records"]))
            for item in lane["query_records"]:
                self.assertEqual(canonical[item["query_id"]]["query"], item["query_template"])
                self.assertIn(item["ecosystem"], item["ecosystems"])

    def feedback_event(self, root, raw_label, label, *, terms=(), scope="candidate"):
        reason = "avoid opaque metrics"
        profile = radar.make_profile("Planner fixture", "Temporary feedback integration", [], project_id="P1")
        candidates = {"schema_version": radar.SCHEMA_VERSION, "candidates": [{
            "candidate_id": "C1", "title": "Candidate one", "url": "https://example.org/source",
            "tier": "priority_now", "summary": "Fixture candidate", "why_now": "Integration check",
            "mechanism_tags": ["candidate metadata only"], "trend_note": "",
            "source_version": "v1.0", "verified_at": "2026-10-14T00:00:00+00:00",
        }]}
        original = radar.render_review(profile, radar.validate_candidates(candidates))
        for field, value in (("\u6807\u6ce8", raw_label), ("\u7406\u7531", reason),
                             ("\u504f\u597d\u8303\u56f4", scope), ("\u786e\u8ba4\u7ef4\u5ea6", ", ".join(terms))):
            original = original.replace(f"\u4f60\u7684{field}\uff1a`\u5f85\u586b\u5199`",
                                        f"\u4f60\u7684{field}\uff1a`{value}`")
        review_path, candidates_path = root / "review.md", root / "candidates.json"
        profile_path, proposal_path = root / "profile.json", root / "proposal.json"
        review_path.write_text(original, encoding="utf-8")
        candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        # Exercise real extraction and explicit confirmation; never hand-build evidence.
        with mock.patch("sys.stdout"):
            self.assertEqual(0, radar.command_extract_review(Namespace(
                review=str(review_path), candidates=str(candidates_path),
                project_id="P1", output=str(proposal_path),
            )))
            self.assertEqual(0, radar.command_record(Namespace(
                profile=str(profile_path), feedback=str(proposal_path), output=None, confirm=True,
            )))
        saved = radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))
        event = saved["feedback"][0]
        self.assertEqual(label, event["label"])
        self.assertEqual(reason, event["reason"])
        self.assertEqual(reason, event["evidence"]["raw_reason"])
        self.assertEqual(scope, event["evidence"]["scope"])
        self.assertEqual(list(terms), event["evidence"]["confirmed_terms"])
        self.assertIsNone(radar.feedback_issue(event, "P1"))
        return event

    def test_confirmed_feedback_preserves_five_distinct_ordinals(self):
        cases = [("\u592f", "worth_deepening", 5), ("\u9876\u7ea7", "worth_deepening", 4),
                 ("\u4eba\u4e0a\u4eba", "mechanism_to_borrow", 3), ("NPC", "reference_only", 2),
                 ("\u62c9\u5b8c\u4e86", "not_useful_now", 1)]
        with tempfile.TemporaryDirectory() as directory:
            for raw_label, label, ordinal in cases:
                with self.subTest(raw_label=raw_label):
                    event = self.feedback_event(Path(directory), raw_label, label)
                    result = plan.build_plan({"question": "adherence measurement", "domain": "health",
                                              "project_id": "P1", "preference_events": [event]})
                    self.assertEqual(1, len(result["ranking_policy"]))
                    policy = result["ranking_policy"][0]
                    self.assertEqual((raw_label, label, ordinal),
                                     (policy["raw_label"], policy["label"], policy["ordinal"]))

    def test_avoid_similar_without_dimensions_downweights_only_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            event = self.feedback_event(Path(directory), "avoid_similar", "avoid_similar")
            result = plan.build_plan({"question": "adherence measurement", "domain": "health",
                                      "project_id": "P1", "preference_events": [event]})
            policy = result["ranking_policy"][0]
            self.assertEqual("downweight_candidate", policy["effect"])
            self.assertEqual("C1", policy["candidate_id"])
            self.assertEqual([], policy["confirmed_terms"])
            self.assertIsNone(policy["ordinal"])
            self.assertFalse(any("preference_events[0]" in item["derived_from"]
                                 for item in result["queries"]))

    def test_avoid_similar_dimension_scope_requires_nonempty_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "\u975e\u7a7a\u786e\u8ba4\u7ef4\u5ea6"):
                self.feedback_event(Path(directory), "avoid_similar", "avoid_similar", scope="dimension")

    def test_avoid_similar_uses_only_confirmed_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            event = self.feedback_event(Path(directory), "avoid_similar", "avoid_similar",
                                        terms=["opaque metrics"], scope="dimension")
            result = plan.build_plan({"question": "adherence measurement", "domain": "health",
                                      "project_id": "P1", "preference_events": [event]})
            policy = result["ranking_policy"][0]
            self.assertEqual("downweight_explicit_dimensions", policy["effect"])
            self.assertEqual(["opaque metrics"], policy["confirmed_terms"])

    def test_feedback_gate_uses_two_argument_interface_and_quarantines_legacy(self):
        event = {"candidate_id": "C1", "label": "avoid_similar"}
        def issue(item, project_id):
            self.assertIs(event, item)
            self.assertEqual("P1", project_id)
            return "legacy_or_missing_user_evidence"
        with mock.patch.object(plan, "feedback_issue", side_effect=issue):
            result = plan.build_plan({"question": "adherence measurement", "domain": "health",
                                      "project_id": "P1", "preference_events": [event]})
        self.assertEqual([], result["ranking_policy"])
        self.assertEqual("quarantined", result["consumption"]["preference_events[0]"]["status"])

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
            self.assertEqual("", completed.stdout)
            self.assertEqual("plan_ready", json.loads(completed.stderr)["status"])

    def test_cli_stdout_is_one_json_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps({"question": "memory consolidation", "domain": "business"}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(Path(plan.__file__).resolve()), "--input", str(input_path), "--output", "-"],
                cwd=root, capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("business", json.loads(completed.stdout)["domain"])
            self.assertEqual("plan_ready", json.loads(completed.stderr)["status"])
            self.assertFalse((root / "-").exists())

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
