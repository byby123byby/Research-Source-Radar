#!/usr/bin/env python3
"""Build a bounded, cross-domain candidate-discovery plan.

This is a planning and audit-boundary tool, not a crawler. It emits deterministic
lanes and query families so a host agent cannot silently stop at one search index.
Network retrieval and authoritative verification remain host responsibilities.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_contract import PROFILE_CONTRACTS, RECOVERY_CONTRACT
from mechanism_transfer import validate_bridge
from radar_feedback import feedback_issue, validate_profile


SCHEMA_VERSION = 2
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
    "life_science": {
        "ecosystems": ["pubmed", "europe_pmc", "protocols", "data_repositories", "discipline_repositories"],
        "source_classes": ["paper", "protocol", "dataset", "model", "systematic_review"],
        "adjacent": "methods_or_experimental_science",
    },
    "law_policy": {
        "ecosystems": ["official_legal_sources", "regulator_pages", "institutional_repositories", "ssrn", "openalex"],
        "source_classes": ["legislation", "judgment", "policy", "paper", "report", "dataset"],
        "adjacent": "social_science_or_institutional_analysis",
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
    ("reuse", "maintained implementation, current version or successor that removes work from the project"),
)

# Where a reusable result for each field usually lives. Searched in addition to
# the field's literature indexes so "how to do X" also asks "who already built X".
REUSE_ECOSYSTEMS = {
    "computing": ["package_registries", "github", "huggingface"],
    "health": ["package_registries", "github", "guidelines"],
    "life_science": ["package_registries", "github", "protocols"],
    "social_science": ["package_registries", "github", "standards", "data_repositories"],
    "business": ["package_registries", "github", "standards"],
    "financial_quant": ["package_registries", "github", "standards"],
    "humanities": ["dh_venues", "institutional_repositories", "standards"],
    "arts_design_media": ["practice_research", "artist_archives", "standards"],
    "experimental_science": ["protocols", "standards_bodies", "package_registries"],
    "law_policy": ["official_legal_sources", "regulator_pages", "institutional_repositories"],
    "multidisciplinary": ["package_registries", "github", "standards"],
}
FOUNDATION_KINDS = {"method", "standard", "dataset", "tool", "theory", "other"}
CITATION_INDEXES = ["openalex", "crossref"]
REUSE_FAMILIES = ("existing_implementation", "current_version", "successor_citation")

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
    {
        "slot": 7,
        "kind": "reuse_or_successor",
        "purpose": "for the strongest method/standard/dataset anchors, search maintained implementations, current versions and recent citing work one hop out",
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
    "official_legal_sources": "official legislation judgment jurisdiction effective date amendment",
    "standards_bodies": "current standard edition amendment supersedes",
}


def clean_foundation_sources(value: Any) -> list[dict[str, Any]]:
    """Resolved anchors (usually from round one) that deserve a one-hop successor check."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError("foundation_sources must be a list of at most 8 resolved anchors")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"foundation_sources[{index}] must be an object")
        kind = item.get("kind", "other")
        if kind not in FOUNDATION_KINDS:
            raise ValueError(f"foundation_sources[{index}].kind must be one of {sorted(FOUNDATION_KINDS)}")
        result.append({
            "identity": clean_text(item.get("identity"), f"foundation_sources[{index}].identity"),
            "title": clean_text(item.get("title"), f"foundation_sources[{index}].title"),
            "kind": kind,
            "authors": clean_list(item.get("authors"), f"foundation_sources[{index}].authors", max_items=3),
        })
    return result


