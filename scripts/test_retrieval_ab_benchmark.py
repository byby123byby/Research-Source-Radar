#!/usr/bin/env python3

import copy
import json
import signal
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retrieval_ab_benchmark as ab


SKILL_ROOT = Path(__file__).resolve().parents[1]


def public_task_set():
    categories = [
        "similar_work",
        "mechanism_transfer",
        "current_landscape",
        "similar_work",
        "mechanism_transfer",
        "similar_work",
        "current_landscape",
        "mechanism_transfer",
    ]
    tasks = [
        {
            "id": f"TASK-{201 + index}",
            "category": category,
            "prompt": f"Find traceable research sources for a cross-disciplinary project in task family {index + 1}.",
            "constraints": ["Keep source identity visible", "Separate direct evidence from transferable mechanisms"],
            "source_types": ["paper", "official_document"],
            "time_sensitive": category == "current_landscape",
            "evaluation_focus": "Source validity, relevance, and mechanism transfer.",
        }
        for index, category in enumerate(categories)
    ]
    ids = [item["id"] for item in tasks]
    return {
        "schema_version": 1,
        "benchmark_id": "research-source-radar-cross-domain-v3-v1",
        "cutoff_date": "2026-07-18",
        "research_question": "Does the Skill recover useful, identity-valid sources across disciplines?",
        "primary_metrics": list(ab.PRIMARY_METRICS),
        "safety_metrics": ["invalid_source_rate", "completion"],
        "efficiency_metrics": ["valid_relevant_per_1k_tokens", "valid_relevant_per_minute", "wall_seconds", "total_tokens"],
        "task_sets": {"pilot": ids[:4], "main": ids},
        "tasks": tasks,
    }


def benchmark_tasks():
    return public_task_set()


def small_tasks():
    data = benchmark_tasks()
    selected = copy.deepcopy(data["tasks"][:2])
    ids = [item["id"] for item in selected]
    data["tasks"] = selected
    data["task_sets"] = {"pilot": ids, "main": ids}
    return data


def answer(source_suffix="baseline", relevance_text="useful"):
    return {
        "summary": f"Summary for {source_suffix}",
        "sources": [
            {
                "rank": 1,
                "title": f"Source {source_suffix}",
                "url": f"https://github.com/example/{source_suffix}",
                "source_type": "github_repository",
                "role": "direct",
                "relevance_rationale": relevance_text,
                "mechanism": "bounded mechanism",
                "limitations": "benchmark fixture",
                "research_impact": "high",
                "project_shift": "changes a project decision",
                "mechanism_transfer": "direct",
                "deployment_fit": "direct",
                "next_experiment": "run a bounded comparison",
                "popularity_signal": "none",
                "popularity_evidence": [],
            }
        ],
        "queries": [
            {"query": f"query {source_suffix}", "source": "GitHub"},
            {"query": f"mechanism query {source_suffix}", "source": "scholarly index"},
        ],
        "gaps": ["fixture gap"],
        "constraint_notes": ["fixture constraint"],
        "discovery_trace": discovery_trace(),
    }


def discovery_trace(mode="used", route="fast"):
    return {
        "mode": mode,
        "route": route,
        "attempted_families": ["task_decomposition", "mechanism_neighbor"],
        "covered_families": ["task_decomposition"],
        "uncovered_families": ["validation_or_failure"],
        "budget_used": {"query_records": 2, "targeted_opens": 1, "gap_probes": 0},
        "budget_remaining": {"query_records": 3, "targeted_opens": 0, "gap_probes": 1},
        "contribution_map": {
            "problem": "find research-moving sources",
            "inputs": "user project and explicit seed constellation",
            "mechanism": "mechanism and ecosystem expansion",
            "outputs": "ranked candidates and transfer paths",
            "constraints": "bounded search and identity verification",
            "evidence": "canonical metadata and independent coverage",
        },
        "gap_matrix": [
            {"family": "current", "status": "covered", "missing_atoms": [], "supporting_sources": ["S1"]}
        ],
        "next_query_reason": "probe the highest-value uncovered mechanism family",
        "bridge_paths": [],
        "self_refutation": {
            "repeated_families": [],
            "empty_cells": [],
            "hard_negative": "a broad keyword match was excluded",
            "transfer_risks": [],
        },
        "stop_evidence": "the coverage probe added no new identity-valid family",
    }


def exploration_item(title="Exploration lead"):
    return {
        "rank": 2,
        "title": title,
        "url": "https://github.com/example/exploration",
        "source_type": "github_repository",
        "role": "mechanism",
        "relevance_rationale": "a concrete mechanism bridge",
        "mechanism": "transferable mechanism",
        "limitations": "requires adaptation",
        "research_impact": "exploratory",
        "project_shift": "tests a mechanism neighbor",
        "mechanism_transfer": "adapt",
        "deployment_fit": "partial",
        "next_experiment": "run an isolated adaptation test",
        "popularity_signal": "none",
        "popularity_evidence": [],
    }


