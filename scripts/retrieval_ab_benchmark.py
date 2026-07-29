#!/usr/bin/env python3
"""Prepare, run, blind, and score paired retrieval-skill A/B trials."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import random
import re
import shutil
import signal
import subprocess  # nosec B404
import sys
import tempfile
import time
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast

import research_contract as contract
import install_skill as installer
from runtime_contract import DEFAULT_MAX_SOURCES, PROFILE_CONTRACTS, SOURCE_ROLES


SCHEMA_VERSION = 1
BENCHMARK_ID = "research-source-radar-cross-domain-v3-v1"
SUPPORTED_BENCHMARK_IDS = {
    BENCHMARK_ID,
    "research-source-radar-user-aligned-v1",
}
RECOVERY_BENCHMARK_IDS = {
    "research-source-radar-user-aligned-v1",
    BENCHMARK_ID,
}
HOLDOUT_BENCHMARK_IDS = {"research-source-radar-user-aligned-v1"}


def find_holdout_leaks(skill_root: Path, gold_path: Path) -> list[str]:
    """Find canonical hidden-lead identifiers exposed to the treatment package."""

    gold = contract.load_json(gold_path)
    lead_sets = gold.get("lead_sets")
    if not isinstance(lead_sets, dict):
        raise ValueError("holdout gold must contain lead_sets")
    identifiers = sorted(
        {
            str(lead.get("id") or "").casefold()
            for leads in lead_sets.values()
            if isinstance(leads, list)
            for lead in leads
            if isinstance(lead, dict) and len(str(lead.get("id") or "")) >= 4
        }
    )
    leaks: list[str] = []
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 5_000_000:
            continue
        try:
            text_value = path.read_text(encoding="utf-8").casefold()
        except UnicodeDecodeError:
            continue
        for identifier in identifiers:
            pattern = rf"(?<![a-z0-9]){re.escape(identifier)}(?![a-z0-9])"
            if re.search(pattern, text_value):
                leaks.append(f"{path.relative_to(skill_root).as_posix()}: {identifier}")
    return leaks
TASK_ID_PATTERN = re.compile(r"TASK-[0-9]{3}")
TRIAL_ID_PATTERN = re.compile(r"TRIAL-[0-9A-F]{16}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
POOL_ID_PATTERN = re.compile(r"J[0-9]{5}")
CONDITIONS = ("baseline", "skill")
CATEGORIES = {
    "exact_identity",
    "ambiguous_seed",
    "similar_work",
    "current_landscape",
    "mechanism_transfer",
}
SOURCE_TYPES = {
    "paper",
    "preprint",
    "github_repository",
    "official_document",
    "model",
    "dataset",
    "technical_blog",
    "standard",
    "other",
}
PRIMARY_METRICS = ("ndcg_at_10", "valid_high_relevance_sources")
MAX_TASKS = 200
MAX_SOURCES = 20
MAX_QUERIES = 50
ACTIVE_LOOP_MAX_QUERIES = 8
RECOVERY_BUDGET = cast(dict[str, int], PROFILE_CONTRACTS["recovery"]["budget"])
MAX_TEXT = 8_000
MAX_ERROR_TAIL = 4_000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def nonempty_string(value: Any, *, limit: int = MAX_TEXT) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def string_list(value: Any, *, require_items: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not require_items)
        and all(nonempty_string(item, limit=1_000) for item in value)
    )


def exact_keys(value: dict[str, Any], expected: set[str], path: str, errors: list[str]) -> None:
    if set(value) != expected:
        errors.append(f"{path} fields must be exactly {sorted(expected)}")


def valid_cutoff(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed <= datetime.now(timezone.utc).date()


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def validate_tasks(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    exact_keys(
        data,
        {
            "schema_version",
            "benchmark_id",
            "cutoff_date",
            "research_question",
            "primary_metrics",
            "safety_metrics",
            "efficiency_metrics",
            "task_sets",
            "tasks",
        },
        "root",
        errors,
    )
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if data.get("benchmark_id") not in SUPPORTED_BENCHMARK_IDS:
        errors.append(f"benchmark_id must be one of {sorted(SUPPORTED_BENCHMARK_IDS)}")
    if not valid_cutoff(data.get("cutoff_date")):
        errors.append("cutoff_date must be a non-future ISO date")
    if not nonempty_string(data.get("research_question"), limit=2_000):
        errors.append("research_question must be a non-empty bounded string")
    if data.get("primary_metrics") != list(PRIMARY_METRICS):
        errors.append(f"primary_metrics must be {list(PRIMARY_METRICS)}")
    if not string_list(data.get("safety_metrics")):
        errors.append("safety_metrics must be a non-empty string list")
    if not string_list(data.get("efficiency_metrics")):
        errors.append("efficiency_metrics must be a non-empty string list")

    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        errors.append("tasks must be a non-empty list")
        raw_tasks = []
    if len(raw_tasks) > MAX_TASKS:
        errors.append(f"tasks must contain at most {MAX_TASKS} entries")
    task_ids: set[str] = set()
    expected_task_fields = {
        "id",
        "category",
        "prompt",
        "constraints",
        "source_types",
        "time_sensitive",
        "evaluation_focus",
    }
    for index, raw in enumerate(raw_tasks):
        path = f"tasks[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{path} must be an object")
            continue
        exact_keys(raw, expected_task_fields, path, errors)
        task_id = raw.get("id")
        if not isinstance(task_id, str) or TASK_ID_PATTERN.fullmatch(task_id) is None:
            errors.append(f"{path}.id must match TASK-NNN")
        elif task_id in task_ids:
            errors.append(f"duplicate task id: {task_id}")
        else:
            task_ids.add(task_id)
        if raw.get("category") not in CATEGORIES:
            errors.append(f"{path}.category is unsupported")
        if not nonempty_string(raw.get("prompt"), limit=4_000):
            errors.append(f"{path}.prompt must be a non-empty bounded string")
        if not string_list(raw.get("constraints")):
            errors.append(f"{path}.constraints must be a non-empty string list")
        source_types = raw.get("source_types")
        if not string_list(source_types) or not isinstance(source_types, list) or any(
            item not in SOURCE_TYPES for item in source_types
        ):
            errors.append(f"{path}.source_types contains unsupported values")
        if not isinstance(raw.get("time_sensitive"), bool):
            errors.append(f"{path}.time_sensitive must be boolean")
        if not nonempty_string(raw.get("evaluation_focus"), limit=1_000):
            errors.append(f"{path}.evaluation_focus must be a non-empty bounded string")

    task_sets = data.get("task_sets")
    if not isinstance(task_sets, dict):
        errors.append("task_sets must be an object")
        task_sets = {}
    else:
        exact_keys(task_sets, {"pilot", "main"}, "task_sets", errors)
    pilot = task_sets.get("pilot")
    main = task_sets.get("main")
    for name, values in (("pilot", pilot), ("main", main)):
        if not isinstance(values, list) or not values:
            errors.append(f"task_sets.{name} must be a non-empty list")
            continue
        if any(not isinstance(item, str) or item not in task_ids for item in values):
            errors.append(f"task_sets.{name} must contain known task IDs")
        if len(set(cast(list[str], values))) != len(values):
            errors.append(f"task_sets.{name} must not contain duplicates")
    if isinstance(pilot, list) and isinstance(main, list) and not set(pilot).issubset(set(main)):
        errors.append("task_sets.pilot must be a subset of task_sets.main")
    return errors


def task_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return {}
    return {
        str(item["id"]): cast(dict[str, Any], item)
        for item in tasks
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def response_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "sources", "queries", "gaps", "constraint_notes", "discovery_trace"],
        "properties": {
            "summary": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
            "sources": {
                "type": "array",
                "maxItems": MAX_SOURCES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "rank",
                        "title",
                        "url",
                        "source_type",
                        "role",
                        "relevance_rationale",
                        "mechanism",
                        "limitations",
                        "research_impact",
                        "project_shift",
                        "mechanism_transfer",
                        "deployment_fit",
                        "next_experiment",
                        "popularity_signal",
                        "popularity_evidence",
                    ],
                    "properties": {
                        "rank": {"type": "integer", "minimum": 1, "maximum": MAX_SOURCES},
                        "title": {"type": "string", "minLength": 1, "maxLength": 1_000},
                        "url": {"type": "string", "minLength": 1, "maxLength": 2_000},
                        "source_type": {"enum": sorted(SOURCE_TYPES)},
                        "role": {"enum": list(SOURCE_ROLES)},
                        "relevance_rationale": {"type": "string", "minLength": 1, "maxLength": 2_000},
                        "mechanism": {"type": "string", "maxLength": 2_000},
                        "limitations": {"type": "string", "maxLength": 2_000},
                        "research_impact": {"enum": ["high", "medium", "low", "exploratory"]},
                        "project_shift": {"type": "string", "maxLength": 2_000},
                        "mechanism_transfer": {"enum": ["direct", "adapt", "represented", "exploratory"]},
                        "deployment_fit": {"enum": ["direct", "partial", "incompatible", "unknown"]},
                        "next_experiment": {"type": "string", "maxLength": 2_000},
                        "popularity_signal": {"enum": ["none", "observed", "triangulated"]},
                        "popularity_evidence": {
                            "type": "array",
                            "maxItems": 6,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["kind", "url", "claim", "independence_group"],
                                "properties": {
                                    "kind": {"type": "string", "minLength": 1, "maxLength": 100},
                                    "url": {"type": "string", "minLength": 1, "maxLength": 2_000},
                                    "claim": {"type": "string", "minLength": 1, "maxLength": 1_000},
                                    "independence_group": {"type": "string", "minLength": 1, "maxLength": 200},
                                },
                            },
                        },
                    },
                },
            },
            "queries": {
                "type": "array",
                "maxItems": MAX_QUERIES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["query", "source"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 2_000},
                        "source": {"type": "string", "minLength": 1, "maxLength": 1_000},
                    },
                },
            },
            "gaps": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 2_000},
                "maxItems": 30,
            },
            "constraint_notes": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 2_000},
                "maxItems": 30,
            },
            "discovery_trace": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "mode",
                    "route",
                    "attempted_families",
                    "covered_families",
                    "uncovered_families",
                    "budget_used",
                    "budget_remaining",
                    "contribution_map",
                    "gap_matrix",
                    "next_query_reason",
                    "bridge_paths",
                    "self_refutation",
                    "stop_evidence",
                ],
                "properties": {
                    "mode": {"enum": ["used", "not_used", "blocked"]},
                    "route": {"enum": ["fast", "recovery", "standard"]},
                    "attempted_families": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 200}},
                    "covered_families": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 200}},
                    "uncovered_families": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 200}},
                    "budget_used": {"type": "object", "additionalProperties": False, "required": ["query_records", "targeted_opens", "gap_probes"], "properties": {
                        "query_records": {"type": "integer", "minimum": 0, "maximum": 8},
                        "targeted_opens": {"type": "integer", "minimum": 0, "maximum": 2},
                        "gap_probes": {"type": "integer", "minimum": 0, "maximum": 1},
                    }},
                    "budget_remaining": {"type": "object", "additionalProperties": False, "required": ["query_records", "targeted_opens", "gap_probes"], "properties": {
                        "query_records": {"type": "integer", "minimum": 0, "maximum": 8},
                        "targeted_opens": {"type": "integer", "minimum": 0, "maximum": 2},
                        "gap_probes": {"type": "integer", "minimum": 0, "maximum": 1},
                    }},
                    "contribution_map": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["problem", "inputs", "mechanism", "outputs", "constraints", "evidence"],
                        "properties": {
                            "problem": {"type": "string", "minLength": 1, "maxLength": 2_000},
                            "inputs": {"type": "string", "minLength": 1, "maxLength": 2_000},
                            "mechanism": {"type": "string", "minLength": 1, "maxLength": 2_000},
                            "outputs": {"type": "string", "minLength": 1, "maxLength": 2_000},
                            "constraints": {"type": "string", "minLength": 1, "maxLength": 2_000},
                            "evidence": {"type": "string", "minLength": 1, "maxLength": 2_000},
                        },
                    },
                    "gap_matrix": {
                        "type": "array",
                        "maxItems": 30,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["family", "status", "missing_atoms", "supporting_sources"],
                            "properties": {
                                "family": {"type": "string", "minLength": 1, "maxLength": 200},
                                "status": {"enum": ["covered", "uncertain", "empty", "not_applicable"]},
                                "missing_atoms": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 200}},
                                "supporting_sources": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 1_000}},
                            },
                        },
                    },
                    "next_query_reason": {"type": "string", "minLength": 1, "maxLength": 2_000},
                    "bridge_paths": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["bridge_type", "from_id", "to_id", "source_locator", "bridge_strength"],
                            "properties": {
                                "bridge_type": {"type": "string", "minLength": 1, "maxLength": 200},
                                "from_id": {"type": "string", "minLength": 1, "maxLength": 1_000},
                                "to_id": {"type": "string", "minLength": 1, "maxLength": 1_000},
                                "source_locator": {"type": "string", "minLength": 1, "maxLength": 2_000},
                                "bridge_strength": {"enum": ["strong", "moderate", "weak", "unresolved"]},
                            },
                        },
                    },
                    "self_refutation": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["repeated_families", "empty_cells", "hard_negative", "transfer_risks"],
                        "properties": {
                            "repeated_families": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 500}},
                            "empty_cells": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 500}},
                            "hard_negative": {"type": "string", "minLength": 1, "maxLength": 2_000},
                            "transfer_risks": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 500}},
                        },
                    },
                    "stop_evidence": {"type": "string", "minLength": 1, "maxLength": 2_000},
                },
            },
        },
    }


def trial_response_schema(condition: str) -> dict[str, Any]:
    """Return the same output contract for both experimental conditions."""
    if condition not in CONDITIONS:
        raise ValueError(f"unsupported condition: {condition}")
    return response_schema()


def build_prompt(
    task: dict[str, Any],
    cutoff_date: str,
    max_sources: int,
    *,
    recovery_route_required: bool = False,
) -> str:
    shared_query_cap = int(
        PROFILE_CONTRACTS["recovery"]["budget"]["query_records"]
        if recovery_route_required
        else PROFILE_CONTRACTS["standard"]["budget"]["query_records"]
    )
    constraints = "\n".join(f"- {item}" for item in cast(list[str], task["constraints"]))
    source_types = ", ".join(cast(list[str], task["source_types"]))
    freshness = "Use sources available by the frozen cutoff date." if task["time_sensitive"] else "Include foundational and current sources where relevant."
    route_instruction = (
        "This task evaluates the installed Skill's recovery route. Do not select fast merely because this is a "
        "benchmark; when the Skill is present, use mode=used and route=recovery. The baseline has no installed Skill "
        "and must use mode=not_used.\n\n"
        if recovery_route_required
        else ""
    )
    return (
        "You are participating in a controlled research-retrieval benchmark.\n"
        "Use any installed skill that directly applies. Search the internet rather than relying only on memory. "
        "Return only JSON matching the provided response schema. Do not mention the experimental condition.\n\n"
        f"Frozen cutoff date: {cutoff_date}\n"
        f"Maximum ranked sources: {max_sources}\n"
        f"Preferred source types: {source_types}\n"
        f"Freshness rule: {freshness}\n\n"
        f"{route_instruction}"
        f"Task: {task['prompt']}\n\n"
        f"Project constraints:\n{constraints}\n\n"
        "Rank one unified source list by usefulness to the task. Give every source one role: direct, mechanism, "
        "validation, current, or adjacent. Use canonical paper, repository, model, dataset, or official URLs. "
        "Record the actual query and source interface used. Separate directly deployable work from mechanisms that can only be adapted. "
        "Keep unresolved identity or evidence gaps visible. Use concise evidence and do not carry raw result pages, full abstracts, "
        "or README bodies into later calls. Always include discovery_trace in the JSON: use mode=used only when an installed "
        "research-discovery skill was actually loaded and its active loop was executed; if no such skill was loaded, use "
        "mode=not_used or blocked. Every source must include the research-impact, transfer, deployment-fit, next-experiment, "
        "and popularity fields; use popularity_signal=none and an empty popularity_evidence list when no attention signal was verified. "
        "Use popularity_signal=triangulated only when popularity_evidence contains at least two distinct independence_group values; "
        "otherwise use observed or none. This benchmark tests research-source discovery across disciplines, but this shared task "
        "prompt must not prescribe condition-specific search, ranking, or discovery behavior; that behavior must come from the "
        "installed Skill or from the baseline agent's ordinary research process. The final queries array is a hard shared "
        f"audit cap: record at most {shared_query_cap} distinct query records. If more search is needed, stop searching, record the missing lane "
        "or timeout in gaps and stop_evidence, and do not emit an additional query record."
    )


def deterministic_trial_id(seed: int, task_id: str, repetition: int, condition: str) -> str:
    digest = hashlib.sha256(f"{seed}|{task_id}|{repetition}|{condition}".encode("utf-8")).hexdigest()
    return f"TRIAL-{digest[:16].upper()}"


def prepare_manifest(
    tasks_data: dict[str, Any],
    *,
    phase: str,
    runs: int,
    seed: int,
    model: str,
    reasoning_effort: str,
    max_wall_seconds: int,
    max_sources: int,
) -> tuple[dict[str, Any], dict[str, str]]:
    errors = validate_tasks(tasks_data)
    if errors:
        raise ValueError("invalid benchmark tasks: " + "; ".join(errors))
    if phase not in {"pilot", "main"}:
        raise ValueError("phase must be pilot or main")
    if not 1 <= runs <= 10:
        raise ValueError("runs must be between 1 and 10")
    if not 30 <= max_wall_seconds <= 3_600:
        raise ValueError("max_wall_seconds must be between 30 and 3600")
    if not 1 <= max_sources <= MAX_SOURCES:
        raise ValueError(f"max_sources must be between 1 and {MAX_SOURCES}")
    task_lookup = task_index(tasks_data)
    set_ids = cast(dict[str, list[str]], tasks_data["task_sets"])[phase]
    prompts: dict[str, str] = {}
    trials: list[dict[str, Any]] = []
    for task_id in set_ids:
        task = task_lookup[task_id]
        prompt = build_prompt(
            task,
            str(tasks_data["cutoff_date"]),
            max_sources,
            recovery_route_required=tasks_data["benchmark_id"] in RECOVERY_BENCHMARK_IDS,
        )
        for repetition in range(1, runs + 1):
            for condition in CONDITIONS:
                trial_id = deterministic_trial_id(seed, task_id, repetition, condition)
                prompt_name = f"prompts/{trial_id}.txt"
                response_name = f"responses/{trial_id}.json"
                prompts[prompt_name] = prompt
                trials.append(
                    {
                        "sequence": 0,
                        "trial_id": trial_id,
                        "task_id": task_id,
                        "repetition": repetition,
                        "condition": condition,
                        "prompt_path": prompt_name,
                        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "response_path": response_name,
                    }
                )
    # A fixed seed is required for reproducible condition assignment.
    generator = random.Random(seed)  # nosec B311
    generator.shuffle(trials)
    for index, trial in enumerate(trials, start=1):
        trial["sequence"] = index
    schema = response_schema()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": tasks_data["benchmark_id"],
        "created_at": utc_now(),
        "cutoff_date": tasks_data["cutoff_date"],
        "phase": phase,
        "seed": seed,
        "runs_per_condition": runs,
        "task_file_sha256": canonical_hash(tasks_data),
        "response_schema_sha256": canonical_hash(schema),
        "conditions": {
            "baseline": {"target_skill_present": False, "other_user_skills_present": False},
            "skill": {"target_skill_present": True, "other_user_skills_present": False},
        },
        "execution": {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "max_wall_seconds": max_wall_seconds,
            "max_sources": max_sources,
            "normalization_policy": "canonical_dedupe_then_cap_and_rerank_v1",
            "fresh_context_per_trial": True,
            "internet_required": True,
            "executor": "codex exec --ephemeral --ignore-user-config",
        },
        "trials": trials,
    }
    return manifest, prompts


def write_prepared_run(output_dir: Path, manifest: dict[str, Any], prompts: dict[str, str]) -> None:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True, mode=0o700)
    (output_dir / "prompts").mkdir(mode=0o700)
    (output_dir / "responses").mkdir(mode=0o700)
    contract.write_json_atomic(output_dir / "trial_manifest.json", manifest)
    contract.write_json_atomic(output_dir / "response_schema.json", response_schema())
    for relative, prompt in prompts.items():
        path = output_dir / relative
        contract.write_text_atomic(path, prompt + "\n", default_mode=0o600)


def validate_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {
        "schema_version",
        "benchmark_id",
        "created_at",
        "cutoff_date",
        "phase",
        "seed",
        "runs_per_condition",
        "task_file_sha256",
        "response_schema_sha256",
        "conditions",
        "execution",
        "trials",
    }
    exact_keys(data, expected, "manifest", errors)
    if data.get("schema_version") != SCHEMA_VERSION or data.get("benchmark_id") not in SUPPORTED_BENCHMARK_IDS:
        errors.append("manifest schema or benchmark ID is unsupported")
    if parse_timestamp(data.get("created_at")) is None:
        errors.append("manifest created_at must be a timezone-aware ISO timestamp")
    if not valid_cutoff(data.get("cutoff_date")):
        errors.append("manifest cutoff_date must be a non-future ISO date")
    if data.get("phase") not in {"pilot", "main"}:
        errors.append("manifest phase is unsupported")
    if not isinstance(data.get("seed"), int) or isinstance(data.get("seed"), bool):
        errors.append("manifest seed must be an integer")
    runs = data.get("runs_per_condition")
    if not isinstance(runs, int) or isinstance(runs, bool) or not 1 <= runs <= 10:
        errors.append("manifest runs_per_condition must be between 1 and 10")
    for key in ("task_file_sha256", "response_schema_sha256"):
        value = data.get(key)
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            errors.append(f"manifest {key} must be a lowercase SHA-256 digest")
    if data.get("response_schema_sha256") != canonical_hash(response_schema()):
        errors.append("manifest response_schema_sha256 does not match this runner")
    expected_conditions = {
        "baseline": {"target_skill_present": False, "other_user_skills_present": False},
        "skill": {"target_skill_present": True, "other_user_skills_present": False},
    }
    if data.get("conditions") != expected_conditions:
        errors.append("manifest conditions must preserve the frozen isolation design")
    execution = data.get("execution")
    if not isinstance(execution, dict):
        errors.append("manifest execution must be an object")
    else:
        exact_keys(
            execution,
            {
                "model",
                "reasoning_effort",
                "max_wall_seconds",
                "max_sources",
                "normalization_policy",
                "fresh_context_per_trial",
                "internet_required",
                "executor",
            },
            "manifest.execution",
            errors,
        )
        if not nonempty_string(execution.get("model"), limit=200):
            errors.append("manifest.execution.model must be a non-empty bounded string")
        if execution.get("reasoning_effort") not in {"low", "medium", "high"}:
            errors.append("manifest.execution.reasoning_effort is unsupported")
        wall = execution.get("max_wall_seconds")
        if not isinstance(wall, int) or isinstance(wall, bool) or not 30 <= wall <= 3_600:
            errors.append("manifest.execution.max_wall_seconds must be between 30 and 3600")
        source_limit = execution.get("max_sources")
        if not isinstance(source_limit, int) or isinstance(source_limit, bool) or not 1 <= source_limit <= MAX_SOURCES:
            errors.append(f"manifest.execution.max_sources must be between 1 and {MAX_SOURCES}")
        if execution.get("normalization_policy") != "canonical_dedupe_then_cap_and_rerank_v1":
            errors.append("manifest.execution.normalization_policy is unsupported")
        if execution.get("fresh_context_per_trial") is not True:
            errors.append("manifest.execution.fresh_context_per_trial must be true")
        if execution.get("internet_required") is not True:
            errors.append("manifest.execution.internet_required must be true")
        if execution.get("executor") != "codex exec --ephemeral --ignore-user-config":
            errors.append("manifest.execution.executor is unsupported")
    trials = data.get("trials")
    if not isinstance(trials, list) or not trials:
        errors.append("manifest trials must be a non-empty list")
        trials = []
    seen: set[str] = set()
    sequences: set[int] = set()
    pairs: dict[tuple[str, int], dict[str, str]] = {}
    for index, trial in enumerate(trials):
        path = f"trials[{index}]"
        if not isinstance(trial, dict):
            errors.append(f"{path} must be an object")
            continue
        exact_keys(
            trial,
            {
                "sequence",
                "trial_id",
                "task_id",
                "repetition",
                "condition",
                "prompt_path",
                "prompt_sha256",
                "response_path",
            },
            path,
            errors,
        )
        trial_id = trial.get("trial_id")
        if not isinstance(trial_id, str) or TRIAL_ID_PATTERN.fullmatch(trial_id) is None:
            errors.append(f"{path}.trial_id is invalid")
        elif trial_id in seen:
            errors.append(f"duplicate trial_id: {trial_id}")
        else:
            seen.add(trial_id)
        sequence = trial.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            errors.append(f"{path}.sequence must be a positive integer")
        elif sequence in sequences:
            errors.append(f"duplicate trial sequence: {sequence}")
        else:
            sequences.add(sequence)
        task_id = trial.get("task_id")
        if not isinstance(task_id, str) or TASK_ID_PATTERN.fullmatch(task_id) is None:
            errors.append(f"{path}.task_id is invalid")
        condition = trial.get("condition")
        if condition not in CONDITIONS:
            errors.append(f"{path}.condition is invalid")
        repetition = trial.get("repetition")
        if (
            not isinstance(repetition, int)
            or isinstance(repetition, bool)
            or not isinstance(runs, int)
            or not 1 <= repetition <= runs
        ):
            errors.append(f"{path}.repetition is outside the frozen run range")
        for key in ("prompt_path", "response_path"):
            value = trial.get(key)
            relative = Path(value) if isinstance(value, str) else Path("..")
            if (
                not isinstance(value, str)
                or relative.is_absolute()
                or ".." in relative.parts
                or len(relative.parts) != 2
            ):
                errors.append(f"{path}.{key} must be a contained relative path")
        if isinstance(trial_id, str):
            if trial.get("prompt_path") != f"prompts/{trial_id}.txt":
                errors.append(f"{path}.prompt_path does not match trial_id")
            if trial.get("response_path") != f"responses/{trial_id}.json":
                errors.append(f"{path}.response_path does not match trial_id")
        prompt_hash = trial.get("prompt_sha256")
        if not isinstance(prompt_hash, str) or SHA256_PATTERN.fullmatch(prompt_hash) is None:
            errors.append(f"{path}.prompt_sha256 must be a lowercase SHA-256 digest")
        if (
            isinstance(task_id, str)
            and isinstance(repetition, int)
            and not isinstance(repetition, bool)
            and isinstance(condition, str)
            and condition in CONDITIONS
            and isinstance(data.get("seed"), int)
            and not isinstance(data.get("seed"), bool)
            and isinstance(trial_id, str)
            and trial_id != deterministic_trial_id(cast(int, data["seed"]), task_id, repetition, condition)
        ):
            errors.append(f"{path}.trial_id does not match the frozen deterministic assignment")
        if (
            isinstance(task_id, str)
            and isinstance(repetition, int)
            and not isinstance(repetition, bool)
            and isinstance(condition, str)
            and condition in CONDITIONS
            and isinstance(prompt_hash, str)
        ):
            pair = pairs.setdefault((task_id, repetition), {})
            if condition in pair:
                errors.append(f"duplicate condition for task/repetition: {task_id}/{repetition}/{condition}")
            pair[condition] = prompt_hash
    if sequences != set(range(1, len(trials) + 1)):
        errors.append("manifest trial sequences must be contiguous from 1")
    for (task_id, repetition), conditions in sorted(pairs.items()):
        if set(conditions) != set(CONDITIONS):
            errors.append(f"task/repetition lacks a paired condition: {task_id}/{repetition}")
        elif len(set(conditions.values())) != 1:
            errors.append(f"paired prompts differ between conditions: {task_id}/{repetition}")
    return errors


def validate_discovery_trace(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["answer.discovery_trace must be an object"]
    expected = {
        "mode",
        "route",
        "attempted_families",
        "covered_families",
        "uncovered_families",
        "budget_used",
        "budget_remaining",
        "contribution_map",
        "gap_matrix",
        "next_query_reason",
        "bridge_paths",
        "self_refutation",
        "stop_evidence",
    }
    exact_keys(value, expected, "answer.discovery_trace", errors)
    if value.get("mode") not in {"used", "not_used", "blocked"}:
        errors.append("answer.discovery_trace.mode is invalid")
    route = value.get("route")
    if route not in {"fast", "recovery", "standard"}:
        errors.append("answer.discovery_trace.route is invalid")
    for key in ("attempted_families", "covered_families", "uncovered_families"):
        if not string_list(value.get(key), require_items=False):
            errors.append(f"answer.discovery_trace.{key} must be a bounded string list")
    for key in ("budget_used", "budget_remaining"):
        budget = value.get(key)
        if not isinstance(budget, dict):
            errors.append(f"answer.discovery_trace.{key} must be an object")
            continue
        exact_keys(
            budget,
            {"query_records", "targeted_opens", "gap_probes"},
            f"answer.discovery_trace.{key}",
            errors,
        )
        for field in ("query_records", "targeted_opens", "gap_probes"):
            number = budget.get(field)
            if not isinstance(number, int) or isinstance(number, bool) or number < 0:
                errors.append(f"answer.discovery_trace.{key}.{field} must be a non-negative integer")
    contribution_map = value.get("contribution_map")
    if not isinstance(contribution_map, dict):
        errors.append("answer.discovery_trace.contribution_map must be an object")
    else:
        exact_keys(
            contribution_map,
            {"problem", "inputs", "mechanism", "outputs", "constraints", "evidence"},
            "answer.discovery_trace.contribution_map",
            errors,
        )
        for key in ("problem", "inputs", "mechanism", "outputs", "constraints", "evidence"):
            if not nonempty_string(contribution_map.get(key), limit=2_000):
                errors.append(f"answer.discovery_trace.contribution_map.{key} must be non-empty")
    gap_matrix = value.get("gap_matrix")
    if not isinstance(gap_matrix, list) or len(gap_matrix) > 30:
        errors.append("answer.discovery_trace.gap_matrix must contain at most 30 items")
        gap_matrix = []
    for index, item in enumerate(gap_matrix):
        path = f"answer.discovery_trace.gap_matrix[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        exact_keys(item, {"family", "status", "missing_atoms", "supporting_sources"}, path, errors)
        if not nonempty_string(item.get("family"), limit=200):
            errors.append(f"{path}.family must be non-empty")
        if item.get("status") not in {"covered", "uncertain", "empty", "not_applicable"}:
            errors.append(f"{path}.status is invalid")
        for key in ("missing_atoms", "supporting_sources"):
            if not string_list(item.get(key), require_items=False):
                errors.append(f"{path}.{key} must be a bounded string list")
    if not nonempty_string(value.get("next_query_reason"), limit=2_000):
        errors.append("answer.discovery_trace.next_query_reason must be non-empty")
    bridge_paths = value.get("bridge_paths")
    if not isinstance(bridge_paths, list) or len(bridge_paths) > 12:
        errors.append("answer.discovery_trace.bridge_paths must contain at most 12 items")
        bridge_paths = []
    for index, item in enumerate(bridge_paths):
        path = f"answer.discovery_trace.bridge_paths[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        exact_keys(item, {"bridge_type", "from_id", "to_id", "source_locator", "bridge_strength"}, path, errors)
        for key in ("bridge_type", "from_id", "to_id", "source_locator"):
            if not nonempty_string(item.get(key), limit=2_000):
                errors.append(f"{path}.{key} must be non-empty")
        if item.get("bridge_strength") not in {"strong", "moderate", "weak", "unresolved"}:
            errors.append(f"{path}.bridge_strength is invalid")
    self_refutation = value.get("self_refutation")
    if not isinstance(self_refutation, dict):
        errors.append("answer.discovery_trace.self_refutation must be an object")
    else:
        exact_keys(self_refutation, {"repeated_families", "empty_cells", "hard_negative", "transfer_risks"}, "answer.discovery_trace.self_refutation", errors)
        for key in ("repeated_families", "empty_cells", "transfer_risks"):
            if not string_list(self_refutation.get(key), require_items=False):
                errors.append(f"answer.discovery_trace.self_refutation.{key} must be a bounded string list")
        if not nonempty_string(self_refutation.get("hard_negative"), limit=2_000):
            errors.append("answer.discovery_trace.self_refutation.hard_negative must be non-empty")
    if not nonempty_string(value.get("stop_evidence"), limit=2_000):
        errors.append("answer.discovery_trace.stop_evidence must be non-empty")
    return errors


def validate_answer(value: Any, *, max_sources: int = MAX_SOURCES) -> list[str]:
    errors: list[str] = []
    if not isinstance(max_sources, int) or isinstance(max_sources, bool) or not 1 <= max_sources <= MAX_SOURCES:
        return [f"max_sources must be between 1 and {MAX_SOURCES}"]
    if not isinstance(value, dict):
        return ["answer must be an object"]
    allowed_keys = {"summary", "sources", "queries", "gaps", "constraint_notes", "discovery_trace"}
    exact_keys(value, allowed_keys, "answer", errors)
    if not nonempty_string(value.get("summary")):
        errors.append("answer.summary must be a non-empty bounded string")
    sources = value.get("sources")
    if not isinstance(sources, list) or len(sources) > max_sources:
        errors.append(f"answer.sources must be a list of at most {max_sources}")
        sources = []
    seen_ranks: set[int] = set()
    for index, source in enumerate(sources):
        path = f"answer.sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{path} must be an object")
            continue
        required_source_keys = {
            "rank", "title", "url", "source_type", "role", "relevance_rationale", "mechanism", "limitations",
            "research_impact", "project_shift", "mechanism_transfer", "deployment_fit",
            "next_experiment", "popularity_signal", "popularity_evidence",
        }
        unexpected_source_keys = set(source) - required_source_keys
        if unexpected_source_keys:
            errors.append(f"{path} has unexpected fields: {sorted(unexpected_source_keys)}")
        missing_source_keys = required_source_keys - set(source)
        if missing_source_keys:
            errors.append(f"{path} is missing required fields: {sorted(missing_source_keys)}")
        rank = source.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or not 1 <= rank <= MAX_SOURCES:
            errors.append(f"{path}.rank is invalid")
        elif rank in seen_ranks:
            errors.append(f"duplicate source rank: {rank}")
        else:
            seen_ranks.add(rank)
        for key in ("title", "url", "relevance_rationale"):
            if not nonempty_string(source.get(key), limit=2_000):
                errors.append(f"{path}.{key} must be a non-empty bounded string")
        for key in ("mechanism", "limitations"):
            if not isinstance(source.get(key), str) or len(cast(str, source.get(key))) > 2_000:
                errors.append(f"{path}.{key} must be a bounded string")
        if source.get("source_type") not in SOURCE_TYPES:
            errors.append(f"{path}.source_type is unsupported")
        if source.get("role") not in SOURCE_ROLES:
            errors.append(f"{path}.role is unsupported")
        for key, allowed in (
            ("research_impact", {"high", "medium", "low", "exploratory"}),
            ("mechanism_transfer", {"direct", "adapt", "represented", "exploratory"}),
            ("deployment_fit", {"direct", "partial", "incompatible", "unknown"}),
            ("popularity_signal", {"none", "observed", "triangulated"}),
        ):
            if key in source and source.get(key) not in allowed:
                errors.append(f"{path}.{key} is invalid")
        for key in ("project_shift", "next_experiment"):
            if key in source and (not isinstance(source.get(key), str) or len(cast(str, source.get(key))) > 2_000):
                errors.append(f"{path}.{key} must be a bounded string")
        popularity_evidence = source.get("popularity_evidence")
        if "popularity_evidence" in source:
            if not isinstance(popularity_evidence, list) or len(popularity_evidence) > 6:
                errors.append(f"{path}.popularity_evidence must contain at most 6 items")
                popularity_evidence = []
            groups: set[str] = set()
            for evidence_index, item in enumerate(popularity_evidence):
                evidence_path = f"{path}.popularity_evidence[{evidence_index}]"
                if not isinstance(item, dict):
                    errors.append(f"{evidence_path} must be an object")
                    continue
                exact_keys(item, {"kind", "url", "claim", "independence_group"}, evidence_path, errors)
                for field in ("kind", "url", "claim", "independence_group"):
                    if not nonempty_string(item.get(field), limit=2_000):
                        errors.append(f"{evidence_path}.{field} must be non-empty")
                if isinstance(item.get("independence_group"), str):
                    groups.add(item["independence_group"])
            signal = source.get("popularity_signal")
            if signal == "observed" and len(popularity_evidence) < 1:
                errors.append(f"{path}.popularity_signal=observed needs one popularity_evidence item")
            if signal == "triangulated" and len(groups) < 2:
                errors.append(f"{path}.popularity_signal=triangulated needs two independent evidence groups")
    expected_ranks = list(range(1, len(sources) + 1))
    if sorted(seen_ranks) != expected_ranks:
        errors.append("answer source ranks must be contiguous from 1")
    queries = value.get("queries")
    if not isinstance(queries, list) or len(queries) > MAX_QUERIES:
        errors.append(f"answer.queries must be a list of at most {MAX_QUERIES}")
        queries = []
    for index, query in enumerate(queries):
        if not isinstance(query, dict) or set(query) != {"query", "source"}:
            errors.append(f"answer.queries[{index}] must contain query and source")
        elif not nonempty_string(query.get("query"), limit=2_000) or not nonempty_string(
            query.get("source"), limit=1_000
        ):
            errors.append(f"answer.queries[{index}] values must be non-empty bounded strings")
    for key in ("gaps", "constraint_notes"):
        if not string_list(value.get(key), require_items=False):
            errors.append(f"answer.{key} must be a bounded string list")
    errors.extend(validate_discovery_trace(value.get("discovery_trace")))
    trace = value.get("discovery_trace")
    if (
        isinstance(trace, dict)
        and trace.get("mode") == "used"
        and trace.get("route") == "recovery"
        and isinstance(queries, list)
    ):
        used = trace.get("budget_used")
        remaining = trace.get("budget_remaining")
        if isinstance(used, dict) and isinstance(remaining, dict):
            used_queries = used.get("query_records")
            if isinstance(used_queries, int) and not isinstance(used_queries, bool):
                if len(queries) != used_queries:
                    errors.append(
                        "answer.queries count must equal recovery budget_used.query_records"
                    )
                if used_queries > RECOVERY_BUDGET["query_records"]:
                    errors.append(
                        "answer recovery query budget exceeds the runtime contract"
                    )
            for field in ("query_records", "targeted_opens", "gap_probes"):
                used_value = used.get(field)
                remaining_value = remaining.get(field)
                if (
                    isinstance(used_value, int)
                    and not isinstance(used_value, bool)
                    and isinstance(remaining_value, int)
                    and not isinstance(remaining_value, bool)
                    and used_value + remaining_value > RECOVERY_BUDGET[field]
                ):
                    errors.append(
                        f"answer recovery {field} used-plus-actionable-remaining exceeds the runtime contract"
                    )
    if (
        isinstance(value.get("discovery_trace"), dict)
        and value["discovery_trace"].get("mode") == "used"
        and isinstance(queries, list)
        and len(queries) > ACTIVE_LOOP_MAX_QUERIES
    ):
        errors.append(
            f"answer.queries exceeds the active discovery loop budget of {ACTIVE_LOOP_MAX_QUERIES}"
        )
    return errors


def validate_treatment_trace(
    answer: Any,
    *,
    condition: Any,
    benchmark_id: Any,
) -> list[str]:
    if benchmark_id not in RECOVERY_BENCHMARK_IDS:
        return []
    if not isinstance(answer, dict) or not isinstance(answer.get("discovery_trace"), dict):
        return ["recovery benchmark answer must contain discovery_trace"]
    trace = cast(dict[str, Any], answer["discovery_trace"])
    if condition == "skill" and (trace.get("mode"), trace.get("route")) != ("used", "recovery"):
        return ["Skill condition must execute mode=used and route=recovery for this benchmark"]
    if condition == "baseline" and trace.get("mode") != "not_used":
        return ["baseline condition must use discovery_trace.mode=not_used"]
    return []


def validate_response(data: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {
        "schema_version",
        "trial_id",
        "task_id",
        "condition",
        "repetition",
        "execution",
        "answer",
    }
    exact_keys(data, expected, "response", errors)
    trials = manifest.get("trials")
    trial_lookup = (
        {
            str(item["trial_id"]): item
            for item in trials
            if isinstance(item, dict) and isinstance(item.get("trial_id"), str)
        }
        if isinstance(trials, list)
        else {}
    )
    trial_id = data.get("trial_id")
    trial = trial_lookup.get(trial_id) if isinstance(trial_id, str) else None
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append("response schema_version is unsupported")
    if not isinstance(trial_id, str) or trial is None:
        errors.append("response trial_id is not present in the manifest")
    else:
        for key in ("task_id", "condition", "repetition"):
            if data.get(key) != trial.get(key):
                errors.append(f"response {key} does not match the manifest")
    execution = data.get("execution")
    if not isinstance(execution, dict):
        errors.append("response.execution must be an object")
    else:
        execution_keys = {
            "status",
            "model",
            "started_at",
            "ended_at",
            "wall_seconds",
            "input_tokens",
            "output_tokens",
            "executor_exit_code",
            "event_log_sha256",
            "error",
        }
        current_execution_keys = execution_keys | {"empty_query_attempts"}
        normalized_execution_keys = current_execution_keys | {"normalization"}
        if frozenset(execution) not in {frozenset(execution_keys), frozenset(current_execution_keys), frozenset(normalized_execution_keys)}:
            exact_keys(execution, normalized_execution_keys, "response.execution", errors)
        if "empty_query_attempts" in execution:
            value = execution.get("empty_query_attempts")
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append("response.execution.empty_query_attempts must be a non-negative integer")
        if "normalization" in execution:
            normalization = execution.get("normalization")
            normalization_fields = {
                "applied", "raw_source_count", "stored_source_count",
                "deduplicated_source_count", "capped_source_count", "notes",
            }
            if not isinstance(normalization, dict):
                errors.append("response.execution.normalization must be an object")
            else:
                exact_keys(normalization, normalization_fields, "response.execution.normalization", errors)
                if not isinstance(normalization.get("applied"), bool):
                    errors.append("response.execution.normalization.applied must be boolean")
                for key in (
                    "raw_source_count", "stored_source_count",
                    "deduplicated_source_count", "capped_source_count",
                ):
                    number = normalization.get(key)
                    if not isinstance(number, int) or isinstance(number, bool) or number < 0:
                        errors.append(f"response.execution.normalization.{key} must be a non-negative integer")
                if not string_list(normalization.get("notes"), require_items=False):
                    errors.append("response.execution.normalization.notes must be a bounded string list")
        if execution.get("status") not in {"completed", "failed"}:
            errors.append("response.execution.status is invalid")
        expected_model = cast(dict[str, Any], manifest.get("execution", {})).get("model")
        if execution.get("model") != expected_model:
            errors.append("response.execution.model does not match the manifest")
        started_at = parse_timestamp(execution.get("started_at"))
        ended_at = parse_timestamp(execution.get("ended_at"))
        if started_at is None:
            errors.append("response.execution.started_at must be a timezone-aware ISO timestamp")
        if ended_at is None:
            errors.append("response.execution.ended_at must be a timezone-aware ISO timestamp")
        if started_at is not None and ended_at is not None and ended_at < started_at:
            errors.append("response.execution.ended_at must not precede started_at")
        for key in ("wall_seconds",):
            value = execution.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 or not math.isfinite(value):
                errors.append(f"response.execution.{key} must be a finite non-negative number")
        for key in ("input_tokens", "output_tokens", "executor_exit_code"):
            value = execution.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"response.execution.{key} must be a non-negative integer")
        event_hash = execution.get("event_log_sha256")
        if not isinstance(event_hash, str) or SHA256_PATTERN.fullmatch(event_hash) is None:
            errors.append("response.execution.event_log_sha256 must be a lowercase SHA-256 digest")
        if execution.get("status") == "completed":
            source_limit = cast(dict[str, Any], manifest.get("execution", {})).get("max_sources", MAX_SOURCES)
            errors.extend(validate_answer(data.get("answer"), max_sources=source_limit))
            errors.extend(
                validate_treatment_trace(
                    data.get("answer"),
                    condition=data.get("condition"),
                    benchmark_id=manifest.get("benchmark_id"),
                )
            )
            if execution.get("executor_exit_code") != 0:
                errors.append("completed response must have executor_exit_code 0")
            if execution.get("error") != "":
                errors.append("completed response must have an empty error")
        elif data.get("answer") is not None:
            errors.append("failed response must use null answer")
        if not isinstance(execution.get("error"), str) or len(cast(str, execution.get("error"))) > MAX_ERROR_TAIL:
            errors.append("response.execution.error must be a bounded string")
        elif execution.get("status") == "failed" and not cast(str, execution.get("error")).strip():
            errors.append("failed response must record a bounded error")
    return errors


def normalized_title(title: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", title.casefold()).split())


def normalized_source_key(url: str, title: str, source_type: str | None = None) -> str:
    title_key = normalized_title(title)
    if source_type in {"paper", "preprint"} and title_key:
        return f"work:{title_key}"
    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except ValueError:
        parsed = urllib.parse.SplitResult("", "", "", "", "")
    host = (parsed.hostname or "").casefold()
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    if host in {"www.github.com", "github.com"}:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            return f"github:{parts[0].casefold()}/{parts[1].removesuffix('.git').casefold()}"
    if host in {"doi.org", "dx.doi.org"} and path:
        return f"doi:{urllib.parse.unquote(path.lstrip('/')).casefold()}"
    if host in {"arxiv.org", "www.arxiv.org"}:
        match = re.search(r"/(?:abs|pdf)/([^/]+)", path)
        if match:
            return f"arxiv:{match.group(1).removesuffix('.pdf').casefold()}"
    if parsed.scheme in {"http", "https"} and host:
        return urllib.parse.urlunsplit(("https", host, path or "/", "", ""))
    return f"title:{title_key}"


def normalize_answer(value: Any, *, max_sources: int) -> tuple[Any, dict[str, Any]]:
    """Apply the same bounded, auditable source normalization to both conditions."""
    diagnostics: dict[str, Any] = {
        "applied": False,
        "raw_source_count": 0,
        "stored_source_count": 0,
        "deduplicated_source_count": 0,
        "capped_source_count": 0,
        "notes": [],
    }
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        return value, diagnostics
    normalized = copy.deepcopy(value)
    raw_sources = cast(list[Any], normalized["sources"])
    diagnostics["raw_source_count"] = len(raw_sources)
    original_ranks = [source.get("rank") if isinstance(source, dict) else None for source in raw_sources]
    kept: list[Any] = []
    seen: set[str] = set()
    duplicate_count = 0
    for index, source in enumerate(raw_sources):
        if not isinstance(source, dict):
            kept.append(source)
            continue
        title = source.get("title")
        url = source.get("url")
        source_type = source.get("source_type")
        if isinstance(title, str) and isinstance(url, str):
            key = normalized_source_key(url, title, source_type if isinstance(source_type, str) else None)
        else:
            key = f"invalid:{index}"
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        kept.append(source)
    capped_count = max(0, len(kept) - max_sources)
    kept = kept[:max_sources]
    for rank, source in enumerate(kept, start=1):
        if isinstance(source, dict):
            source["rank"] = rank
    normalized["sources"] = kept
    diagnostics["stored_source_count"] = len(kept)
    diagnostics["deduplicated_source_count"] = duplicate_count
    diagnostics["capped_source_count"] = capped_count
    notes = cast(list[str], diagnostics["notes"])
    if duplicate_count:
        notes.append(f"removed {duplicate_count} duplicate canonical source(s)")
    if capped_count:
        notes.append(f"omitted {capped_count} source(s) beyond the shared cap of {max_sources}")
    rank_changed = original_ranks[:len(kept)] != list(range(1, len(kept) + 1))
    if rank_changed:
        notes.append("rewrote source ranks to a contiguous sequence")
    diagnostics["applied"] = bool(notes)
    return normalized, diagnostics


def load_responses(response_dir: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    responses: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    trials = cast(list[dict[str, Any]], manifest.get("trials", []))
    expected_paths = {response_dir.parent / str(trial["response_path"]) for trial in trials}
    actual_paths = set(response_dir.glob("*.json")) if response_dir.is_dir() else set()
    for path in sorted(actual_paths - expected_paths):
        errors.append(f"unrecognized response file: {path.name}")
    for path in sorted(actual_paths & expected_paths):
        try:
            data = contract.load_json(path)
        except SystemExit as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        validation = validate_response(data, manifest)
        if validation:
            errors.extend(f"{path.name}: {item}" for item in validation)
            continue
        trial_id = cast(str, data["trial_id"])
        if trial_id in seen:
            errors.append(f"duplicate response for {trial_id}")
            continue
        seen.add(trial_id)
        responses.append(data)
    return responses, errors


def response_candidates(answer: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Return the unified ranked list with each candidate's declared role."""
    return [
        (source, str(source.get("role", "direct")))
        for source in cast(list[dict[str, Any]], answer["sources"])
    ]


