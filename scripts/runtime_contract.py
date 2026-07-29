#!/usr/bin/env python3
"""Load and validate the shared discovery runtime contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime-contract-v1.json"


def load_runtime_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_runtime_contract(data)
    if errors:
        raise ValueError("invalid runtime contract: " + "; ".join(errors))
    return cast(dict[str, Any], data)


def validate_runtime_contract(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    output = data.get("output")
    if not isinstance(output, dict):
        errors.append("output must be an object")
        output = {}
    if output.get("single_ranked_list") is not True:
        errors.append("output.single_ranked_list must be true")
    default_limit = output.get("default_max_sources")
    if not isinstance(default_limit, int) or isinstance(default_limit, bool) or not 1 <= default_limit <= 20:
        errors.append("output.default_max_sources must be an integer from 1 to 20")
    roles = output.get("source_roles")
    if not isinstance(roles, list) or len(roles) < 3 or len(set(roles)) != len(roles):
        errors.append("output.source_roles must be a unique list with at least three roles")
    elif any(not isinstance(role, str) or not role.strip() for role in roles):
        errors.append("output.source_roles must contain non-empty strings")
    normalization = output.get("normalization")
    required_normalization = {
        "applies_equally_to_all_conditions",
        "deduplicate_by_canonical_identity",
        "cap_to_manifest_limit",
        "rerank_contiguously",
        "record_every_change",
    }
    if not isinstance(normalization, dict) or set(normalization) != required_normalization:
        errors.append("output.normalization fields do not match the required policy")
    elif any(normalization.get(key) is not True for key in required_normalization):
        errors.append("all output.normalization policies must be true")
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != {"fast", "recovery", "standard"}:
        errors.append("profiles must contain exactly fast, recovery, and standard")
        profiles = {}
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            errors.append(f"profiles.{name} must be an object")
            continue
        limit = profile.get("max_sources")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            errors.append(f"profiles.{name}.max_sources must be an integer from 1 to 20")
        pool = profile.get("candidate_pool")
        if not isinstance(pool, dict) or not isinstance(pool.get("min"), int) or not isinstance(pool.get("max"), int):
            errors.append(f"profiles.{name}.candidate_pool is invalid")
        elif not 1 <= pool["min"] <= pool["max"] <= 100:
            errors.append(f"profiles.{name}.candidate_pool bounds are invalid")
        budget = profile.get("budget")
        required_budget = {"batched_search_calls", "query_records", "targeted_opens", "gap_probes"}
        if not isinstance(budget, dict) or set(budget) != required_budget:
            errors.append(f"profiles.{name}.budget fields are invalid")
        elif any(
            not isinstance(budget.get(key), int)
            or isinstance(budget.get(key), bool)
            or budget[key] < 0
            for key in required_budget
        ):
            errors.append(f"profiles.{name}.budget values must be non-negative integers")
        elif budget["query_records"] < budget["batched_search_calls"]:
            errors.append(f"profiles.{name}.budget query_records cannot be smaller than batched_search_calls")

        early_stop = profile.get("early_stop")
        required_stop = {
            "min_identity_valid_candidates",
            "min_distinct_families",
            "stop_after_first_batch_when_covered",
            "allow_one_gap_probe_when_incomplete",
            "minimum_discovery_lanes",
        }
        if not isinstance(early_stop, dict) or set(early_stop) != required_stop:
            errors.append(f"profiles.{name}.early_stop fields are invalid")
        elif (
            any(
                not isinstance(early_stop.get(key), int)
                or isinstance(early_stop.get(key), bool)
                or early_stop[key] < 1
                for key in (
                    "min_identity_valid_candidates",
                    "min_distinct_families",
                    "minimum_discovery_lanes",
                )
            )
            or not isinstance(early_stop.get("stop_after_first_batch_when_covered"), bool)
            or not isinstance(early_stop.get("allow_one_gap_probe_when_incomplete"), bool)
        ):
            errors.append(f"profiles.{name}.early_stop values are invalid")

        network = profile.get("network_policy")
        required_network = {
            "soft_timeout_seconds", "hard_timeout_seconds", "same_query_retries", "on_timeout"
        }
        if not isinstance(network, dict) or set(network) != required_network:
            errors.append(f"profiles.{name}.network_policy fields are invalid")
        elif (
            not isinstance(network.get("soft_timeout_seconds"), int)
            or isinstance(network.get("soft_timeout_seconds"), bool)
            or not isinstance(network.get("hard_timeout_seconds"), int)
            or isinstance(network.get("hard_timeout_seconds"), bool)
            or network["soft_timeout_seconds"] < 1
            or network["hard_timeout_seconds"] < network["soft_timeout_seconds"]
            or not isinstance(network.get("same_query_retries"), int)
            or isinstance(network.get("same_query_retries"), bool)
            or network["same_query_retries"] < 0
            or network.get("on_timeout") != "record_gap_and_continue"
        ):
            errors.append(f"profiles.{name}.network_policy values are invalid")
    recovery_profile = profiles.get("recovery") if isinstance(profiles, dict) else None
    if isinstance(recovery_profile, dict):
        completion = recovery_profile.get("completion_policy")
        if not isinstance(completion, dict):
            errors.append("profiles.recovery.completion_policy must be an object")
        else:
            reserve = completion.get("reserve_finalization_seconds")
            stop_after = completion.get("stop_new_discovery_after_seconds")
            if not isinstance(reserve, int) or isinstance(reserve, bool) or not 30 <= reserve <= 180:
                errors.append("profiles.recovery.completion_policy.reserve_finalization_seconds is invalid")
            if not isinstance(stop_after, int) or isinstance(stop_after, bool) or not 60 <= stop_after <= 600:
                errors.append("profiles.recovery.completion_policy.stop_new_discovery_after_seconds is invalid")
            if completion.get("finalize_from_verified_ledger_on_deadline") is not True:
                errors.append("profiles.recovery.completion_policy must finalize from the verified ledger")
            if completion.get("gap_probe_counts_toward_query_records") is not True:
                errors.append("profiles.recovery.completion_policy must count the gap probe toward query records")
    recovery = data.get("recovery")
    if not isinstance(recovery, dict):
        errors.append("recovery must be an object")
    else:
        families = recovery.get("required_families")
        minimum = recovery.get("minimum_attempted_families")
        lanes = recovery.get("required_lanes")
        if not isinstance(families, list) or not families:
            errors.append("recovery.required_families must be a non-empty list")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or not isinstance(families, list) or not 1 <= minimum <= len(families):
            errors.append("recovery.minimum_attempted_families is invalid")
        if not isinstance(lanes, list) or not lanes:
            errors.append("recovery.required_lanes must be a non-empty list")
    if isinstance(profiles, dict) and isinstance(output, dict):
        recovery_profile = profiles.get("recovery")
        if isinstance(recovery_profile, dict) and recovery_profile.get("max_sources") != output.get("default_max_sources"):
            errors.append("recovery max_sources must equal output.default_max_sources")
    return errors


RUNTIME_CONTRACT = load_runtime_contract()
OUTPUT_CONTRACT = cast(dict[str, Any], RUNTIME_CONTRACT["output"])
PROFILE_CONTRACTS = cast(dict[str, dict[str, Any]], RUNTIME_CONTRACT["profiles"])
RECOVERY_CONTRACT = cast(dict[str, Any], RUNTIME_CONTRACT["recovery"])
SOURCE_ROLES = tuple(cast(list[str], OUTPUT_CONTRACT["source_roles"]))
DEFAULT_MAX_SOURCES = cast(int, OUTPUT_CONTRACT["default_max_sources"])