def per_round_minimums(query_records: int, has_bridges: bool) -> dict[str, int]:
    """Reserve real search capacity so classic direct matches cannot crowd out reuse, recency and long tail."""
    minimums = {
        "reuse": 2 if query_records >= 8 else 1,
        "attention": 1,
        "artifact_or_relation": 1 if query_records >= 6 else 0,
        "adjacent": 1 if has_bridges and query_records >= 6 else 0,
    }
    while sum(minimums.values()) > query_records:
        key = max(minimums, key=lambda name: minimums[name])
        minimums[key] -= 1
    return minimums


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
        "biology": "life_science",
        "biological_science": "life_science",
        "law": "law_policy",
        "policy": "law_policy",
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
    frame = payload.get("project_frame", {})
    if not isinstance(frame, dict):
        raise ValueError("project_frame must be an object")
    frame = {
        "bottleneck": clean_text(frame.get("bottleneck", question), "project_frame.bottleneck"),
        **{key: clean_list(frame.get(key), f"project_frame.{key}") for key in (
            "inputs", "outputs", "constraints", "failure_modes", "mechanism_terms", "evidence_refs",
        )},
    }
    constraints = list(dict.fromkeys(constraints + frame["constraints"]))
    subject = frame["bottleneck"]
    usage: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    def add(lane: str, query: str, refs: list[str], ecosystems: list[str], **extra: Any) -> None:
        query = " ".join(query.split())
        if not query:
            return
        # Merge exact duplicates, retaining their input lineage instead of
        # counting the same search as independent discovery.
        previous = next((item for item in records if item["query"] == query), None)
        if previous is None:
            previous = {"query_id": f"Q{len(records) + 1:03d}", "lane": lane, "query": query,
                        "ecosystems": ecosystems, "derived_from": [], **extra}
            records.append(previous)
        for ref in refs:
            if ref not in previous["derived_from"]:
                previous["derived_from"].append(ref)
            entry = usage.setdefault(ref, {"used_by": []})
            if previous["query_id"] not in entry["used_by"]:
                entry["used_by"].append(previous["query_id"])

    add("exact", subject, ["project_frame.bottleneck"], profile_ecosystems)
    for index, constraint in enumerate(constraints):
        add("exact", f"{subject} {constraint}", ["project_frame.bottleneck", f"constraints[{index}]"], profile_ecosystems)
    for index, lead in enumerate(known_leads):
        add("exact", lead, [f"known_leads[{index}]"], profile_ecosystems, known_lead=True)
    mechanism_terms = frame["mechanism_terms"]
    if mechanism_terms:
        add("mechanism", " ".join(mechanism_terms) + " method implementation", [f"project_frame.mechanism_terms[{i}]" for i in range(len(mechanism_terms))], profile_ecosystems)
    else:
        usage["project_frame.mechanism_terms"] = {"used_by": [], "unused_reason": "Host must extract mechanism vocabulary; topical words alone do not count as mechanism coverage."}
    for key in ("inputs", "outputs", "failure_modes"):
        for index, term in enumerate(frame[key]):
            lane = "validation" if key == "failure_modes" else "mechanism"
            add(lane, f"{subject} {term}", ["project_frame.bottleneck", f"project_frame.{key}[{index}]"], profile_ecosystems)
    for lane, suffix in (("artifact", "survey bibliography dataset implementation"),
                         ("validation", "limitations negative results replication"),
                         ("attention", f"{time_window} release conference community")):
        add(lane, f"{subject} {suffix}", ["project_frame.bottleneck"], profile_ecosystems)

    raw_bridges = payload.get("mechanism_bridges", [])
    if not isinstance(raw_bridges, list) or len(raw_bridges) > 12:
        raise ValueError("mechanism_bridges must be a list of at most 12 bridges")
    bridges = [validate_bridge(item) for item in raw_bridges]
    if len({item["bridge_id"] for item in bridges}) != len(bridges):
        raise ValueError("duplicate bridge_id")
    for bridge in bridges:
        # Deliberately omit the target domain's keywords. Search the foreign
        # vocabulary even when names and citation networks do not overlap.
        try:
            bridge["source_domain"] = normalize_domain(bridge["source_domain"])
        except ValueError:
            # Valid foreign disciplines without a native profile use the fallback.
            pass
        foreign = DOMAINS.get(bridge["source_domain"], DOMAINS["multidisciplinary"])
        for term in bridge["search_terms"]:
            add("adjacent", f"{bridge['source_domain']} {term}", [f"bridge:{bridge['bridge_id']}"], list(foreign["ecosystems"]), bridge_id=bridge["bridge_id"], bridge_status=bridge["status"])
        add("validation", f"{bridge['search_terms'][0]} {' '.join(bridge['breaks_when'])}", [f"bridge:{bridge['bridge_id']}"], list(foreign["ecosystems"]))

    # Reuse family: does a maintained implementation, current version or successor
    # already remove part of the work? Generated from the frame, not from known answers.
    reuse_ecosystems = REUSE_ECOSYSTEMS[domain]
    for index, term in enumerate(mechanism_terms[:4]):
        add("reuse", f"{term} software package implementation toolkit",
            [f"project_frame.mechanism_terms[{index}]"], reuse_ecosystems, family="existing_implementation")
    for index, output in enumerate(frame["outputs"][:3]):
        add("reuse", f"{output} existing tool template implementation",
            [f"project_frame.outputs[{index}]"], reuse_ecosystems, family="existing_implementation")
    add("reuse", f"{subject} current version update guideline standard successor",
        ["project_frame.bottleneck"], list(dict.fromkeys(profile_ecosystems + reuse_ecosystems)), family="current_version")

    foundations = clean_foundation_sources(payload.get("foundation_sources"))
    for index, source in enumerate(foundations):
        ref = f"foundation_sources[{index}]"
        identity = source["identity"]
        add("reuse", f"cited by: {source['title']}", [ref], CITATION_INDEXES,
            family="successor_citation", operation="forward_citations", window="last_24_months", anchor=identity)
        add("reuse", f"\"{source['title']}\" software package implementation", [ref], reuse_ecosystems,
            family="existing_implementation", anchor=identity)
        if source["kind"] in {"standard", "method", "dataset"}:
            add("reuse", f"\"{source['title']}\" updated version extension supersedes", [ref],
                list(dict.fromkeys(profile_ecosystems + reuse_ecosystems)), family="current_version", anchor=identity)
        if source["authors"]:
            add("reuse", f"{source['authors'][0]} software package {source['title']}", [ref], reuse_ecosystems,
                family="author_artifact", anchor=identity)

    relations = payload.get("seed_relations", [])
    if not isinstance(relations, list) or len(relations) > 40:
        raise ValueError("seed_relations must be a list of at most 40 records")
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            raise ValueError("seed relation must be an object")
        anchor = clean_text(relation.get("source_identity"), "seed_relation.source_identity")
        kind = clean_text(relation.get("relation"), "seed_relation.relation")
        evidence = clean_text(relation.get("evidence_ref"), "seed_relation.evidence_ref")
        term = clean_text(relation.get("search_term"), "seed_relation.search_term")
        add("artifact", f"{term} {kind}", [f"seed_relations[{index}]"], profile_ecosystems, anchor=anchor, evidence_ref=evidence)

    project_id = payload.get("project_id", "")
    ranking_policy: list[dict[str, Any]] = []
    feedback = payload.get("preference_events", [])
    if not isinstance(feedback, list) or len(feedback) > 120:
        raise ValueError("preference_events must be a bounded list")
    for index, event in enumerate(feedback):
        ref = f"preference_events[{index}]"
        issue = feedback_issue(event, project_id)
        if issue:
            usage[ref] = {"used_by": [], "unused_reason": issue, "status": "quarantined"}
            continue
        label = event["label"]
        terms = event["evidence"]["confirmed_terms"]
        if label in {"worth_deepening", "mechanism_to_borrow"}:
            query = " ".join(terms) if terms else event["title"]
            add("mechanism", f"{query} related methods alternatives", [ref], profile_ecosystems)
            effect = "deep_priority" if label == "worth_deepening" else "mechanism_reference"
        elif label in {"not_useful_now", "already_known", "reference_only"}:
            effect = "candidate_only"
        elif label == "avoid_similar":
            effect = ("downweight_explicit_dimensions"
                      if terms and event["evidence"]["scope"] == "dimension"
                      else "downweight_candidate")
        else:
            usage[ref] = {"used_by": [], "unused_reason": "neutral feedback or no explicitly scoped dimensions; no positive expansion"}
            continue
        ranking_policy.append({"event_ref": ref, "candidate_id": event["candidate_id"],
                               "source_identity": event["evidence"]["source_identity"],
                               "effect": effect, "label": label, "confirmed_terms": terms,
                               "raw_label": event["evidence"]["raw_label"],
                               "ordinal": {"\u592f": 5, "\u9876\u7ea7": 4, "\u4eba\u4e0a\u4eba": 3,
                                           "NPC": 2, "\u62c9\u5b8c\u4e86": 1}.get(event["evidence"]["raw_label"].strip()),
                               "source_ref": event["evidence"]["source_ref"]})
        usage.setdefault(ref, {"used_by": []})["ranking_effect"] = effect

    lanes: list[dict[str, Any]] = []
    for lane, purpose in (*LANE_TEMPLATES, ("adjacent", "structural transfer across independent fields")):
        queries = [item for item in records if item["lane"] == lane]
        ecosystems = list(dict.fromkeys(eco for item in queries for eco in item["ecosystems"]))
        lanes.append({"lane": lane, "purpose": purpose, "ecosystems": ecosystems,
                      "ecosystem_hints": {eco: ECOSYSTEM_HINTS.get(eco, "authoritative source method evidence") for eco in ecosystems},
                      "query": queries[0]["query"] if queries else "",
                      "query_records": [dict(item, query_template=item["query"], ecosystem=ecosystem)
                                        for item in queries for ecosystem in item["ecosystems"]],
                      "required_bridge": lane in {"mechanism", "adjacent"},
                      "status": "planned" if queries else "needs_host_input"})
    expected_ecosystems = list(dict.fromkeys(eco for lane in lanes for eco in lane["ecosystems"]))
    max_sources = payload.get("max_sources", budget["max_sources"])
    if not isinstance(max_sources, int) or isinstance(max_sources, bool) or not 1 <= max_sources <= 20:
        raise ValueError("max_sources must be an integer from 1 to 20")
    availability_declared = bool(available_ecosystems)
    uncovered = [item for item in expected_ecosystems if availability_declared and item not in available_ecosystems]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "domain": domain,
        "question": question,
        "project_id": project_id,
        "project_frame": frame,
        "mechanism_bridges": bridges,
        "foundation_sources": foundations,
        "queries": records,
        "consumption": usage,
        "ranking_policy": ranking_policy,
        "ranking_boundary": "Host applies these bounded preferences after identity and project-fit gates, records candidate-level effects, and preserves exploration; this planner does not score user usefulness.",
        "host_actions": (["Provide a structural bridge hypothesis or explain why transfer is not applicable; do not count an empty adjacent lane as searched."] if not bridges else []) + (["Attach evidence_refs for the project frame; inferred fields remain hypotheses."] if not frame["evidence_refs"] else []) + (["After round one, pass the 3-5 strongest resolved method/standard/dataset anchors as foundation_sources and rerun; record each successor check as found, none_found or blocked."] if not foundations else []),
        "usefulness_policy": {
            "required_query_families": list(REUSE_FAMILIES),
            "per_round_minimums": per_round_minimums(budget["budget"]["query_records"], bool(bridges)),
            "successor_check": "Each foundation source gets one hop: recent citing work, current version or extension, maintained implementation. Record found/none_found/blocked; never infer absence from an unexecuted query.",
            "age_is_not_exclusion": True,
            "identity_conflict": "When a proof, preprint, mirror or index record disagrees with the formal record, resolve the DOI/registry or publisher record and cite it; report the conflict only if the formal record cannot be reached.",
            "date_fields": ["first_published", "version_or_edition", "observed_at", "attention_event"],
            "lineage_grouping": "Method paper, its maintained implementation and successor versions form one lineage entry with member links; near-duplicate papers of one lineage do not fill separate slots.",
            "top_investment": {"size": [3, 5], "required_fields": ["why_invest", "saves_work", "next_action"]},
        },
        "constraints": constraints,
        "available_ecosystems": available_ecosystems,
        "availability_status": "declared" if availability_declared else "not_declared",
        "known_leads": known_leads,
        "known_leads_runtime_role": "recovery_targets_only",
        "time_window": time_window,
        "source_classes": profile["source_classes"],
        "budget_profile": budget_profile,
        "candidate_pool": {**budget["candidate_pool"], "metadata_only": True},
        "shortlist": {"max_sources": max_sources, "single_ranked_list": True},
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
        "query_execution": "Queries are a prioritized backlog, not executed calls. Spread distinct lanes across per-round capacity, expand real relations after retrieval, and record actual executed IDs. Never claim coverage from a plan alone.",
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
    parser.add_argument("--output", required=True, help="JSON plan output path, or - for stdout")
    parser.add_argument("--profile", help="explicit same-project feedback profile; never auto-discovered")
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
    if args.profile:
        preference_profile = validate_profile(json.loads(Path(args.profile).expanduser().read_text(encoding="utf-8")))
        if not payload.get("project_id") or payload["project_id"] != preference_profile["project"].get("id"):
            raise ValueError("profile project id must match the explicitly supplied project_id")
        if "preference_events" in payload:
            raise ValueError("use either --profile or preference_events, not both")
        payload["preference_events"] = preference_profile["feedback"]
    plan = build_plan(payload)
    rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output == "-":
        sys.stdout.write(rendered)
    else:
        output_path.write_text(rendered, encoding="utf-8")
    print(json.dumps({
        "status": "plan_ready",
        "domain": plan["domain"],
        "budget_profile": plan["budget_profile"],
        "lanes": len(plan["lanes"]),
    }, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