def build_blind_pool(
    tasks_data: dict[str, Any], manifest: dict[str, Any], responses: list[dict[str, Any]]
) -> dict[str, Any]:
    task_errors = validate_tasks(tasks_data)
    manifest_errors = validate_manifest(manifest)
    if task_errors or manifest_errors:
        raise ValueError("invalid pool inputs: " + "; ".join([*task_errors, *manifest_errors]))
    if canonical_hash(tasks_data) != manifest.get("task_file_sha256"):
        raise ValueError("task file does not match the frozen manifest")
    response_errors = [
        error
        for response in responses
        for error in validate_response(response, manifest)
    ]
    if response_errors:
        raise ValueError("invalid pool responses: " + "; ".join(response_errors))
    tasks = task_index(tasks_data)
    pooled: dict[tuple[str, str], dict[str, Any]] = {}
    for response in responses:
        if cast(dict[str, Any], response["execution"])["status"] != "completed":
            continue
        answer = cast(dict[str, Any], response["answer"])
        for source, _role in response_candidates(answer):
            key = normalized_source_key(
                str(source["url"]), str(source["title"]), str(source["source_type"])
            )
            pool_key = (str(response["task_id"]), key)
            item = pooled.setdefault(
                pool_key,
                {
                    "pool_id": "",
                    "task_id": response["task_id"],
                    "task_prompt": tasks[str(response["task_id"])]["prompt"],
                    "task_constraints": tasks[str(response["task_id"])]["constraints"],
                    "evaluation_focus": tasks[str(response["task_id"])]["evaluation_focus"],
                    "source_key": key,
                    "title": source["title"],
                    "url": source["url"],
                    "source_types": [],
                    "relevance": None,
                    "identity_valid": "unjudged",
                    "constraint_fit": None,
                    "notes": "",
                },
            )
            if source["source_type"] not in item["source_types"]:
                cast(list[str], item["source_types"]).append(str(source["source_type"]))
    items = sorted(pooled.values(), key=lambda item: (str(item["task_id"]), str(item["source_key"])))
    for index, item in enumerate(items, start=1):
        item["pool_id"] = f"J{index:05d}"
        cast(list[str], item["source_types"]).sort()
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": manifest["benchmark_id"],
        "created_at": utc_now(),
        "manifest_sha256": canonical_hash(manifest),
        "blinding": "condition and repetition removed; judge source relevance and identity independently",
        "scale": {
            "relevance": {"0": "irrelevant", "1": "relevant", "2": "highly relevant"},
            "identity_valid": ["unjudged", "valid", "invalid", "unresolved"],
            "constraint_fit": {"0": "incompatible", "1": "mechanism transfer", "2": "direct fit"},
        },
        "items": items,
    }