def response_for(trial, result, *, tokens=100, wall=60.0, status="completed"):
    answer_value = None
    if status == "completed":
        answer_value = copy.deepcopy(result)
        answer_value["discovery_trace"] = discovery_trace(
            mode="not_used" if trial["condition"] == "baseline" else "used",
            route="fast" if trial["condition"] == "baseline" else "recovery",
        )
    return {
        "schema_version": ab.SCHEMA_VERSION,
        "trial_id": trial["trial_id"],
        "task_id": trial["task_id"],
        "condition": trial["condition"],
        "repetition": trial["repetition"],
        "execution": {
            "status": status,
            "model": "test-model",
            "started_at": "2026-07-16T00:00:00+00:00",
            "ended_at": "2026-07-16T00:01:00+00:00",
            "wall_seconds": wall,
            "input_tokens": tokens,
            "output_tokens": tokens,
            "empty_query_attempts": 0,
            "executor_exit_code": 0 if status == "completed" else 1,
            "event_log_sha256": "0" * 64,
            "error": "" if status == "completed" else "fixture failure",
        },
        "answer": answer_value,
    }


class RetrievalABBenchmarkTests(unittest.TestCase):
    def prepared(self, *, runs=1, seed=7):
        return ab.prepare_manifest(
            small_tasks(),
            phase="pilot",
            runs=runs,
            seed=seed,
            model="test-model",
            reasoning_effort="high",
            max_wall_seconds=60,
            max_sources=ab.DEFAULT_MAX_SOURCES,
        )

    def test_public_task_set_is_valid_and_has_frozen_sizes(self):
        data = benchmark_tasks()
        self.assertEqual([], ab.validate_tasks(data))
        self.assertEqual(8, len(data["tasks"]))
        self.assertEqual(4, len(data["task_sets"]["pilot"]))
        self.assertEqual(8, len(data["task_sets"]["main"]))
        self.assertEqual(list(ab.PRIMARY_METRICS), data["primary_metrics"])

    def test_cross_domain_v3_task_set_is_valid_and_discipline_diverse(self):
        data = benchmark_tasks()
        self.assertEqual([], ab.validate_tasks(data))
        self.assertEqual("research-source-radar-cross-domain-v3-v1", data["benchmark_id"])
        self.assertEqual(8, len(data["tasks"]))
        self.assertEqual(4, len(data["task_sets"]["pilot"]))
        self.assertEqual(8, len(data["task_sets"]["main"]))
        self.assertGreaterEqual(len({item["category"] for item in data["tasks"]}), 3)

    def test_task_validation_rejects_schema_category_source_and_set_errors(self):
        data = small_tasks()
        data["unexpected"] = True
        data["tasks"][0]["category"] = "marketing"
        data["tasks"][0]["source_types"] = ["social_hype"]
        data["task_sets"]["pilot"] = ["TASK-999"]
        errors = ab.validate_tasks(data)
        self.assertTrue(any("fields must be exactly" in item for item in errors))
        self.assertTrue(any("category is unsupported" in item for item in errors))
        self.assertTrue(any("source_types contains unsupported" in item for item in errors))
        self.assertTrue(any("known task IDs" in item for item in errors))

    def test_unsupported_task_and_manifest_versions_are_rejected(self):
        tasks = small_tasks()
        tasks["schema_version"] = 999
        self.assertTrue(any("schema_version" in item for item in ab.validate_tasks(tasks)))
        manifest, _ = self.prepared()
        manifest["schema_version"] = 999
        self.assertTrue(any("unsupported" in item for item in ab.validate_manifest(manifest)))

    def test_prepare_is_deterministic_balanced_and_prompt_identical_between_conditions(self):
        first, prompts_first = self.prepared(runs=2, seed=11)
        second, prompts_second = self.prepared(runs=2, seed=11)
        first_without_time = dict(first)
        second_without_time = dict(second)
        first_without_time.pop("created_at")
        second_without_time.pop("created_at")
        self.assertEqual(first_without_time, second_without_time)
        self.assertEqual(prompts_first, prompts_second)
        trials = first["trials"]
        self.assertEqual(8, len(trials))
        self.assertEqual(4, sum(item["condition"] == "baseline" for item in trials))
        self.assertEqual(4, sum(item["condition"] == "skill" for item in trials))
        self.assertTrue(all("Return only JSON matching the provided response schema" in prompt for prompt in prompts_first.values()))
        self.assertTrue(all("condition-specific search, ranking, or discovery behavior" in prompt for prompt in prompts_first.values()))
        self.assertTrue(all("preserve at least one verified candidate in discovery_trace.exploration" not in prompt for prompt in prompts_first.values()))
        by_task = {}
        for trial in trials:
            by_task.setdefault((trial["task_id"], trial["repetition"]), set()).add(trial["prompt_sha256"])
        self.assertTrue(all(len(values) == 1 for values in by_task.values()))

    def test_prepared_run_refuses_to_overwrite_and_manifest_rejects_traversal(self):
        manifest, prompts = self.prepared()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            ab.write_prepared_run(output, manifest, prompts)
            with self.assertRaises(FileExistsError):
                ab.write_prepared_run(output, manifest, prompts)
            mutated = copy.deepcopy(manifest)
            mutated["trials"][0]["prompt_path"] = "../secret"
            self.assertTrue(any("contained relative path" in item for item in ab.validate_manifest(mutated)))

    def test_manifest_rejects_unpaired_or_changed_condition_prompts(self):
        manifest, _ = self.prepared()
        mutated = copy.deepcopy(manifest)
        mutated["trials"][0]["prompt_sha256"] = "f" * 64
        self.assertTrue(any("paired prompts differ" in item for item in ab.validate_manifest(mutated)))
        mutated = copy.deepcopy(manifest)
        mutated["conditions"]["baseline"]["other_user_skills_present"] = True
        self.assertTrue(any("isolation design" in item for item in ab.validate_manifest(mutated)))

    def test_answer_validation_rejects_duplicate_noncontiguous_ranks_and_extra_fields(self):
        value = answer()
        duplicate = copy.deepcopy(value["sources"][0])
        duplicate["title"] = "Second"
        value["sources"].append(duplicate)
        value["extra"] = "not allowed"
        errors = ab.validate_answer(value)
        self.assertTrue(any("fields must be exactly" in item for item in errors))
        self.assertTrue(any("duplicate source rank" in item for item in errors))
        self.assertTrue(any("contiguous" in item for item in errors))

    def test_answer_accepts_auditable_discovery_trace(self):
        enriched = answer("enriched")
        enriched["sources"][0].update(
            {
                "research_impact": "high",
                "project_shift": "changes the candidate-generation protocol",
                "mechanism_transfer": "adapt",
                "deployment_fit": "partial",
                "next_experiment": "blindly compare recovery at ten",
                "popularity_signal": "triangulated",
                "popularity_evidence": [
                    {
                        "kind": "github_activity",
                        "url": "https://github.com/example/enriched",
                        "claim": "unusual recent star growth",
                        "independence_group": "repository activity",
                    },
                    {
                        "kind": "technical_coverage",
                        "url": "https://example.org/coverage",
                        "claim": "substantive mechanism discussion",
                        "independence_group": "independent technical coverage",
                    },
                ],
            }
        )
        self.assertEqual([], ab.validate_answer(enriched))

    def test_answer_uses_one_ranked_list_with_explicit_roles(self):
        enriched = answer("mechanism")
        enriched["sources"].append(exploration_item())
        enriched["discovery_trace"] = discovery_trace()
        self.assertEqual([], ab.validate_answer(enriched))
        enriched["sources"][1]["role"] = "invalid"
        self.assertTrue(any("role" in item for item in ab.validate_answer(enriched)))

    def test_recovery_route_requires_family_and_budget_accounting(self):
        enriched = answer("recovery")
        enriched["queries"] = [
            {"query": f"recovery query {index}", "source": "authoritative index"}
            for index in range(1, 7)
        ]
        trace = discovery_trace()
        trace.update({
            "route": "recovery",
            "attempted_families": ["task_decomposition", "mechanism_neighbor", "artifact_or_ecosystem", "validation_or_failure"],
            "covered_families": ["task_decomposition", "mechanism_neighbor", "artifact_or_ecosystem"],
            "uncovered_families": ["failure"],
            "budget_used": {"query_records": 6, "targeted_opens": 1, "gap_probes": 1},
            "budget_remaining": {"query_records": 0, "targeted_opens": 1, "gap_probes": 0},
        })
        enriched["discovery_trace"] = trace
        self.assertEqual([], ab.validate_answer(enriched))

        invalid = copy.deepcopy(enriched)
        invalid["discovery_trace"].pop("attempted_families", None)
        self.assertTrue(any("attempted_families" in error for error in ab.validate_answer(invalid)))

    def test_recovery_route_rejects_a_seventh_gap_probe_query(self):
        enriched = answer("recovery-budget-overrun")
        enriched["queries"] = [
            {"query": f"recovery query {index}", "source": "authoritative index"}
            for index in range(1, 8)
        ]
        trace = discovery_trace()
        trace.update({
            "route": "recovery",
            "budget_used": {"query_records": 7, "targeted_opens": 2, "gap_probes": 1},
            "budget_remaining": {"query_records": 0, "targeted_opens": 0, "gap_probes": 0},
        })
        enriched["discovery_trace"] = trace
        errors = ab.validate_answer(enriched)
        self.assertTrue(any("query budget exceeds" in error for error in errors))
        self.assertTrue(any("used-plus-actionable-remaining" in error for error in errors))

    def test_recovery_route_rejects_query_trace_count_mismatch(self):
        enriched = answer("recovery-trace-mismatch")
        enriched["queries"] = [
            {"query": f"recovery query {index}", "source": "authoritative index"}
            for index in range(1, 7)
        ]
        trace = discovery_trace()
        trace.update({
            "route": "recovery",
            "budget_used": {"query_records": 5, "targeted_opens": 1, "gap_probes": 0},
            "budget_remaining": {"query_records": 1, "targeted_opens": 1, "gap_probes": 1},
        })
        enriched["discovery_trace"] = trace
        self.assertTrue(any("count must equal" in error for error in ab.validate_answer(enriched)))

    def test_recovery_route_allows_exhausted_dependent_gap_probe(self):
        enriched = answer("recovery-dependent-budget")
        enriched["queries"] = [
            {"query": f"recovery query {index}", "source": "authoritative index"}
            for index in range(1, 7)
        ]
        trace = discovery_trace()
        trace.update({
            "route": "recovery",
            "budget_used": {"query_records": 6, "targeted_opens": 2, "gap_probes": 0},
            "budget_remaining": {"query_records": 0, "targeted_opens": 0, "gap_probes": 0},
        })
        enriched["discovery_trace"] = trace
        self.assertEqual([], ab.validate_answer(enriched))

    def test_response_schema_requires_all_recovery_budget_counters(self):
        schema = ab.response_schema()
        trace = schema["properties"]["discovery_trace"]
        for field in ("budget_used", "budget_remaining"):
            budget = trace["properties"][field]
            self.assertEqual(
                ["query_records", "targeted_opens", "gap_probes"],
                budget["required"],
            )

    def test_blind_pool_and_metrics_use_roles_inside_one_list(self):
        manifest, _ = self.prepared()
        responses = []
        for trial in manifest["trials"]:
            enriched = answer(f"{trial['condition']}-{trial['task_id']}")
            enriched["discovery_trace"] = discovery_trace()
            neighbor = exploration_item(f"neighbor-{trial['condition']}-{trial['task_id']}")
            neighbor["url"] = f"https://github.com/example/neighbor-{trial['condition']}-{trial['task_id']}"
            enriched["sources"].append(neighbor)
            responses.append(response_for(trial, enriched))
        pool = ab.build_blind_pool(small_tasks(), manifest, responses)
        self.assertEqual(8, len(pool["items"]))
        for item in pool["items"]:
            item["relevance"] = 2
            item["identity_valid"] = "valid"
            item["constraint_fit"] = 1
        metrics = ab.score_benchmark(manifest, responses, pool, iterations=20, seed=4)
        self.assertEqual(1.0, metrics["condition_summary"]["skill"]["exploration_source_count"])
        self.assertEqual(1.0, metrics["condition_summary"]["skill"]["exploration_valid_high_relevance_sources"])

    def test_quality_metrics_score_unified_list_and_role_subsets(self):
        manifest, _ = self.prepared()
        trial = manifest["trials"][0]
        result = answer("union")
        result["discovery_trace"] = discovery_trace()
        result["sources"].append(exploration_item("neighbor"))
        response = response_for(trial, result)
        primary = result["sources"][0]
        neighbor = result["sources"][1]
        judgments = {
            (trial["task_id"], ab.normalized_source_key(primary["url"], primary["title"], primary["source_type"])): {
                "relevance": 1,
                "identity_valid": "valid",
                "constraint_fit": 1,
            },
            (trial["task_id"], ab.normalized_source_key(neighbor["url"], neighbor["title"], neighbor["source_type"])): {
                "relevance": 2,
                "identity_valid": "valid",
                "constraint_fit": 1,
            },
        }
        metrics = ab.trial_metrics(response, judgments)
        self.assertEqual(2.0, metrics["discovery_valid_relevant_sources"])
        self.assertEqual(1.0, metrics["valid_high_relevance_sources"])

    def test_active_trace_rejects_malformed_trace_and_over_budget_queries(self):
        malformed = answer("malformed")
        malformed["discovery_trace"] = discovery_trace()
        del malformed["discovery_trace"]["stop_evidence"]
        self.assertTrue(any("stop_evidence" in item for item in ab.validate_answer(malformed)))
        over_budget = answer("over-budget")
        over_budget["discovery_trace"] = discovery_trace()
        over_budget["queries"] = [
            {"query": f"query {index}", "source": "web"} for index in range(ab.ACTIVE_LOOP_MAX_QUERIES + 1)
        ]
        self.assertTrue(any("active discovery loop budget" in item for item in ab.validate_answer(over_budget)))

    def test_prepared_prompt_declares_trace_contract(self):
        prompt = ab.build_prompt(small_tasks()["tasks"][0], "2026-07-16", 10)
        self.assertIn("discovery_trace", prompt)
        self.assertIn("at most 8 distinct query records", prompt)

    def test_recovery_benchmark_prompt_freezes_the_treatment_route(self):
        prompt = ab.build_prompt(
            small_tasks()["tasks"][0],
            "2026-07-16",
            6,
            recovery_route_required=True,
        )
        self.assertIn("use mode=used and route=recovery", prompt)
        self.assertIn("baseline has no installed Skill", prompt)
        recovery_cap = ab.PROFILE_CONTRACTS["recovery"]["budget"]["query_records"]
        self.assertIn(f"at most {recovery_cap} distinct query records", prompt)

    def test_recovery_benchmark_rejects_condition_route_drift(self):
        skill_answer = answer("skill-route-drift")
        self.assertTrue(any(
            "route=recovery" in error
            for error in ab.validate_treatment_trace(
                skill_answer,
                condition="skill",
                benchmark_id="research-source-radar-cross-domain-v3-v1",
            )
        ))
        baseline_answer = answer("baseline-mode-drift")
        self.assertTrue(any(
            "mode=not_used" in error
            for error in ab.validate_treatment_trace(
                baseline_answer,
                condition="baseline",
                benchmark_id="research-source-radar-cross-domain-v3-v1",
            )
        ))

    def test_response_schema_requires_unified_roles_and_family_trace(self):
        trace = ab.response_schema()["properties"]["discovery_trace"]
        source = ab.response_schema()["properties"]["sources"]["items"]
        self.assertIn("role", source["required"])
        self.assertEqual(set(ab.SOURCE_ROLES), set(source["properties"]["role"]["enum"]))
        self.assertNotIn("exploration", trace["properties"])
        for field in (
            "route",
            "attempted_families",
            "covered_families",
            "uncovered_families",
            "budget_used",
            "budget_remaining",
        ):
            self.assertIn(field, trace["required"])

    def test_condition_schema_is_identical_for_baseline_and_skill(self):
        baseline = ab.trial_response_schema("baseline")
        skill = ab.trial_response_schema("skill")
        self.assertEqual(baseline, skill)

    def test_live_preflight_accepts_current_skill_contract(self):
        result = ab.run_live_preflight(SKILL_ROOT)
        self.assertEqual("PASS", result["status"])
        self.assertRegex(result["contract_fingerprint"], r"^[0-9a-f]{64}$")

    def test_live_preflight_blocks_failed_report(self):
        failed = subprocess.CompletedProcess(
            args=["preflight"],
            returncode=1,
            stdout=json.dumps({"status": "FAIL", "checks": [{"name": "schema", "status": "fail"}]}),
            stderr="",
        )
        with mock.patch.object(ab.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(ValueError, "live run blocked"):
                ab.run_live_preflight(SKILL_ROOT)

    def test_live_preflight_timeout_blocks_execution(self):
        with mock.patch.object(ab.subprocess, "run", side_effect=subprocess.TimeoutExpired("preflight", 30)):
            with self.assertRaisesRegex(ValueError, "timed out; live run blocked"):
                ab.run_live_preflight(SKILL_ROOT)

    def test_normalization_deduplicates_caps_and_reranks_equally(self):
        value = answer("normalize")
        value["sources"] = []
        for index in range(1, 9):
            source = copy.deepcopy(answer(f"source-{index}")["sources"][0])
            source["rank"] = index + 10
            value["sources"].append(source)
        duplicate = copy.deepcopy(value["sources"][0])
        duplicate["rank"] = 99
        value["sources"].insert(1, duplicate)
        normalized, diagnostics = ab.normalize_answer(value, max_sources=6)
        self.assertEqual(6, len(normalized["sources"]))
        self.assertEqual(list(range(1, 7)), [source["rank"] for source in normalized["sources"]])
        self.assertEqual(1, diagnostics["deduplicated_source_count"])
        self.assertEqual(2, diagnostics["capped_source_count"])
        self.assertTrue(diagnostics["applied"])
        self.assertEqual([], ab.validate_answer(normalized, max_sources=6))

    def test_validator_uses_manifest_source_limit(self):
        value = answer("limit")
        for index in range(2, 7):
            source = copy.deepcopy(value["sources"][0])
            source["rank"] = index
            source["title"] = f"Source {index}"
            source["url"] = f"https://github.com/example/source-{index}"
            value["sources"].append(source)
        self.assertEqual([], ab.validate_answer(value, max_sources=6))
        self.assertTrue(any("at most 4" in item for item in ab.validate_answer(value, max_sources=4)))

    def test_error_tail_prioritizes_validation_diagnostics_over_event_noise(self):
        rendered = ab.safe_error_tail("event-noise " * 500, "invalid final answer: missing trace")
        self.assertIn("invalid final answer", rendered)

    def test_global_execution_blocker_only_matches_batch_level_quota_failures(self):
        quota = {
            "execution": {
                "status": "failed",
                "error": "You've hit your usage limit. Purchase more credits.",
            }
        }
        timeout = {"execution": {"status": "failed", "error": "trial exceeded hard timeout"}}
        completed = {"execution": {"status": "completed", "error": "quota exceeded"}}
        self.assertEqual("account_usage_limit", ab.global_execution_blocker(quota))
        self.assertIsNone(ab.global_execution_blocker(timeout))
        self.assertIsNone(ab.global_execution_blocker(completed))

    def test_holdout_contamination_gate_finds_canonical_identifier_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skill"
            skill.mkdir()
            gold = root / "gold.json"
            gold.write_text(
                json.dumps({"lead_sets": {"TASK-1": [{"id": "hidden-tool", "aliases": ["hidden tool"]}]}}),
                encoding="utf-8",
            )
            (skill / "SKILL.md").write_text("Use hidden-tool for this task.\n", encoding="utf-8")
            self.assertEqual(["SKILL.md: hidden-tool"], ab.find_holdout_leaks(skill, gold))
            (skill / "SKILL.md").write_text("Use unrelated methods.\n", encoding="utf-8")
            self.assertEqual([], ab.find_holdout_leaks(skill, gold))

    def test_stage_treatment_excludes_real_holdout_from_runtime_package(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "treatment"
            gold = Path(directory) / "gold.json"
            gold.write_text(json.dumps({"lead_sets": {}}), encoding="utf-8")
            args = Namespace(
                source_skill=str(SKILL_ROOT),
                output=str(output),
                holdout_gold=str(gold),
            )
            self.assertEqual(0, ab.command_stage_treatment(args))
            self.assertTrue((output / "SKILL.md").is_file())
            self.assertEqual([], ab.find_holdout_leaks(output, gold))

    def test_response_must_match_manifest_and_failed_response_cannot_contain_answer(self):
        manifest, _ = self.prepared()
        trial = manifest["trials"][0]
        value = response_for(trial, answer())
        value["condition"] = "skill" if trial["condition"] == "baseline" else "baseline"
        self.assertTrue(any("condition does not match" in item for item in ab.validate_response(value, manifest)))
        failed = response_for(trial, answer(), status="failed")
        failed["answer"] = answer()
        self.assertTrue(any("failed response must use null" in item for item in ab.validate_response(failed, manifest)))

    def test_response_validator_accepts_legacy_execution_without_empty_query_metric(self):
        manifest, _ = self.prepared()
        trial = manifest["trials"][0]
        value = response_for(trial, answer())
        value["execution"].pop("empty_query_attempts")
        self.assertEqual([], ab.validate_response(value, manifest))

    def test_empty_query_metric_ignores_started_placeholders_and_counts_completed_searches(self):
        events = [
            {
                "type": "item.started",
                "item": {"type": "web_search", "query": "", "action": {"type": "other"}},
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "web_search",
                    "query": "valid query",
                    "action": {"type": "search", "queries": ["valid query"]},
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "web_search",
                    "query": "",
                    "action": {"type": "search", "queries": []},
                },
            },
        ]
        payload = "\n".join(json.dumps(event) for event in events)
        self.assertEqual(1, ab.count_empty_query_attempts(payload))

    def test_response_rejects_timestamp_hash_and_completion_inconsistency(self):
        manifest, _ = self.prepared()
        trial = manifest["trials"][0]
        value = response_for(trial, answer())
        value["execution"]["started_at"] = "2026-07-16T00:02:00+00:00"
        value["execution"]["event_log_sha256"] = "not-a-hash"
        value["execution"]["executor_exit_code"] = 1
        errors = ab.validate_response(value, manifest)
        self.assertTrue(any("must not precede" in item for item in errors))
        self.assertTrue(any("event_log_sha256" in item for item in errors))
        self.assertTrue(any("exit_code 0" in item for item in errors))

    def test_source_normalization_deduplicates_github_doi_and_arxiv_forms(self):
        self.assertEqual(
            ab.normalized_source_key("https://github.com/Example/Repo/tree/main", "x"),
            ab.normalized_source_key("http://www.github.com/example/repo.git", "y"),
        )
        self.assertEqual(
            "doi:10.1000/example",
            ab.normalized_source_key("https://doi.org/10.1000/Example?x=1", "x"),
        )
        self.assertEqual(
            "arxiv:2401.00001",
            ab.normalized_source_key("https://arxiv.org/pdf/2401.00001.pdf", "x"),
        )
        self.assertEqual(
            ab.normalized_source_key(
                "https://doi.org/10.1145/3411764.3445186",
                "Screen Recognition: Creating Accessibility Metadata for Mobile Applications from Pixels",
                "paper",
            ),
            ab.normalized_source_key(
                "https://docs-assets.developer.apple.com/ml-research/papers/screen-recognition-chi-2021.pdf",
                "Screen Recognition: Creating Accessibility Metadata for Mobile Applications from Pixels",
                "paper",
            ),
        )

    def test_blind_pool_removes_condition_and_deduplicates_sources(self):
        manifest, _ = self.prepared()
        task_id = manifest["trials"][0]["task_id"]
        matching = [item for item in manifest["trials"] if item["task_id"] == task_id]
        responses = [response_for(item, answer("shared")) for item in matching]
        pool = ab.build_blind_pool(small_tasks(), manifest, responses)
        self.assertEqual(1, len(pool["items"]))
        serialized = json.dumps(pool)
        self.assertNotIn('"condition"', serialized)
        self.assertNotIn('"repetition"', serialized)
        expected_task = next(
            item for item in small_tasks()["tasks"] if item["id"] == pool["items"][0]["task_id"]
        )
        self.assertEqual(expected_task["constraints"], pool["items"][0]["task_constraints"])
        self.assertTrue(pool["items"][0]["evaluation_focus"])
        self.assertIsNone(pool["items"][0]["relevance"])

    def test_judgments_require_complete_human_labels_and_manifest_binding(self):
        manifest, _ = self.prepared()
        responses = [
            response_for(trial, answer(f"{trial['condition']}-{trial['task_id']}"))
            for trial in manifest["trials"]
        ]
        pool = ab.build_blind_pool(small_tasks(), manifest, responses)
        errors = ab.validate_judgments(pool, ab.canonical_hash(manifest))
        self.assertTrue(any("relevance must be" in item for item in errors))
        self.assertTrue(any("identity_valid must be judged" in item for item in errors))
        pool["manifest_sha256"] = "wrong"
        self.assertTrue(any("do not belong" in item for item in ab.validate_judgments(pool, ab.canonical_hash(manifest))))

    def test_score_rejects_missing_or_invented_judgment_items(self):
        manifest, _ = self.prepared()
        responses = [
            response_for(trial, answer(f"{trial['condition']}-{trial['task_id']}"))
            for trial in manifest["trials"]
        ]
        pool = ab.build_blind_pool(small_tasks(), manifest, responses)
        for item in pool["items"]:
            item["relevance"] = 1
            item["identity_valid"] = "valid"
            item["constraint_fit"] = 1
        pool["items"].pop()
        with self.assertRaisesRegex(ValueError, "exact pooled"):
            ab.score_benchmark(manifest, responses, pool, iterations=10, seed=1)

    def test_score_reports_positive_skill_difference_on_controlled_fixture(self):
        manifest, _ = self.prepared(runs=2)
        responses = []
        for trial in manifest["trials"]:
            suffix = f"{trial['condition']}-{trial['task_id']}"
            responses.append(response_for(trial, answer(suffix), tokens=100, wall=60.0))
        pool = ab.build_blind_pool(small_tasks(), manifest, responses)
        for item in pool["items"]:
            is_skill = "/skill-" in item["url"]
            item["relevance"] = 2 if is_skill else 1
            item["identity_valid"] = "valid"
            item["constraint_fit"] = 2 if is_skill else 1
        metrics = ab.score_benchmark(manifest, responses, pool, iterations=500, seed=3)
        self.assertEqual(len(manifest["trials"]), metrics["completed_response_count"])
        self.assertGreater(metrics["paired_task_bootstrap"]["ndcg_at_10"]["mean_difference"], 0)
        self.assertGreater(
            metrics["condition_summary"]["skill"]["valid_high_relevance_sources"],
            metrics["condition_summary"]["baseline"]["valid_high_relevance_sources"],
        )
        self.assertIn("frozen pooled-judgment benchmark", metrics["claim_boundary"])

    def test_score_rejects_missing_responses(self):
        manifest, _ = self.prepared()
        response = response_for(manifest["trials"][0], answer())
        pool = ab.build_blind_pool(small_tasks(), manifest, [response])
        for item in pool["items"]:
            item["relevance"] = 1
            item["identity_valid"] = "valid"
            item["constraint_fit"] = 1
        with self.assertRaisesRegex(ValueError, "missing responses"):
            ab.score_benchmark(manifest, [response], pool, iterations=10, seed=1)

    def test_irrelevant_or_invalid_sources_do_not_count_as_direct_fit(self):
        manifest, _ = self.prepared()
        trial = manifest["trials"][0]
        response = response_for(trial, answer("direct-fit"))
        key = ab.normalized_source_key(
            response["answer"]["sources"][0]["url"],
            response["answer"]["sources"][0]["title"],
            response["answer"]["sources"][0]["source_type"],
        )
        judgment = {
            (trial["task_id"], key): {
                "relevance": 0,
                "identity_valid": "valid",
                "constraint_fit": 2,
            }
        }
        self.assertEqual(0.0, ab.trial_metrics(response, judgment)["direct_fit_sources"])
        judgment[(trial["task_id"], key)]["relevance"] = 1
        judgment[(trial["task_id"], key)]["identity_valid"] = "invalid"
        self.assertEqual(0.0, ab.trial_metrics(response, judgment)["direct_fit_sources"])

    def test_event_usage_uses_largest_recorded_values_and_ignores_noise(self):
        payload = "\n".join(
            [
                "not json",
                json.dumps({"usage": {"input_tokens": 10, "output_tokens": 2}}),
                json.dumps({"nested": [{"input_tokens": 25}, {"output_tokens": 8}]}),
            ]
        )
        self.assertEqual((25, 8), ab.parse_event_usage(payload))

    def test_cli_prepare_pool_and_score_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "tasks.json"
            tasks_path.write_text(json.dumps(small_tasks()), encoding="utf-8")
            run_dir = root / "run"
            prepare_args = Namespace(
                tasks=str(tasks_path),
                output_dir=str(run_dir),
                phase="pilot",
                runs=1,
                seed=19,
                model="test-model",
                reasoning_effort="high",
                max_wall_seconds=60,
                max_sources=10,
            )
            self.assertEqual(0, ab.command_prepare(prepare_args))
            manifest = ab.load_valid_manifest(run_dir / "trial_manifest.json")
            for trial in manifest["trials"]:
                result = response_for(trial, answer(f"{trial['condition']}-{trial['task_id']}"))
                ab.contract.write_json_atomic(run_dir / trial["response_path"], result)

            judgments_path = root / "judgments.json"
            self.assertEqual(
                0,
                ab.command_pool(
                    Namespace(
                        run_dir=str(run_dir),
                        tasks=str(tasks_path),
                        output=str(judgments_path),
                    )
                ),
            )
            judgments = ab.contract.load_json(judgments_path)
            for item in judgments["items"]:
                item["relevance"] = 1
                item["identity_valid"] = "valid"
                item["constraint_fit"] = 1
            ab.contract.write_json_atomic(judgments_path, judgments)
            metrics_path = root / "metrics.json"
            report_path = root / "report.md"
            self.assertEqual(
                0,
                ab.command_score(
                    Namespace(
                        run_dir=str(run_dir),
                        judgments=str(judgments_path),
                        output=str(metrics_path),
                        report=str(report_path),
                        bootstrap_iterations=100,
                        seed=19,
                    )
                ),
            )
            self.assertTrue(metrics_path.is_file())
            self.assertIn("Retrieval Skill A/B Report", report_path.read_text(encoding="utf-8"))

    def test_load_responses_rejects_unrecognized_files(self):
        manifest, prompts = self.prepared()
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            ab.write_prepared_run(run_dir, manifest, prompts)
            (run_dir / "responses" / "unexpected.json").write_text("{}", encoding="utf-8")
            responses, errors = ab.load_responses(run_dir / "responses", manifest)
            self.assertEqual([], responses)
            self.assertTrue(any("unrecognized response file" in item for item in errors))

    def test_run_codex_trial_uses_ephemeral_skill_isolation_and_records_usage(self):
        manifest, prompts = self.prepared()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            ab.write_prepared_run(run_dir, manifest, prompts)
            source_home = root / "source-home"
            source_home.mkdir()
            (source_home / "auth.json").write_text("{}", encoding="utf-8")
            target_skill = root / "target-skill"
            target_skill.mkdir()
            (target_skill / "SKILL.md").write_text("---\nname: test\ndescription: test\n---\n", encoding="utf-8")
            codex = root / "codex"
            codex.write_text("binary placeholder", encoding="utf-8")
            codex.chmod(0o700)
            observed = []
            commands = []

            class FakeProcess:
                def __init__(self, command, kwargs):
                    self.command = command
                    self.kwargs = kwargs
                    self.pid = 12345
                    self.returncode = 0

                def communicate(self, input=None, timeout=None):
                    isolated_home = Path(self.kwargs["env"]["CODEX_HOME"])
                    condition_has_skill = any((isolated_home / "skills").iterdir())
                    observed.append(condition_has_skill)
                    output_index = self.command.index("--output-last-message") + 1
                    value = answer("runner")
                    value["discovery_trace"] = discovery_trace(
                        mode="used" if condition_has_skill else "not_used",
                        route="recovery" if condition_has_skill else "fast",
                    )
                    Path(self.command[output_index]).write_text(json.dumps(value), encoding="utf-8")
                    events = json.dumps({"usage": {"input_tokens": 120, "output_tokens": 30}})
                    return events, ""

                def poll(self):
                    return self.returncode

                def wait(self, timeout=None):
                    return self.returncode

            def fake_popen(command, **kwargs):
                commands.append(command)
                return FakeProcess(command, kwargs)

            trials = sorted(manifest["trials"], key=lambda item: item["condition"])
            with mock.patch.object(ab.subprocess, "Popen", side_effect=fake_popen):
                for trial in trials:
                    result = ab.run_codex_trial(
                        codex=codex,
                        source_codex_home=source_home,
                        target_skill=target_skill,
                        run_dir=run_dir,
                        manifest=manifest,
                        trial=trial,
                    )
                    self.assertEqual("completed", result["execution"]["status"])
                    self.assertEqual(120, result["execution"]["input_tokens"])
                    self.assertEqual(30, result["execution"]["output_tokens"])
            self.assertIn(False, observed)
            self.assertIn(True, observed)
            self.assertTrue(any("suppress_unstable_features_warning=true" in command for command in commands))

    def test_run_codex_trial_records_timeout_as_failed_response(self):
        manifest, prompts = self.prepared()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            ab.write_prepared_run(run_dir, manifest, prompts)
            source_home = root / "source-home"
            source_home.mkdir()
            (source_home / "auth.json").write_text("{}", encoding="utf-8")
            target_skill = root / "target-skill"
            target_skill.mkdir()
            (target_skill / "SKILL.md").write_text("---\nname: test\ndescription: test\n---\n", encoding="utf-8")
            codex = root / "codex"
            codex.write_text("binary placeholder", encoding="utf-8")
            codex.chmod(0o700)
            class TimeoutProcess:
                def __init__(self):
                    self.pid = 12345
                    self.returncode = None
                    self.calls = 0

                def communicate(self, input=None, timeout=None):
                    self.calls += 1
                    if self.calls == 1:
                        raise subprocess.TimeoutExpired([str(codex)], 1, output="event", stderr="slow")
                    return "", ""

                def poll(self):
                    return None

                def wait(self, timeout=None):
                    self.returncode = -signal.SIGTERM
                    return self.returncode

            with mock.patch.object(ab.subprocess, "Popen", return_value=TimeoutProcess()), mock.patch.object(
                ab.os, "killpg", create=True
            ) as killpg:
                result = ab.run_codex_trial(
                    codex=codex,
                    source_codex_home=source_home,
                    target_skill=target_skill,
                    run_dir=run_dir,
                    manifest=manifest,
                    trial=manifest["trials"][0],
                )
            self.assertEqual("failed", result["execution"]["status"])
            self.assertEqual(124, result["execution"]["executor_exit_code"])
            self.assertIn("hard timeout", result["execution"]["error"])
            killpg.assert_called_once()

    def test_terminate_process_group_cleans_descendants_after_parent_exit(self):
        class ExitedParent:
            pid = 54321

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        with mock.patch.object(ab.os, "killpg", create=True) as killpg:
            ab._terminate_process_group(ExitedParent())
        killpg.assert_called_once_with(54321, signal.SIGTERM)

    def test_command_validate_tasks_reports_pass_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.json"
            invalid = root / "invalid.json"
            valid.write_text(json.dumps(small_tasks()), encoding="utf-8")
            malformed = small_tasks()
            malformed["schema_version"] = 77
            invalid.write_text(json.dumps(malformed), encoding="utf-8")
            self.assertEqual(0, ab.command_validate_tasks(Namespace(tasks=str(valid))))
            self.assertEqual(1, ab.command_validate_tasks(Namespace(tasks=str(invalid))))

    def test_live_runner_requires_regular_auth_and_explicit_confirmation(self):
        args = mock.Mock(confirm_live_run=False)
        with self.assertRaisesRegex(ValueError, "confirm-live-run"):
            ab.command_run(args)
        manifest, prompts = self.prepared()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            ab.write_prepared_run(run_dir, manifest, prompts)
            source_home = root / "source"
            source_home.mkdir()
            target_skill = root / "skill"
            target_skill.mkdir()
            codex = root / "codex"
            codex.write_text("x", encoding="utf-8")
            codex.chmod(0o700)
            with self.assertRaisesRegex(ValueError, "auth.json"):
                ab.run_codex_trial(
                    codex=codex,
                    source_codex_home=source_home,
                    target_skill=target_skill,
                    run_dir=run_dir,
                    manifest=manifest,
                    trial=manifest["trials"][0],
                )


if __name__ == "__main__":
    unittest.main()
