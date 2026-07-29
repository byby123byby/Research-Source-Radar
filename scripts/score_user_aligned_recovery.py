#!/usr/bin/env python3
"""Score hidden-name known-lead recovery for an A/B run.

This is deliberately separate from generic nDCG scoring. It measures whether
the conditions recover an externally declared lead set; it does not infer user
approval for genuinely new neighbors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def matching_lead_ids(sources: list[Any], leads: list[dict[str, Any]]) -> set[str]:
    hits: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        haystack = normalized(f"{source.get('title', '')} {source.get('url', '')}")
        for lead in leads:
            if any(normalized(alias) in haystack for alias in lead["aliases"]):
                hits.add(str(lead["id"]))
    return hits


def lead_hits(response: dict[str, Any], leads: list[dict[str, Any]], k: int) -> set[str]:
    answer = response.get("answer")
    if not isinstance(answer, dict):
        return set()
    sources = answer.get("sources")
    if not isinstance(sources, list):
        return set()
    return matching_lead_ids(sources[:k], leads)


def exploration_hits(response: dict[str, Any], leads: list[dict[str, Any]]) -> set[str]:
    answer = response.get("answer")
    sources = answer.get("sources") if isinstance(answer, dict) else None
    if not isinstance(sources, list):
        return set()
    neighbor_sources = [
        source
        for source in sources
        if isinstance(source, dict) and source.get("role") in {"mechanism", "current", "adjacent"}
    ]
    return matching_lead_ids(neighbor_sources, leads)


def active_loop_trace_mode(response: dict[str, Any]) -> str:
    answer = response.get("answer")
    trace = answer.get("discovery_trace") if isinstance(answer, dict) else None
    return str(trace.get("mode")) if isinstance(trace, dict) else "missing"


def trace_contract_compliant(condition: str, mode: str) -> bool:
    if condition == "skill":
        return mode == "used"
    if condition == "baseline":
        return mode in {"not_used", "blocked"}
    return False


def validate_complete_pairs(
    manifest: dict[str, Any], responses_dir: Path
) -> list[str]:
    """Reject effectiveness scoring when a preregistered pair is incomplete."""

    errors: list[str] = []
    observed: dict[tuple[str, int], set[str]] = defaultdict(set)
    for trial in manifest["trials"]:
        trial_id = str(trial["trial_id"])
        path = responses_dir / f"{trial_id}.json"
        if not path.is_file():
            errors.append(f"{trial_id}: response is missing")
            continue
        response = load(path)
        status = response.get("execution", {}).get("status")
        if status != "completed":
            errors.append(f"{trial_id}: status is {status!r}, expected 'completed'")
            continue
        if response.get("task_id") != trial["task_id"] or response.get("condition") != trial["condition"]:
            errors.append(f"{trial_id}: response identity does not match the manifest")
            continue
        observed[(str(trial["task_id"]), int(trial["repetition"]))].add(str(trial["condition"]))
    for key, conditions in sorted(observed.items()):
        if conditions != {"baseline", "skill"}:
            errors.append(
                f"{key[0]} repetition {key[1]}: incomplete pair {sorted(conditions)}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest = load(run_dir / "trial_manifest.json")
    gold = load(Path(args.gold).expanduser().resolve())
    responses_dir = run_dir / "responses"
    completeness_errors = validate_complete_pairs(manifest, responses_dir)
    if completeness_errors:
        raise SystemExit(
            "refusing to score an incomplete hidden-lead run:\n- "
            + "\n- ".join(completeness_errors)
        )
    lead_sets = gold["lead_sets"]
    rows: list[dict[str, Any]] = []
    for trial in manifest["trials"]:
        path = responses_dir / f"{trial['trial_id']}.json"
        if not path.exists():
            continue
        response = load(path)
        leads = lead_sets[str(trial["task_id"])]
        rows.append(
            {
                "trial_id": trial["trial_id"],
                "task_id": trial["task_id"],
                "condition": trial["condition"],
                "repetition": trial["repetition"],
                "status": response.get("execution", {}).get("status"),
                "hits_at_5": sorted(lead_hits(response, leads, 5)),
                "hits_at_10": sorted(lead_hits(response, leads, 10)),
                "exploration_hits": sorted(exploration_hits(response, leads)),
                "combined_hits_at_10": sorted(
                    lead_hits(response, leads, 10) | exploration_hits(response, leads)
                ),
                "lead_count": len(leads),
                "wall_seconds": response.get("execution", {}).get("wall_seconds"),
                "total_tokens": sum(
                    int(response.get("execution", {}).get(key, 0) or 0)
                    for key in ("input_tokens", "output_tokens")
                ),
                "discovery_trace_mode": active_loop_trace_mode(response),
                "active_loop_trace_present": active_loop_trace_mode(response) == "used",
                "active_loop_trace_compliant": trace_contract_compliant(
                    str(trial["condition"]), active_loop_trace_mode(response)
                ),
                "query_count": len(response.get("answer", {}).get("queries", []))
                if isinstance(response.get("answer"), dict)
                and isinstance(response.get("answer", {}).get("queries"), list)
                else 0,
            }
        )

    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_condition[str(row["condition"])].append(row)

    def summary(condition: str, key: str) -> dict[str, float]:
        values = by_condition.get(condition, [])
        completed = [row for row in values if row["status"] == "completed"]
        denominator = sum(row["lead_count"] for row in completed)
        recovered = sum(len(row[key]) for row in completed)
        total_tokens = sum(int(row["total_tokens"] or 0) for row in completed)
        total_wall_seconds = sum(float(row["wall_seconds"] or 0) for row in completed)
        return {
            "trials": float(len(values)),
            "completed": float(len(completed)),
            "completed_trial_rate": (len(completed) / len(values)) if values else 0.0,
            "recovered_leads": float(recovered),
            "eligible_leads": float(denominator),
            "recovery_rate": (recovered / denominator) if denominator else 0.0,
            "mean_wall_seconds": (
                total_wall_seconds / len(completed)
                if completed
                else 0.0
            ),
            "mean_total_tokens": (
                total_tokens / len(completed)
                if completed
                else 0.0
            ),
            "recovery_per_minute": (recovered / (total_wall_seconds / 60.0)) if total_wall_seconds else 0.0,
            "recovery_per_10k_tokens": (recovered / (total_tokens / 10_000.0)) if total_tokens else 0.0,
            "active_loop_trace_rate": (
                sum(1 for row in completed if row["active_loop_trace_present"]) / len(completed)
                if completed
                else 0.0
            ),
            "active_loop_trace_compliance_rate": (
                sum(1 for row in completed if row["active_loop_trace_compliant"]) / len(completed)
                if completed
                else 0.0
            ),
        }

    paired: list[dict[str, Any]] = []
    index: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        index[(str(row["task_id"]), int(row["repetition"]))][str(row["condition"])] = row
    for key, pair in sorted(index.items()):
        baseline = pair.get("baseline")
        skill = pair.get("skill")
        if not baseline or not skill:
            continue
        baseline_hits = set(baseline["hits_at_10"])
        skill_hits = set(skill["hits_at_10"])
        paired.append(
            {
                "task_id": key[0],
                "repetition": key[1],
                "skill_only_recovery": sorted(skill_hits - baseline_hits),
                "baseline_only_recovery": sorted(baseline_hits - skill_hits),
                "skill_only_combined_recovery": sorted(
                    set(skill["combined_hits_at_10"]) - set(baseline["combined_hits_at_10"])
                ),
                "baseline_only_combined_recovery": sorted(
                    set(baseline["combined_hits_at_10"]) - set(skill["combined_hits_at_10"])
                ),
            }
        )

    payload = {
        "benchmark_id": manifest["benchmark_id"],
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "gold_sha256": hashlib.sha256(Path(args.gold).read_bytes()).hexdigest(),
        "automatic_match_boundary": gold["matching_rule"],
        "condition_summary_at_5": {condition: summary(condition, "hits_at_5") for condition in ("baseline", "skill")},
        "condition_summary_at_10": {condition: summary(condition, "hits_at_10") for condition in ("baseline", "skill")},
        "condition_summary_at_10_combined": {
            condition: summary(condition, "combined_hits_at_10") for condition in ("baseline", "skill")
        },
        "exploration_only_summary": {
            condition: summary(condition, "exploration_hits") for condition in ("baseline", "skill")
        },
        "paired_recovery_at_10": paired,
        "rows": rows,
        "human_review_required": [
            "user_approved_novel@k",
            "mechanism_family_coverage",
            "hard_negative_rate",
            "identity validity beyond alias matching",
        ],
        "claim_boundary": "Automatic alias matching estimates hidden known-lead recovery only. It does not establish that a new neighbor is useful or that the Skill is universally superior.",
    }
    output = Path(args.output).expanduser()
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "rows": len(rows), "paired": len(paired)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