def validate_judgments(
    data: dict[str, Any], expected_manifest_hash: str, expected_benchmark_id: str = BENCHMARK_ID
) -> list[str]:
    errors: list[str] = []
    exact_keys(
        data,
        {"schema_version", "benchmark_id", "created_at", "manifest_sha256", "blinding", "scale", "items"},
        "judgments",
        errors,
    )
    if data.get("schema_version") != SCHEMA_VERSION or data.get("benchmark_id") != expected_benchmark_id:
        errors.append("judgment schema or benchmark ID is unsupported")
    if data.get("manifest_sha256") != expected_manifest_hash:
        errors.append("judgments do not belong to this manifest")
    if parse_timestamp(data.get("created_at")) is None:
        errors.append("judgments.created_at must be a timezone-aware ISO timestamp")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return errors + ["judgments.items must be a non-empty list"]
    seen: set[str] = set()
    seen_sources: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        path = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        exact_keys(
            item,
            {
                "pool_id",
                "task_id",
                "task_prompt",
                "task_constraints",
                "evaluation_focus",
                "source_key",
                "title",
                "url",
                "source_types",
                "relevance",
                "identity_valid",
                "constraint_fit",
                "notes",
            },
            path,
            errors,
        )
        pool_id = item.get("pool_id")
        if not isinstance(pool_id, str) or POOL_ID_PATTERN.fullmatch(pool_id) is None or pool_id in seen:
            errors.append(f"{path}.pool_id is invalid or duplicated")
        else:
            seen.add(pool_id)
        if item.get("relevance") not in {0, 1, 2}:
            errors.append(f"{path}.relevance must be 0, 1, or 2")
        if item.get("identity_valid") not in {"valid", "invalid", "unresolved"}:
            errors.append(f"{path}.identity_valid must be judged")
        if item.get("constraint_fit") not in {0, 1, 2}:
            errors.append(f"{path}.constraint_fit must be 0, 1, or 2")
        task_id = item.get("task_id")
        source_key = item.get("source_key")
        if not isinstance(task_id, str) or TASK_ID_PATTERN.fullmatch(task_id) is None:
            errors.append(f"{path}.task_id is invalid")
        if not nonempty_string(source_key, limit=2_000):
            errors.append(f"{path}.source_key is invalid")
        if isinstance(task_id, str) and isinstance(source_key, str):
            pair = (task_id, source_key)
            if pair in seen_sources:
                errors.append(f"{path} duplicates a judged task/source")
            seen_sources.add(pair)
        for key in ("task_prompt", "evaluation_focus", "title", "url"):
            if not nonempty_string(item.get(key), limit=4_000):
                errors.append(f"{path}.{key} must be a non-empty bounded string")
        if not string_list(item.get("task_constraints")):
            errors.append(f"{path}.task_constraints must be a non-empty bounded string list")
        source_types = item.get("source_types")
        if (
            not isinstance(source_types, list)
            or not source_types
            or any(value not in SOURCE_TYPES for value in source_types)
            or len(set(cast(list[str], source_types))) != len(source_types)
        ):
            errors.append(f"{path}.source_types must be a unique supported list")
        if not isinstance(item.get("notes"), str) or len(cast(str, item.get("notes"))) > 4_000:
            errors.append(f"{path}.notes must be a bounded string")
    return errors


