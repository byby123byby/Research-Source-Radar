#!/usr/bin/env python3
"""Fail closed before a live retrieval A/B experiment spends network or tokens."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import discovery_plan
import research_contract as io
import retrieval_ab_benchmark as benchmark
from runtime_contract import (
    DEFAULT_MAX_SOURCES,
    PROFILE_CONTRACTS,
    RUNTIME_CONTRACT,
    SOURCE_ROLES,
    validate_runtime_contract,
)


FORBIDDEN_SCHEMA_KEYWORDS = {
    "$ref", "allOf", "anyOf", "oneOf", "not", "if", "then", "else", "patternProperties"
}
LEGACY_CONTRACT_MARKERS = {
    "max_primary",
    "max_exploration",
    "discovery_trace.exploration",
    "four primary",
    "two exploration",
    "two-bucket",
}

FINGERPRINT_FILES = (
    "SKILL.md",
    "references/runtime-contract-v1.json",
    "references/missed-source-recovery-v5.md",
    "scripts/discovery_plan.py",
    "scripts/retrieval_ab_benchmark.py",
    "scripts/preflight_retrieval_experiment.py",
)

RUNTIME_PARITY_FILES = (
    "references/runtime-contract-v1.json",
    "scripts/runtime_contract.py",
    "scripts/discovery_plan.py",
    "scripts/retrieval_ab_benchmark.py",
    "scripts/preflight_retrieval_experiment.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def contract_fingerprint(skill_root: Path) -> tuple[str, list[dict[str, str]]]:
    records: list[dict[str, str]] = []
    digest = hashlib.sha256()
    for relative in FINGERPRINT_FILES:
        path = skill_root / relative
        if not path.is_file():
            records.append({"path": relative, "sha256": "missing"})
            digest.update(f"{relative}\0missing\n".encode())
            continue
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({"path": relative, "sha256": file_hash})
        digest.update(f"{relative}\0{file_hash}\n".encode())
    return digest.hexdigest(), records


def source(rank: int, suffix: str) -> dict[str, Any]:
    return {
        "rank": rank,
        "title": f"Source {suffix}",
        "url": f"https://github.com/example/{suffix}",
        "source_type": "github_repository",
        "role": SOURCE_ROLES[(rank - 1) % len(SOURCE_ROLES)],
        "relevance_rationale": "matches the target task and one mechanism anchor",
        "mechanism": "bounded mechanism fixture",
        "limitations": "synthetic preflight fixture",
        "research_impact": "high",
        "project_shift": "changes one project decision",
        "mechanism_transfer": "adapt",
        "deployment_fit": "partial",
        "next_experiment": "run a bounded isolated test",
        "popularity_signal": "none",
        "popularity_evidence": [],
    }


def trace() -> dict[str, Any]:
    return {
        "mode": "used",
        "route": "recovery",
        "attempted_families": [
            "task_decomposition", "mechanism_neighbor",
            "artifact_or_ecosystem", "validation_or_failure",
        ],
        "covered_families": ["task_decomposition", "mechanism_neighbor"],
        "uncovered_families": ["current_or_attention"],
        "budget_used": {"query_records": 4, "targeted_opens": 1, "gap_probes": 0},
        "budget_remaining": {"query_records": 2, "targeted_opens": 1, "gap_probes": 1},
        "contribution_map": {
            "problem": "find project-moving sources",
            "inputs": "research question and constraints",
            "mechanism": "multi-family discovery and reranking",
            "outputs": "one ranked source list",
            "constraints": "bounded and auditable",
            "evidence": "canonical identities",
        },
        "gap_matrix": [],
        "next_query_reason": "probe the highest-value uncovered family",
        "bridge_paths": [],
        "self_refutation": {
            "repeated_families": [],
            "empty_cells": [],
            "hard_negative": "a popularity-only source was excluded",
            "transfer_risks": [],
        },
        "stop_evidence": "the shared budget was exhausted after the gap probe",
    }


def answer(count: int) -> dict[str, Any]:
    return {
        "summary": "Synthetic preflight answer",
        "sources": [source(index, f"fixture-{index}") for index in range(1, count + 1)],
        "queries": [
            {"query": f"fixture query {index}", "source": "fixture"}
            for index in range(1, 5)
        ],
        "gaps": [],
        "constraint_notes": [],
        "discovery_trace": trace(),
    }


def schema_keywords(value: Any) -> set[str]:
    found: set[str] = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            found.update(str(key) for key in item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def run_preflight(skill_root: Path, tasks_path: Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "pass" if passed else "fail", "detail": detail})

    runtime_errors = validate_runtime_contract(RUNTIME_CONTRACT)
    record("runtime_contract", not runtime_errors, "; ".join(runtime_errors) or "single source of truth is valid")

    runner_root = Path(__file__).resolve().parents[1]
    parity_errors: list[str] = []
    for relative in RUNTIME_PARITY_FILES:
        runner_path = runner_root / relative
        target_path = skill_root / relative
        if not target_path.is_file():
            parity_errors.append(f"missing:{relative}")
        elif runner_path.read_bytes() != target_path.read_bytes():
            parity_errors.append(f"mismatch:{relative}")
    record(
        "runner_target_parity",
        not parity_errors,
        "runner and target Skill use identical runtime files" if not parity_errors else ", ".join(parity_errors),
    )

    baseline_schema = benchmark.trial_response_schema("baseline")
    skill_schema = benchmark.trial_response_schema("skill")
    record(
        "condition_schema_parity",
        baseline_schema == skill_schema,
        "baseline and Skill use the same response schema",
    )
    forbidden = sorted(schema_keywords(baseline_schema) & FORBIDDEN_SCHEMA_KEYWORDS)
    record(
        "schema_subset",
        not forbidden,
        "no unsupported composition keywords" if not forbidden else f"forbidden keywords: {forbidden}",
    )

    valid = answer(DEFAULT_MAX_SOURCES)
    record(
        "validator_accepts_limit",
        not benchmark.validate_answer(valid, max_sources=DEFAULT_MAX_SOURCES),
        f"validator accepts exactly {DEFAULT_MAX_SOURCES} sources",
    )
    over_limit = answer(DEFAULT_MAX_SOURCES + 2)
    normalized, diagnostics = benchmark.normalize_answer(over_limit, max_sources=DEFAULT_MAX_SOURCES)
    normalize_errors = benchmark.validate_answer(normalized, max_sources=DEFAULT_MAX_SOURCES)
    record(
        "shared_normalization",
        not normalize_errors and diagnostics["capped_source_count"] == 2,
        "; ".join(normalize_errors) or "dedupe/cap/rerank policy produces a valid answer",
    )

    duplicate = copy.deepcopy(valid)
    duplicate["sources"].insert(1, copy.deepcopy(duplicate["sources"][0]))
    duplicate_normalized, duplicate_diagnostics = benchmark.normalize_answer(
        duplicate, max_sources=DEFAULT_MAX_SOURCES
    )
    record(
        "canonical_deduplication",
        duplicate_diagnostics["deduplicated_source_count"] == 1
        and not benchmark.validate_answer(duplicate_normalized, max_sources=DEFAULT_MAX_SOURCES),
        "duplicate canonical identities are removed and recorded",
    )

    plan = discovery_plan.build_plan({
        "question": "preflight research discovery",
        "domain": "multidisciplinary",
    })
    plan_limit = plan.get("shortlist", {}).get("max_sources")
    recovery_profile = PROFILE_CONTRACTS["recovery"]
    planner_matches_runtime = (
        plan.get("budget") == recovery_profile["budget"]
        and plan.get("candidate_pool", {}).get("min") == recovery_profile["candidate_pool"]["min"]
        and plan.get("candidate_pool", {}).get("max") == recovery_profile["candidate_pool"]["max"]
        and plan.get("early_stop") == recovery_profile["early_stop"]
        and plan.get("completion_policy") == recovery_profile["completion_policy"]
    )
    record(
        "planner_output_parity",
        plan_limit == DEFAULT_MAX_SOURCES
        and plan.get("shortlist", {}).get("single_ranked_list") is True
        and planner_matches_runtime,
        (
            f"planner limit={plan_limit}; runtime limit={DEFAULT_MAX_SOURCES}; "
            f"budget and completion policy parity={planner_matches_runtime}"
        ),
    )

    contract_files = [
        skill_root / "SKILL.md",
        skill_root / "references" / "missed-source-recovery-v5.md",
        skill_root / "references" / "fast-budget-route.md",
    ]
    legacy_hits: list[str] = []
    for path in contract_files:
        if not path.is_file():
            legacy_hits.append(f"missing:{path.name}")
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for marker in LEGACY_CONTRACT_MARKERS:
            if marker in text:
                legacy_hits.append(f"{path.name}:{marker}")
    record(
        "documentation_contract_parity",
        not legacy_hits,
        "no legacy two-bucket markers" if not legacy_hits else ", ".join(legacy_hits),
    )

    if tasks_path is not None:
        tasks = io.load_json(tasks_path)
        task_errors = benchmark.validate_tasks(tasks)
        record("task_set", not task_errors, "; ".join(task_errors) or "task set is valid")

    failures = [item for item in checks if item["status"] == "fail"]
    fingerprint, fingerprint_files = contract_fingerprint(skill_root)
    return {
        "schema_version": 1,
        "checked_at": utc_now(),
        "status": "PASS" if not failures else "FAIL",
        "live_run_allowed": not failures,
        "skill_root": str(skill_root),
        "default_max_sources": DEFAULT_MAX_SOURCES,
        "contract_fingerprint": fingerprint,
        "fingerprint_files": fingerprint_files,
        "checks": checks,
        "failure_count": len(failures),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--tasks")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run_preflight(
        Path(args.skill_root).expanduser().resolve(),
        Path(args.tasks).expanduser().resolve() if args.tasks else None,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        io.write_text_atomic(Path(args.output).expanduser(), rendered, default_mode=0o600)
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
