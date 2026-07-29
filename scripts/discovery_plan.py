#!/usr/bin/env python3
"""Build a bounded, cross-domain candidate-discovery plan.

This is a planning and audit-boundary tool, not a crawler. It emits deterministic
lanes and query families so a host agent cannot silently stop at one search index.
Network retrieval and authoritative verification remain host responsibilities.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from runtime_contract import PROFILE_CONTRACTS, RECOVERY_CONTRACT


SCHEMA_VERSION = 1
MAX_TEXT = 2_000
BUDGET_PROFILES = PROFILE_CONTRACTS
DOMAINS = {
    "computing": {
        "ecosystems": ["github", "gitlab", "package_registries", "huggingface", "arxiv", "conference_artifacts"],
        "source_classes": ["repository", "paper", "model", "dataset", "official_document"],
        "adjacent": "information_science_or_hci",
    },
    "health": {
        "ecosystems": ["pubmed", "europe_pmc", "trial_registries", "guidelines", "regulator_pages", "medrxiv"],
        "source_classes": ["paper", "systematic_review", "trial", "guideline", "protocol"],
        "adjacent": "implementation_science_or_health_informatics",
    },
    "social_science": {
        "ecosystems": ["openalex", "ssrn", "ideas_repec", "nber", "society_pages", "institutional_repositories"],
        "source_classes": ["paper", "working_paper", "dataset", "instrument", "report"],
        "adjacent": "methodology_or_public_policy",
    },
    "business": {
        "ecosystems": ["openalex", "ssrn", "ideas_repec", "company_filings", "standards", "industry_data"],
        "source_classes": ["paper", "working_paper", "filing", "standard", "transparent_report"],
        "adjacent": "operations_or_economics",
    },
    "financial_quant": {
        "ecosystems": ["openalex", "ssrn", "ideas_repec", "nber", "company_filings", "crossref", "standards"],
        "source_classes": ["paper", "working_paper", "preprint", "report", "filing", "dataset", "standard", "official_document"],
        "adjacent": "methods_or_implementation_science",
    },
    "humanities": {
        "ecosystems": ["library_catalogs", "h_net", "humanities_commons", "dh_venues", "institutional_repositories", "openalex"],
        "source_classes": ["monograph", "article", "critical_edition", "archive", "corpus", "catalog_record"],
        "adjacent": "digital_humanities_or_cultural_heritage",
    },
    "arts_design_media": {
        "ecosystems": ["museum_records", "exhibition_catalogs", "artist_archives", "practice_research", "production_credits", "openalex"],
        "source_classes": ["catalog", "archive", "practice_research", "production_record", "critical_source"],
        "adjacent": "design_research_or_media_studies",
    },
    "experimental_science": {
        "ecosystems": ["discipline_repositories", "standards_bodies", "protocols", "datasets", "apparatus_docs", "openalex"],
        "source_classes": ["paper", "protocol", "standard", "dataset", "apparatus_document"],
        "adjacent": "metrology_or_replication_science",
    },
    "multidisciplinary": {
        "ecosystems": ["openalex", "crossref", "institutional_repositories", "domain_registry", "standards", "data_repositories"],
        "source_classes": ["paper", "dataset", "standard", "protocol", "report", "repository"],
        "adjacent": "methods_or_implementation_science",
    },
}

LANE_TEMPLATES = (
    ("exact", "exact name, title, author, owner, alias"),
    ("mechanism", "mechanism and neighboring terminology"),
    ("artifact", "implementation, dependency, dataset, benchmark, successor"),
    ("validation", "evaluation, failure, limitation, correction, replication"),
    ("attention", "dated release, technical coverage, conference or community curation"),
)

# Recovery must not spend its entire query budget paraphrasing the user's
# wording. These slots deliberately include two ways to reach candidates that
# are not obvious from the initial problem statement: a domain-native candidate
# reservoir and a second-hop expansion around the first verified anchor. A host
# may mark a slot unavailable, but may not silently replace it with another
# broad direct-match query.
RECOVERY_QUERY_STRATEGY = (
    {
        "slot": 1,
        "kind": "anchor",
        "purpose": "resolve the task and its concrete deployment boundary",
    },
    {
        "slot": 2,
        "kind": "mechanism_vocabulary",
        "purpose": "search a competing or neighboring mechanism vocabulary",
    },
    {
        "slot": 3,
        "kind": "candidate_reservoir",
        "purpose": "search a domain-native index, survey, topic collection, benchmark, or curator that can expose sibling candidates",
    },
    {
        "slot": 4,
        "kind": "contrast_or_failure",
        "purpose": "search alternatives, limits, failures, successors, or abandoned approaches",
    },
    {
        "slot": 5,
        "kind": "anchor_expansion",
        "purpose": "after resolving an initial candidate, search its related work, maintainers, dependencies, citations, alternatives, or implementation neighbors",
    },
    {
        "slot": 6,
        "kind": "coverage_probe",
        "purpose": "probe the highest-value uncovered family or record why it could not be searched",
    },
)

ECOSYSTEM_HINTS = {
    "github": "repository implementation release issues",
    "gitlab": "repository implementation release issues",
    "package_registries": "package dependency version changelog",
    "huggingface": "model dataset card evaluation",
    "arxiv": "preprint method evaluation limitation",
    "conference_artifacts": "conference paper artifact benchmark",
    "pubmed": "peer reviewed study abstract outcome",
    "europe_pmc": "article abstract outcome protocol",
    "trial_registries": "registered trial protocol outcome",
    "guidelines": "guideline recommendation evidence limitation",
    "regulator_pages": "regulatory notice safety evidence",
    "medrxiv": "preprint method outcome limitation",
    "openalex": "article citation abstract method",
    "ssrn": "working paper method evidence",
    "ideas_repec": "working paper economics method data",
    "nber": "working paper empirical method data",
    "society_pages": "society publication conference method",
    "institutional_repositories": "repository thesis report method",
    "company_filings": "filing disclosure operational evidence",
    "standards": "standard protocol requirements evidence",
    "industry_data": "transparent report dataset methodology",
    "library_catalogs": "catalog record monograph edition provenance",
    "h_net": "humanities discussion review archive method",
    "humanities_commons": "humanities article archive method",
    "dh_venues": "digital humanities project corpus method",
    "museum_records": "museum collection record provenance",
    "exhibition_catalogs": "exhibition catalog practice context",
    "artist_archives": "artist archive process provenance",
    "practice_research": "practice research method documentation",
    "production_credits": "production record process authorship",
    "discipline_repositories": "research repository protocol dataset",
    "protocols": "protocol reproducibility method",
    "datasets": "dataset documentation provenance reuse",
    "apparatus_docs": "apparatus documentation calibration method",
    "crossref": "article metadata DOI authors",
    "domain_registry": "domain index publication metadata",
    "data_repositories": "dataset version provenance documentation",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = " ".join(value.split())
    if not value or len(value) > MAX_TEXT:
        raise ValueError(f"{field} must be non-empty and at most {MAX_TEXT} characters")
    return value


def clean_list(value: Any, field: str, max_items: int = 12) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > max_items:
        raise ValueError(f"{field} must be a list of at most {max_items} strings")
    result = []
    for index, item in enumerate(value):
        result.append(clean_text(item, f"{field}[{index}]"))
    return list(dict.fromkeys(result))


def normalize_domain(value: Any) -> str:
    domain = clean_text(value, "domain").casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "cs": "computing",
        "software": "computing",
        "social": "social_science",
        "arts": "arts_design_media",
        "finance": "financial_quant",
        "financial": "financial_quant",
        "financial_quant": "financial_quant",
        "financial_quantitative": "financial_quant",
        "quant": "financial_quant",
        "quantitative_finance": "financial_quant",
        "fintech": "financial_quant",
    }
    domain = aliases.get(domain, domain)
    if domain not in DOMAINS:
        raise ValueError(f"unsupported domain: {domain}")
    return domain


def normalize_budget_profile(value: Any) -> str:
    profile = clean_text(value, "budget_profile").casefold().replace("-", "_")
    if profile not in BUDGET_PROFILES:
        raise ValueError(f"unsupported budget_profile: {profile}")
    return profile


def bounded_terms(question: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", question)
    return list(dict.fromkeys(words[:12]))


def ecosystem_routes(subject: str, ecosystems: Sequence[str]) -> list[dict[str, str]]:
    return [
        {
            "ecosystem": ecosystem,
            "query_hint": ECOSYSTEM_HINTS.get(ecosystem, "authoritative source method evidence"),
            "query_template": f"{subject} {ECOSYSTEM_HINTS.get(ecosystem, 'authoritative source method evidence')}",
        }
        for ecosystem in ecosystems
    ]


def build_plan(payload: dict[str, Any]) -> dict[str, Any]:
    question = clean_text(payload.get("question"), "question")
    domain = normalize_domain(payload.get("domain", "multidisciplinary"))
    constraints = clean_list(payload.get("constraints"), "constraints")
    known_leads = clean_list(payload.get("known_leads"), "known_leads", max_items=20)
    available_ecosystems = clean_list(payload.get("available_ecosystems"), "available_ecosystems", max_items=40)
    time_window = clean_text(payload.get("time_window", "recent_6m"), "time_window")
    # Open-ended research discovery should search beyond the obvious shortlist by
    # default. Callers can still request fast or standard explicitly.
    budget_profile = normalize_budget_profile(payload.get("budget_profile", "recovery"))
    budget = BUDGET_PROFILES[budget_profile]
    profile = DOMAINS[domain]
    profile_ecosystems = list(profile["ecosystems"])
    adjacent = str(profile["adjacent"])
    terms = bounded_terms(question)
    subject = " ".join(terms[:8]) or question[:120]
    lanes = []
    for lane, purpose in LANE_TEMPLATES:
        lanes.append({
            "lane": lane,
            "purpose": purpose,
            "ecosystems": profile_ecosystems,
            "query": f"{subject} {purpose}",
            "query_records": ecosystem_routes(subject, profile_ecosystems),
            "required_bridge": lane != "attention",
        })
    if domain != "computing":
        lanes.append({
            "lane": "adjacent",
            "purpose": f"concrete mechanism transfer through {adjacent}",
            "ecosystems": [adjacent],
            "query": f"{subject} {adjacent} mechanism evidence",
            "query_records": [{
                "ecosystem": adjacent,
                "query_hint": "adjacent mechanism implementation evidence",
                "query_template": f"{subject} {adjacent} mechanism implementation evidence",
            }],
            "required_bridge": True,
        })
    expected_ecosystems = list(dict.fromkeys(profile_ecosystems + ([adjacent] if domain != "computing" else [])))
    availability_declared = bool(available_ecosystems)
    uncovered = [item for item in expected_ecosystems if availability_declared and item not in available_ecosystems]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "domain": domain,
        "question": question,
        "constraints": constraints,
        "available_ecosystems": available_ecosystems,
        "availability_status": "declared" if availability_declared else "not_declared",
        "known_leads": known_leads,
        "known_leads_runtime_role": "recovery_targets_only",
        "time_window": time_window,
        "source_classes": profile["source_classes"],
        "budget_profile": budget_profile,
        "candidate_pool": {**budget["candidate_pool"], "metadata_only": True},
        "shortlist": {"max_sources": budget["max_sources"], "single_ranked_list": True},
        "budget": dict(budget["budget"]),
        "early_stop": dict(budget["early_stop"]),
        "network_policy": dict(budget["network_policy"]),
        "completion_policy": dict(budget.get("completion_policy", {})),
        "route_policy": {
            "minimum_distinct_ecosystems": 3 if len(expected_ecosystems) >= 3 else len(expected_ecosystems),
            "required_lanes": list(RECOVERY_CONTRACT["required_lanes"]),
            "mechanism_expansion": {
                "required_families": list(RECOVERY_CONTRACT["required_families"]),
                "minimum_attempted_families": RECOVERY_CONTRACT["minimum_attempted_families"],
                "stop_rule": "Do not stop after direct matches alone; leave an explicit family gap or run the gap probe.",
            },
            "attention_is_discovery_only": True,
        },
        "recovery_query_strategy": (
            [dict(item) for item in RECOVERY_QUERY_STRATEGY]
            if budget_profile == "recovery"
            else []
        ),
        "lanes": lanes,
        "audit_gates": [
            "authoritative_identity",
            "two_anchor_matches",
            "concrete_mechanism_or_evidence_bridge",
            "duplicate_and_mirror_collapse",
            "direct_use_vs_transfer_separation",
        ],
        "uncovered_ecosystems": uncovered,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON planning input")
    parser.add_argument("--output", required=True, help="JSON plan output")
    parser.add_argument(
        "--budget-profile",
        choices=sorted(BUDGET_PROFILES),
        help="override the input budget profile (fast, recovery, or standard)",
    )
    args = parser.parse_args()
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    if args.budget_profile is not None:
        payload["budget_profile"] = args.budget_profile
    plan = build_plan(payload)
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "plan_ready",
        "domain": plan["domain"],
        "budget_profile": plan["budget_profile"],
        "lanes": len(plan["lanes"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