def dcg(relevances: list[int], k: int) -> float:
    return float(sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(relevances[:k])))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def trial_metrics(
    response: dict[str, Any], judgments: dict[tuple[str, str], dict[str, Any]]
) -> dict[str, float]:
    execution = cast(dict[str, Any], response["execution"])
    if execution["status"] != "completed":
        return {
            "completion": 0.0,
            "ndcg_at_10": 0.0,
            "precision_at_10": 0.0,
            "pooled_recall_at_20": 0.0,
            "valid_high_relevance_sources": 0.0,
            "invalid_source_rate": 0.0,
            "direct_fit_sources": 0.0,
            "unified_source_count": 0.0,
            "primary_source_count": 0.0,
            "exploration_source_count": 0.0,
            "exploration_valid_relevant_sources": 0.0,
            "exploration_valid_high_relevance_sources": 0.0,
            "discovery_valid_relevant_sources": 0.0,
            "valid_relevant_per_1k_tokens": 0.0,
            "valid_relevant_per_minute": 0.0,
            "wall_seconds": float(execution["wall_seconds"]),
            "total_tokens": float(execution["input_tokens"] + execution["output_tokens"]),
        }
    task_id = str(response["task_id"])
    answer = cast(dict[str, Any], response["answer"])
    sources = sorted(cast(list[dict[str, Any]], answer["sources"]), key=lambda x: int(x["rank"]))
    rows: list[dict[str, Any]] = []
    direct_rows: list[dict[str, Any]] = []
    exploration_rows: list[dict[str, Any]] = []
    for source in sources:
        key = normalized_source_key(
            str(source["url"]), str(source["title"]), str(source["source_type"])
        )
        judgment = judgments[(task_id, key)]
        rows.append(judgment)
        if source.get("role") in {"direct", "validation"}:
            direct_rows.append(judgment)
        else:
            exploration_rows.append(judgment)
    relevances = [int(row["relevance"]) for row in rows]
    all_relevant = sum(1 for (judged_task, _), row in judgments.items() if judged_task == task_id and int(row["relevance"]) >= 1)
    retrieved_relevant = sum(1 for row in rows[:20] if int(row["relevance"]) >= 1)
    ideal = sorted(
        [int(row["relevance"]) for (judged_task, _), row in judgments.items() if judged_task == task_id],
        reverse=True,
    )
    ideal_dcg = dcg(ideal, 10)
    valid_relevant = sum(
        1 for row in rows if int(row["relevance"]) >= 1 and row["identity_valid"] == "valid"
    )
    high_valid = sum(
        1 for row in rows if int(row["relevance"]) == 2 and row["identity_valid"] == "valid"
    )
    invalid = sum(1 for row in rows if row["identity_valid"] == "invalid")
    direct_fit = sum(
        1
        for row in direct_rows
        if int(row["relevance"]) >= 1
        and row["identity_valid"] == "valid"
        and int(row["constraint_fit"]) == 2
    )
    exploration_valid_relevant = sum(
        1
        for row in exploration_rows
        if int(row["relevance"]) >= 1 and row["identity_valid"] == "valid"
    )
    exploration_high_valid = sum(
        1
        for row in exploration_rows
        if int(row["relevance"]) == 2 and row["identity_valid"] == "valid"
    )
    discovery_valid_relevant = valid_relevant
    tokens = int(execution["input_tokens"]) + int(execution["output_tokens"])
    minutes = float(execution["wall_seconds"]) / 60.0
    return {
        "completion": 1.0,
        "ndcg_at_10": dcg(relevances, 10) / ideal_dcg if ideal_dcg else 0.0,
        "precision_at_10": sum(1 for value in relevances[:10] if value >= 1) / 10.0,
        "pooled_recall_at_20": retrieved_relevant / all_relevant if all_relevant else 0.0,
        "valid_high_relevance_sources": float(high_valid),
        "invalid_source_rate": invalid / len(rows) if rows else 0.0,
        "direct_fit_sources": float(direct_fit),
        "unified_source_count": float(len(rows)),
        "primary_source_count": float(len(direct_rows)),
        "exploration_source_count": float(len(exploration_rows)),
        "exploration_valid_relevant_sources": float(exploration_valid_relevant),
        "exploration_valid_high_relevance_sources": float(exploration_high_valid),
        "discovery_valid_relevant_sources": float(discovery_valid_relevant),
        "valid_relevant_per_1k_tokens": valid_relevant * 1_000.0 / tokens if tokens else 0.0,
        "valid_relevant_per_minute": valid_relevant / minutes if minutes else 0.0,
        "wall_seconds": float(execution["wall_seconds"]),
        "total_tokens": float(tokens),
    }


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def bootstrap_task_difference(
    task_values: dict[str, tuple[float, float]], *, iterations: int, seed: int
) -> dict[str, float]:
    if not task_values:
        return {"mean_difference": 0.0, "ci95_low": 0.0, "ci95_high": 0.0, "win_rate": 0.0}
    task_ids = sorted(task_values)
    differences = [task_values[task_id][1] - task_values[task_id][0] for task_id in task_ids]
    # A fixed seed is required for reproducible bootstrap intervals.
    generator = random.Random(seed)  # nosec B311
    samples = [
        mean([differences[generator.randrange(len(differences))] for _ in differences])
        for _ in range(iterations)
    ]
    return {
        "mean_difference": mean(differences),
        "ci95_low": percentile(samples, 0.025),
        "ci95_high": percentile(samples, 0.975),
        "win_rate": sum(1 for value in differences if value > 0) / len(differences),
    }


def score_benchmark(
    manifest: dict[str, Any], responses: list[dict[str, Any]], judgment_data: dict[str, Any], *, iterations: int, seed: int
) -> dict[str, Any]:
    manifest_errors = validate_manifest(manifest)
    if manifest_errors:
        raise ValueError("invalid manifest: " + "; ".join(manifest_errors))
    if not 1 <= iterations <= 1_000_000:
        raise ValueError("bootstrap iterations must be between 1 and 1000000")
    manifest_hash = canonical_hash(manifest)
    errors = validate_judgments(judgment_data, manifest_hash, str(manifest["benchmark_id"]))
    if errors:
        raise ValueError("invalid judgments: " + "; ".join(errors))
    judgment_lookup = {
        (str(item["task_id"]), str(item["source_key"])): item
        for item in cast(list[dict[str, Any]], judgment_data["items"])
    }
    response_errors = [
        error
        for response in responses
        for error in validate_response(response, manifest)
    ]
    if response_errors:
        raise ValueError("invalid responses: " + "; ".join(response_errors))
    response_ids = [str(item["trial_id"]) for item in responses]
    if len(response_ids) != len(set(response_ids)):
        raise ValueError("duplicate responses are not allowed")
    response_lookup = {str(item["trial_id"]): item for item in responses}
    required_trial_ids = [str(item["trial_id"]) for item in cast(list[dict[str, Any]], manifest["trials"])]
    missing = sorted(set(required_trial_ids) - set(response_lookup))
    if missing:
        raise ValueError(f"missing responses for {len(missing)} trials")
    extra = sorted(set(response_lookup) - set(required_trial_ids))
    if extra:
        raise ValueError(f"responses contain {len(extra)} trials outside the manifest")
    expected_judgments = {
        (
            str(response["task_id"]),
            normalized_source_key(
                str(source["url"]), str(source["title"]), str(source["source_type"])
            ),
        )
        for response in responses
        if cast(dict[str, Any], response["execution"])["status"] == "completed"
        for source, _role in response_candidates(cast(dict[str, Any], response["answer"]))
    }
    if set(judgment_lookup) != expected_judgments:
        raise ValueError("judgments must match the exact pooled task/source set")
    by_trial = {
        str(response["trial_id"]): trial_metrics(response, judgment_lookup)
        for response in responses
    }
    metric_names = sorted(next(iter(by_trial.values()))) if by_trial else []
    condition_summary: dict[str, dict[str, float]] = {}
    for condition in CONDITIONS:
        matching = [
            by_trial[trial_id]
            for trial_id, response in response_lookup.items()
            if response["condition"] == condition
        ]
        condition_summary[condition] = {
            metric: mean([row[metric] for row in matching]) for metric in metric_names
        }
    paired: dict[str, dict[str, float]] = {}
    for metric in metric_names:
        by_task_condition: dict[str, dict[str, list[float]]] = {}
        for trial_id, response in response_lookup.items():
            task_id = str(response["task_id"])
            condition = str(response["condition"])
            by_task_condition.setdefault(task_id, {"baseline": [], "skill": []})[condition].append(
                by_trial[trial_id][metric]
            )
        task_values = {
            task_id: (mean(values["baseline"]), mean(values["skill"]))
            for task_id, values in by_task_condition.items()
            if values["baseline"] and values["skill"]
        }
        paired[metric] = bootstrap_task_difference(task_values, iterations=iterations, seed=seed)
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": manifest["benchmark_id"],
        "scored_at": utc_now(),
        "manifest_sha256": manifest_hash,
        "judgments_sha256": canonical_hash(judgment_data),
        "trial_count": len(required_trial_ids),
        "completed_response_count": sum(
            1 for response in responses if cast(dict[str, Any], response["execution"])["status"] == "completed"
        ),
        "condition_summary": condition_summary,
        "paired_task_bootstrap": paired,
        "bootstrap": {"iterations": iterations, "seed": seed, "unit": "task"},
        "claim_boundary": (
            "Results estimate performance on this frozen pooled-judgment benchmark only. "
            "They do not prove exhaustive discovery or generalize automatically to other models, dates, domains, or tools."
        ),
    }


def render_report(metrics: dict[str, Any]) -> str:
    lines = [
        "# Retrieval Skill A/B Report",
        "",
        f"- Benchmark: `{metrics['benchmark_id']}`",
        f"- Scored at: `{metrics['scored_at']}`",
        f"- Trials: {metrics['trial_count']}",
        f"- Completed responses: {metrics['completed_response_count']}",
        "",
        "## Condition Means",
        "",
        "| Metric | Baseline | Skill |",
        "|---|---:|---:|",
    ]
    summaries = cast(dict[str, dict[str, float]], metrics["condition_summary"])
    for metric in sorted(summaries["baseline"]):
        lines.append(f"| {metric} | {summaries['baseline'][metric]:.4f} | {summaries['skill'][metric]:.4f} |")
    lines.extend(
        [
            "",
            "## Paired Task-Level Differences",
            "",
            "Positive values favor the Skill condition.",
            "",
            "| Metric | Mean difference | 95% bootstrap CI | Task win rate |",
            "|---|---:|---:|---:|",
        ]
    )
    paired = cast(dict[str, dict[str, float]], metrics["paired_task_bootstrap"])
    for metric in sorted(paired):
        row = paired[metric]
        lines.append(
            f"| {metric} | {row['mean_difference']:.4f} | "
            f"[{row['ci95_low']:.4f}, {row['ci95_high']:.4f}] | {row['win_rate']:.1%} |"
        )
    lines.extend(["", "## Claim Boundary", "", str(metrics["claim_boundary"]), ""])
    return "\n".join(lines)


def recursive_usage(value: Any) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "input_tokens" and isinstance(child, int) and not isinstance(child, bool):
                    input_tokens = max(input_tokens, child)
                elif key == "output_tokens" and isinstance(child, int) and not isinstance(child, bool):
                    output_tokens = max(output_tokens, child)
                elif isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
    return input_tokens, output_tokens


def parse_event_usage(payload: str) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            event = contract.strict_json_loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        current_input, current_output = recursive_usage(event)
        input_tokens = max(input_tokens, current_input)
        output_tokens = max(output_tokens, current_output)
    return input_tokens, output_tokens


def count_empty_query_attempts(payload: str) -> int:
    """Count completed malformed searches, excluding normal started events.

    The JSON event stream emits ``item.started`` records with an empty
    placeholder query before the actual ``item.completed`` search record.
    Counting the placeholder would make every valid search look malformed.
    """
    attempts = 0
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            event = contract.strict_json_loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "web_search":
            continue
        action = item.get("action")
        if not isinstance(action, dict) or action.get("type") != "search":
            continue
        query = item.get("query")
        queries = action.get("queries")
        has_empty_query = isinstance(query, str) and not query.strip()
        has_empty_query_list_item = isinstance(queries, list) and any(
            isinstance(value, str) and not value.strip() for value in queries
        )
        if has_empty_query or has_empty_query_list_item:
            attempts += 1
    return attempts


def safe_error_tail(stdout: str, stderr: str) -> str:
    # Keep runner diagnostics ahead of the often much larger JSON event stream.
    # Otherwise a long successful-looking event log can hide the actual schema
    # validation error that made the trial unusable.
    stderr_tail = stderr.strip()[-3_000:]
    stdout_tail = stdout.strip()[-1_000:]
    sections = []
    if stderr_tail:
        sections.append("stderr:\n" + stderr_tail)
    if stdout_tail:
        sections.append("stdout_tail:\n" + stdout_tail)
    combined = "\n".join(sections).strip()
    return contract.display_safe_text(combined[-MAX_ERROR_TAIL:], preserve_newlines=True)


GLOBAL_EXECUTION_BLOCKERS = (
    "you've hit your usage limit",
    "you have hit your usage limit",
    "insufficient_quota",
    "quota exceeded",
    "purchase more credits",
)


def global_execution_blocker(response: dict[str, Any]) -> str | None:
    """Classify failures that invalidate every later trial in the batch."""

    execution = response.get("execution")
    if not isinstance(execution, dict) or execution.get("status") != "failed":
        return None
    error = str(execution.get("error") or "").casefold()
    if any(marker in error for marker in GLOBAL_EXECUTION_BLOCKERS):
        return "account_usage_limit"
    return None


def _text_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:  # nosec B603
    """Reap Codex and descendants so a timed-out web search cannot block the runner."""
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return
    try:
        killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        # The direct child may have exited while a descendant still owns the
        # pipes. There is no process group left only when cleanup is complete.
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=5)


def run_codex_trial(
    *,
    codex: Path,
    source_codex_home: Path,
    target_skill: Path,
    run_dir: Path,
    manifest: dict[str, Any],
    trial: dict[str, Any],
) -> dict[str, Any]:
    if not codex.is_file() or not os.access(codex, os.X_OK):
        raise ValueError(f"codex executable is unavailable: {codex}")
    auth = source_codex_home / "auth.json"
    if not auth.is_file() or auth.is_symlink():
        raise ValueError("source CODEX_HOME must contain a regular auth.json")
    if not target_skill.is_dir() or target_skill.is_symlink():
        raise ValueError("target skill must be a real directory")
    prompt_path = run_dir / str(trial["prompt_path"])
    response_path = run_dir / str(trial["response_path"])
    if response_path.exists() or response_path.is_symlink():
        raise FileExistsError(f"response already exists: {response_path}")
    prompt = prompt_path.read_text(encoding="utf-8")
    if hashlib.sha256(prompt.rstrip("\n").encode("utf-8")).hexdigest() != trial["prompt_sha256"]:
        raise ValueError(f"prompt hash mismatch for {trial['trial_id']}")
    execution = cast(dict[str, Any], manifest["execution"])
    started_at = utc_now()
    started = time.monotonic()
    stdout = ""
    stderr = ""
    returncode = 1
    answer: dict[str, Any] | None = None
    normalization: dict[str, Any] = {
        "applied": False,
        "raw_source_count": 0,
        "stored_source_count": 0,
        "deduplicated_source_count": 0,
        "capped_source_count": 0,
        "notes": [],
    }
    with tempfile.TemporaryDirectory(prefix="retrieval-ab-home-") as home_name, tempfile.TemporaryDirectory(
        prefix="retrieval-ab-work-"
    ) as work_name:
        isolated_home = Path(home_name)
        os.chmod(isolated_home, 0o700)
        (isolated_home / "auth.json").symlink_to(auth)
        (isolated_home / "skills").mkdir(mode=0o700)
        if trial["condition"] == "skill":
            shutil.copytree(target_skill, isolated_home / "skills" / target_skill.name)
        schema_path = Path(work_name) / "response_schema.json"
        contract.write_json_atomic(schema_path, response_schema())
        output_file = Path(work_name) / "last-message.json"
        command = [
            str(codex),
            "--search",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            str(execution["model"]),
            "-c",
            f"model_reasoning_effort={json.dumps(execution['reasoning_effort'])}",
            "-c",
            "suppress_unstable_features_warning=true",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_file),
            "--json",
            "-",
        ]
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(isolated_home)
        process: subprocess.Popen[str] | None = None
        process_terminated = False
        try:
            process = subprocess.Popen(  # nosec B603
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=work_name,
                env=environment,
                start_new_session=True,
            )
            try:
                process_stdout, process_stderr = process.communicate(
                    input=prompt,
                    timeout=int(execution["max_wall_seconds"]),
                )
                stdout = _text_output(process_stdout)
                stderr = _text_output(process_stderr)
                returncode = int(process.returncode or 0)
                if returncode == 0 and output_file.is_file():
                    raw_answer = contract.load_json(output_file)
                    raw_answer, normalization = normalize_answer(
                        raw_answer,
                        max_sources=cast(int, execution["max_sources"]),
                    )
                    answer_errors = validate_answer(
                        raw_answer,
                        max_sources=cast(int, execution["max_sources"]),
                    )
                    answer_errors.extend(
                        validate_treatment_trace(
                            raw_answer,
                            condition=trial["condition"],
                            benchmark_id=manifest["benchmark_id"],
                        )
                    )
                    if answer_errors:
                        stderr = stderr + "\ninvalid final answer: " + "; ".join(answer_errors)
                    else:
                        answer = raw_answer
            except subprocess.TimeoutExpired as exc:
                _terminate_process_group(process)
                process_terminated = True
                process_stdout, process_stderr = process.communicate()
                stdout = _text_output(exc.stdout) + _text_output(process_stdout)
                stderr = _text_output(exc.stderr) + _text_output(process_stderr)
                stderr = stderr + "\ntrial exceeded hard timeout"
                returncode = 124
        finally:
            if process is not None and not process_terminated and process.poll() is None:
                _terminate_process_group(process)
    wall_seconds = time.monotonic() - started
    input_tokens, output_tokens = parse_event_usage(stdout)
    empty_query_attempts = count_empty_query_attempts(stdout)
    event_hash = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    status = "completed" if returncode == 0 and answer is not None else "failed"
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "trial_id": trial["trial_id"],
        "task_id": trial["task_id"],
        "condition": trial["condition"],
        "repetition": trial["repetition"],
        "execution": {
            "status": status,
            "model": execution["model"],
            "started_at": started_at,
            "ended_at": utc_now(),
            "wall_seconds": wall_seconds,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "empty_query_attempts": empty_query_attempts,
            "normalization": normalization,
            "executor_exit_code": returncode if returncode >= 0 else 128 + abs(returncode),
            "event_log_sha256": event_hash,
            "error": "" if status == "completed" else safe_error_tail(stdout, stderr),
        },
        "answer": answer,
    }
    validation = validate_response(envelope, manifest)
    if validation:
        raise RuntimeError("runner produced an invalid response: " + "; ".join(validation))
    contract.write_json_atomic(response_path, envelope)
    return envelope


def load_valid_manifest(path: Path) -> dict[str, Any]:
    data = contract.load_json(path)
    errors = validate_manifest(data)
    if errors:
        raise ValueError("invalid trial manifest: " + "; ".join(errors))
    return data


def command_validate_tasks(args: argparse.Namespace) -> int:
    data = contract.load_json(Path(args.tasks).expanduser())
    errors = validate_tasks(data)
    if errors:
        for error in errors:
            print(f"ERROR: {contract.display_safe_text(error)}")
        return 1
    print(f"TASKS_PASS count={len(cast(list[Any], data['tasks']))}")
    return 0


def command_stage_treatment(args: argparse.Namespace) -> int:
    source = Path(args.source_skill).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    gold = Path(args.holdout_gold).expanduser().resolve()
    staged = installer.stage_package(
        source,
        output,
        force=False,
        benchmark_treatment=True,
    )
    if staged is None:
        raise ValueError("benchmark treatment output must differ from the source Skill")
    try:
        leaks = find_holdout_leaks(staged, gold)
        if leaks:
            raise ValueError("sanitized treatment still exposes hidden leads: " + "; ".join(leaks[:20]))
        os.replace(staged, output)
        installer.fsync_directory(output.parent)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise
    print(f"TREATMENT_READY output={output} holdout_leaks=0")
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    tasks_data = contract.load_json(Path(args.tasks).expanduser())
    manifest, prompts = prepare_manifest(
        tasks_data,
        phase=args.phase,
        runs=args.runs,
        seed=args.seed,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        max_wall_seconds=args.max_wall_seconds,
        max_sources=args.max_sources,
    )
    output_dir = Path(args.output_dir).expanduser()
    write_prepared_run(output_dir, manifest, prompts)
    print(f"PREPARED trials={len(cast(list[Any], manifest['trials']))} output={output_dir}")
    return 0


def run_live_preflight(target_skill: Path) -> dict[str, Any]:
    script = Path(__file__).resolve().with_name("preflight_retrieval_experiment.py")
    try:
        completed = subprocess.run(  # nosec B603
            [sys.executable, str(script), "--skill-root", str(target_skill)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("retrieval preflight timed out; live run blocked") from exc
    try:
        payload = contract.strict_json_loads(completed.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"retrieval preflight returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or completed.returncode != 0 or payload.get("status") != "PASS":
        detail = payload.get("checks") if isinstance(payload, dict) else completed.stderr
        raise ValueError(f"retrieval preflight failed; live run blocked: {detail}")
    return cast(dict[str, Any], payload)


def command_run(args: argparse.Namespace) -> int:
    if not args.confirm_live_run:
        raise ValueError("live execution requires --confirm-live-run")
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest = load_valid_manifest(run_dir / "trial_manifest.json")
    target_skill = Path(args.target_skill).expanduser().resolve()
    preflight_result = run_live_preflight(target_skill)
    holdout_gold = getattr(args, "holdout_gold", None)
    if manifest["benchmark_id"] in HOLDOUT_BENCHMARK_IDS:
        if not holdout_gold:
            raise ValueError("recovery benchmark requires --holdout-gold contamination check")
        leaks = find_holdout_leaks(target_skill, Path(holdout_gold).expanduser().resolve())
        if leaks:
            raise ValueError(
                "treatment package exposes hidden lead identifiers: " + "; ".join(leaks[:20])
            )
    contract.write_json_atomic(run_dir / "preflight_report.json", preflight_result)
    print(f"PREFLIGHT_PASS checks={len(cast(list[Any], preflight_result['checks']))}")
    response_dir = run_dir / "responses"
    completed = 0
    failed = 0
    aborted_reason: str | None = None
    trials = cast(list[dict[str, Any]], manifest["trials"])
    selected = []
    for item in trials:
        if args.condition is not None and item["condition"] != args.condition:
            continue
        if args.task is not None and item["task_id"] != args.task:
            continue
        response_path = response_dir / f"{item['trial_id']}.json"
        if not response_path.exists():
            selected.append(item)
            continue
        if not args.retry_failed:
            continue
        prior = contract.load_json(response_path)
        if prior.get("execution", {}).get("status") != "failed":
            continue
        archive_dir = response_dir / "failed_attempts"
        archive_dir.mkdir(mode=0o700, exist_ok=True)
        archive_path = archive_dir / f"{item['trial_id']}-{int(time.time())}.json"
        response_path.rename(archive_path)
        selected.append(item)
    if args.limit is not None:
        selected = selected[: args.limit]
    for trial in selected:
        print(f"RUN sequence={trial['sequence']} trial={trial['trial_id']} condition={trial['condition']}")
        response = run_codex_trial(
            codex=Path(args.codex).expanduser().resolve(),
            source_codex_home=Path(args.source_codex_home).expanduser().resolve(),
            target_skill=target_skill,
            run_dir=run_dir,
            manifest=manifest,
            trial=trial,
        )
        if cast(dict[str, Any], response["execution"])["status"] == "completed":
            completed += 1
        else:
            failed += 1
            aborted_reason = global_execution_blocker(response)
            if aborted_reason is not None:
                print(
                    "RUN_ABORTED "
                    f"reason={aborted_reason} sequence={trial['sequence']} "
                    "pending_trials_preserved=true"
                )
                break
    attempted = completed + failed
    print(
        f"RUN_COMPLETE attempted={attempted} completed={completed} failed={failed} "
        f"pending={len(selected) - attempted}"
    )
    return 0 if failed == 0 else 1


def command_pool(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest = load_valid_manifest(run_dir / "trial_manifest.json")
    tasks_data = contract.load_json(Path(args.tasks).expanduser())
    task_errors = validate_tasks(tasks_data)
    if task_errors:
        raise ValueError("invalid tasks: " + "; ".join(task_errors))
    responses, response_errors = load_responses(run_dir / "responses", manifest)
    if response_errors:
        raise ValueError("invalid responses: " + "; ".join(response_errors))
    if not responses:
        raise ValueError("no valid responses are available")
    pool = build_blind_pool(tasks_data, manifest, responses)
    output = Path(args.output).expanduser()
    contract.write_json_atomic(output, pool)
    print(f"POOL_READY items={len(cast(list[Any], pool['items']))} output={output}")
    return 0


def command_score(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest = load_valid_manifest(run_dir / "trial_manifest.json")
    responses, response_errors = load_responses(run_dir / "responses", manifest)
    if response_errors:
        raise ValueError("invalid responses: " + "; ".join(response_errors))
    judgments = contract.load_json(Path(args.judgments).expanduser())
    metrics = score_benchmark(
        manifest,
        responses,
        judgments,
        iterations=args.bootstrap_iterations,
        seed=args.seed,
    )
    output = Path(args.output).expanduser()
    report = Path(args.report).expanduser()
    contract.write_json_atomic(output, metrics)
    contract.write_text_atomic(report, render_report(metrics), default_mode=0o600)
    print(f"SCORE_PASS trials={metrics['trial_count']} output={output} report={report}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-tasks", help="Validate a benchmark task set")
    validate.add_argument("--tasks", required=True)
    validate.set_defaults(handler=command_validate_tasks)

    treatment = commands.add_parser(
        "stage-treatment",
        help="Create a holdout-clean treatment package for a known-lead benchmark",
    )
    treatment.add_argument("--source-skill", required=True)
    treatment.add_argument("--output", required=True)
    treatment.add_argument("--holdout-gold", required=True)
    treatment.set_defaults(handler=command_stage_treatment)

    prepare = commands.add_parser("prepare", help="Create a randomized paired A/B run")
    prepare.add_argument("--tasks", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--phase", choices=("pilot", "main"), default="pilot")
    prepare.add_argument("--runs", type=int, default=2)
    prepare.add_argument("--seed", type=int, default=20260716)
    prepare.add_argument("--model", default="gpt-5.6-sol")
    prepare.add_argument("--reasoning-effort", choices=("low", "medium", "high"), default="high")
    prepare.add_argument("--max-wall-seconds", type=int, default=600)
    prepare.add_argument("--max-sources", type=int, default=DEFAULT_MAX_SOURCES)
    prepare.set_defaults(handler=command_prepare)

    run = commands.add_parser("run", help="Execute pending trials with isolated Codex homes")
    run.add_argument("--run-dir", required=True)
    run.add_argument("--codex", required=True)
    run.add_argument("--source-codex-home", required=True)
    run.add_argument("--target-skill", required=True)
    run.add_argument(
        "--holdout-gold",
        help="Hidden known-lead gold used only to reject treatment-package contamination",
    )
    run.add_argument("--condition", choices=CONDITIONS)
    run.add_argument("--task")
    run.add_argument("--limit", type=int)
    run.add_argument("--retry-failed", action="store_true", help="Archive failed responses and retry them")
    run.add_argument("--confirm-live-run", action="store_true")
    run.set_defaults(handler=command_run)

    pool = commands.add_parser("pool", help="Create a condition-blind pooled judgment file")
    pool.add_argument("--run-dir", required=True)
    pool.add_argument("--tasks", required=True)
    pool.add_argument("--output", required=True)
    pool.set_defaults(handler=command_pool)

    score = commands.add_parser("score", help="Score a completely judged pooled benchmark")
    score.add_argument("--run-dir", required=True)
    score.add_argument("--judgments", required=True)
    score.add_argument("--output", required=True)
    score.add_argument("--report", required=True)
    score.add_argument("--bootstrap-iterations", type=int, default=10_000)
    score.add_argument("--seed", type=int, default=20260716)
    score.set_defaults(handler=command_score)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {contract.display_safe_text(exc, preserve_newlines=True)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
