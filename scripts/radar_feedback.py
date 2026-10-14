#!/usr/bin/env python3
"""Maintain a visible Chinese feedback loop for Research Source Radar.

This tool stores only explicit user choices. It does not crawl social feeds,
infer private interests, call a model, or claim that a feedback label proves a
source is correct. The generated guidance is intended to be read by the next
Radar discovery run alongside the project brief.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import research_contract as contract


SCHEMA_VERSION = 1
MAX_TEXT = 2_000
MAX_ITEMS = 120
FEEDBACK_LABELS = {
    "worth_deepening": "值得深入看",
    "mechanism_to_borrow": "可借鉴机制",
    "reference_only": "相关但仅作参考",
    "not_useful_now": "暂时没用",
    "already_known": "已经知道",
    "avoid_similar": "不想再推荐这类",
    "uncertain": "不确定",
}
COLLOQUIAL_LABELS = {
    "夯": "worth_deepening",
    "夯爆": "worth_deepening",
    "顶级": "worth_deepening",
    "顶": "worth_deepening",
    "人上人": "mechanism_to_borrow",
    "能打": "mechanism_to_borrow",
    "有料": "mechanism_to_borrow",
    "NPC": "reference_only",
    "一般": "reference_only",
    "中规中矩": "reference_only",
    "看一眼": "reference_only",
    "拉完了": "not_useful_now",
    "拉": "not_useful_now",
    "很拉": "not_useful_now",
    "避雷": "avoid_similar",
}
COLLOQUIAL_PRIORITY = {
    "夯": 5,
    "夯爆": 5,
    "顶级": 4,
    "顶": 4,
    "人上人": 3,
    "NPC": 2,
    "一般": 2,
    "中规中矩": 2,
    "看一眼": 2,
    "拉完了": 1,
    "拉": 1,
    "很拉": 1,
}
POSITIVE_LABELS = {"worth_deepening", "mechanism_to_borrow"}
NEGATIVE_LABELS = {"avoid_similar"}
TIER_TITLES = {
    "priority_now": "优先看",
    "frontier_hot": "热门前沿",
    "cross_domain": "跨域启发",
    "watchlist": "持续关注",
}
REVIEW_HEADING = re.compile(r"^### (?P<candidate_id>[^\s]+) · (?P<title>.+)$")
REVIEW_FIELD = re.compile(r"^你的(?P<field>标注|理由|偏好范围|确认维度)[：:]\s*(?P<value>.*)$")
NON_AFFIRMATIVE = re.compile(r"不|没|未|无|非|拒绝|避免|排除|可能|待验证|\b(?:not|no|never|without|avoid|uncertain)\b", re.I)


def parse_review_blocks(text: str) -> dict[str, dict[str, str]]:
    blocks: dict[str, dict[str, str]] = {}
    current = None
    for line in text.splitlines():
        heading = REVIEW_HEADING.match(line.strip())
        if heading:
            candidate_id = heading.group("candidate_id")
            if candidate_id in blocks:
                raise ValueError(f"duplicate review candidate: {candidate_id}")
            current = blocks[candidate_id] = {"title": heading.group("title")}
            continue
        field = REVIEW_FIELD.match(line.strip())
        if field:
            if current is None:
                raise ValueError("review field has no candidate heading")
            key, value = field.group("field"), field.group("value")
            if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
                value = value[1:-1]
            if key in current:
                raise ValueError(f"duplicate review field: {key}")
            current[key] = value
        elif current is not None:
            for prefix, key in (("来源：", "url"), ("来源版本：", "version")):
                if line.startswith(prefix):
                    if key in current:
                        raise ValueError(f"duplicate review field: {key}")
                    current[key] = line[len(prefix):].strip()
    return blocks


def review_dimensions(fields: dict[str, str]) -> tuple[str, list[str]]:
    raw_scope = fields.get("偏好范围", "").strip()
    raw_terms = fields.get("确认维度", "").strip()
    scopes = {"": "candidate", "待填写": "candidate", "当前候选": "candidate",
              "candidate": "candidate", "维度": "dimension", "dimension": "dimension"}
    if raw_scope not in scopes:
        raise ValueError("偏好范围须明确填写 当前候选 或 维度")
    terms = [] if raw_terms in {"", "待填写"} else clean_string_list(
        re.split(r"[、,，;；]", raw_terms), "你的确认维度")
    scope = scopes[raw_scope]
    if (scope == "dimension") != bool(terms):
        raise ValueError("按维度反馈须同时填写 偏好范围：维度 和非空确认维度；只评候选请留空维度")
    return scope, terms


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = " ".join(value.split())
    if (not allow_empty and not value) or len(value) > MAX_TEXT:
        raise ValueError(f"{field} must be {'non-empty and ' if not allow_empty else ''}at most {MAX_TEXT} characters")
    return value


def clean_string_list(value: Any, field: str, *, maximum: int = 24) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{field} must be a list with at most {maximum} items")
    result = [clean_text(item, f"{field}[{index}]") for index, item in enumerate(value)]
    return list(dict.fromkeys(result))


def require_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{field} fields must be exactly {sorted(expected)}")
    return value


def make_profile(project_name: str, project_description: str, constraints: list[str], project_id: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "language": "zh-CN",
        "project": {
            "id": project_id or str(uuid.uuid4()),
            "name": clean_text(project_name, "project_name"),
            "description": clean_text(project_description, "project_description"),
            "constraints": list(dict.fromkeys(constraints)),
        },
        "feedback": [],
        "derived_guidance": {
            "approved_tags": [],
            "avoid_tags": [],
            "next_run_guidance": [
                "先保留热门、直接相关、跨领域三条发现路径；尚无人工反馈，不做个性化降权。",
                "至少保留一部分探索候选，避免只复现已有项目偏好。",
            ],
        },
        "updated_at": now_iso(),
    }


def validate_profile(value: Any) -> dict[str, Any]:
    profile = require_keys(
        value,
        {"schema_version", "language", "project", "feedback", "derived_guidance", "updated_at"},
        "profile",
    )
    if profile["schema_version"] != SCHEMA_VERSION or profile["language"] != "zh-CN":
        raise ValueError("profile schema_version or language is unsupported")
    project_fields = {"name", "description", "constraints"}
    if isinstance(profile["project"], dict) and "id" in profile["project"]:
        project_fields.add("id")
    project = require_keys(profile["project"], project_fields, "profile.project")
    if "id" in project:
        clean_text(project["id"], "profile.project.id")
    clean_text(project["name"], "profile.project.name")
    clean_text(project["description"], "profile.project.description")
    clean_string_list(project["constraints"], "profile.project.constraints", maximum=40)
    if not isinstance(profile["feedback"], list) or len(profile["feedback"]) > MAX_ITEMS:
        raise ValueError("profile.feedback must be a bounded list")
    seen_ids: set[str] = set()
    for index, item in enumerate(profile["feedback"]):
        feedback = require_keys(
            item,
            {"feedback_id", "candidate_id", "title", "label", "reason", "tags", "created_at"} | ({"evidence"} if isinstance(item, dict) and "evidence" in item else set()),
            f"profile.feedback[{index}]",
        )
        feedback_id = clean_text(feedback["feedback_id"], f"profile.feedback[{index}].feedback_id")
        if feedback_id in seen_ids:
            raise ValueError("profile.feedback contains duplicate feedback_id")
        seen_ids.add(feedback_id)
        clean_text(feedback["candidate_id"], f"profile.feedback[{index}].candidate_id")
        clean_text(feedback["title"], f"profile.feedback[{index}].title")
        if feedback["label"] not in FEEDBACK_LABELS:
            raise ValueError(f"profile.feedback[{index}].label is unsupported")
        clean_text(feedback["reason"], f"profile.feedback[{index}].reason", allow_empty=True)
        clean_string_list(feedback["tags"], f"profile.feedback[{index}].tags")
        clean_text(feedback["created_at"], f"profile.feedback[{index}].created_at")
    guidance = require_keys(
        profile["derived_guidance"],
        {"approved_tags", "avoid_tags", "next_run_guidance"},
        "profile.derived_guidance",
    )
    clean_string_list(guidance["approved_tags"], "profile.derived_guidance.approved_tags", maximum=60)
    clean_string_list(guidance["avoid_tags"], "profile.derived_guidance.avoid_tags", maximum=60)
    clean_string_list(guidance["next_run_guidance"], "profile.derived_guidance.next_run_guidance", maximum=20)
    clean_text(profile["updated_at"], "profile.updated_at")
    return profile


def validate_feedback_batch(value: Any) -> list[dict[str, Any]]:
    batch = require_keys(value, {"schema_version", "feedback"}, "feedback_batch")
    if batch["schema_version"] != SCHEMA_VERSION:
        raise ValueError("feedback_batch schema_version is unsupported")
    feedback_items = batch["feedback"]
    if not isinstance(feedback_items, list) or not feedback_items or len(feedback_items) > MAX_ITEMS:
        raise ValueError("feedback_batch.feedback must be a non-empty bounded list")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(feedback_items):
        feedback = require_keys(
            item,
            {"candidate_id", "title", "label", "reason", "tags"} | ({"evidence"} if isinstance(item, dict) and "evidence" in item else set()),
            f"feedback_batch.feedback[{index}]",
        )
        candidate_id = clean_text(feedback["candidate_id"], f"feedback_batch.feedback[{index}].candidate_id")
        if candidate_id in seen:
            raise ValueError("feedback_batch contains duplicate candidate_id")
        seen.add(candidate_id)
        label = feedback["label"]
        if label not in FEEDBACK_LABELS:
            raise ValueError(f"feedback_batch.feedback[{index}].label is unsupported")
        parsed.append({
            "candidate_id": candidate_id,
            "title": clean_text(feedback["title"], f"feedback_batch.feedback[{index}].title"),
            "label": label,
            "reason": clean_text(feedback["reason"], f"feedback_batch.feedback[{index}].reason", allow_empty=True),
            "tags": clean_string_list(feedback["tags"], f"feedback_batch.feedback[{index}].tags"),
            **({"evidence": feedback["evidence"]} if "evidence" in feedback else {}),
        })
    return parsed


def feedback_issue(item: Any, project_id: str, *, source_cache: dict[str, str] | None = None) -> str | None:
    """Return a quarantine reason unless a user judgment has original evidence.

    References are local, user-authorized review snapshots, not source URLs or
    model relevance scores. A changed/deleted snapshot invalidates consumption.
    """
    if not isinstance(item, dict) or not isinstance(item.get("evidence"), dict):
        return "legacy_or_missing_user_evidence"
    evidence = item["evidence"]
    if not project_id or evidence.get("project_id") != project_id:
        return "project_mismatch"
    if evidence.get("status") != "confirmed" or evidence.get("confidence") != "user_explicit":
        return "unconfirmed_user_evidence"
    if evidence.get("candidate_id") != item.get("candidate_id") or evidence.get("candidate_title") != item.get("title"):
        return "candidate_identity_mismatch"
    identity = evidence.get("source_identity")
    if not isinstance(identity, dict) or not all(isinstance(identity.get(key), str) and identity[key].strip() for key in ("url", "version")):
        return "missing_source_identity_or_version"
    if identity["version"].casefold() in {"unverified", "unknown", "latest", "head", "main", "master"}:
        return "unpinned_source_version"
    try:
        datetime.fromisoformat(evidence["verified_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, TypeError, ValueError):
        return "missing_or_invalid_verification_time"
    raw_label, raw_reason = evidence.get("raw_label"), evidence.get("raw_reason")
    if not isinstance(raw_label, str) or not isinstance(raw_reason, str):
        return "missing_raw_user_judgment"
    try:
        if normalize_review_label(raw_label, raw_reason) != item.get("label"):
            return "label_mapping_mismatch"
    except ValueError:
        return "unresolved_label"
    terms = evidence.get("confirmed_terms")
    if not isinstance(terms, list) or len(terms) > 24 or any(not isinstance(term, str) or not term.strip() or term not in raw_reason for term in terms):
        return "preference_terms_not_grounded_in_user_reason"
    if terms and evidence.get("scope") != "dimension":
        return "dimension_scope_not_confirmed"
    if evidence.get("scope") not in {"candidate", "dimension"}:
        return "invalid_feedback_scope"
    if clean_text(raw_reason, "raw_reason", allow_empty=True) != item.get("reason"):
        return "reason_mapping_mismatch"
    ref = evidence.get("source_ref")
    if not isinstance(ref, dict) or not all(isinstance(ref.get(key), str) and ref[key] for key in ("path", "sha256")):
        return "missing_original_input_reference"
    cache = source_cache if source_cache is not None else {}
    try:
        if ref["path"] not in cache:
            cache[ref["path"]] = Path(ref["path"]).expanduser().read_text(encoding="utf-8")
        original = cache[ref["path"]]
    except (OSError, UnicodeError):
        return "original_input_unavailable"
    if hashlib.sha256(original.encode("utf-8")).hexdigest() != ref["sha256"]:
        return "original_input_changed"
    try:
        original_item = parse_review_blocks(original).get(item["candidate_id"])
    except ValueError:
        return "duplicate_or_invalid_original_review"
    if original_item is None:
        return "candidate_missing_or_duplicated_in_original"
    if original_item.get("title") != item["title"] or original_item.get("标注", "") != raw_label or original_item.get("理由", "") != raw_reason:
        return "original_judgment_mismatch"
    if original_item.get("url") != identity["url"]:
        return "original_source_url_mismatch"
    if original_item.get("version") != identity["version"]:
        return "original_source_version_missing_or_mismatched"
    try:
        original_scope, original_terms = review_dimensions(original_item)
    except ValueError:
        return "invalid_original_dimension_confirmation"
    if evidence["scope"] != original_scope or terms != original_terms:
        return "original_dimension_confirmation_mismatch"
    if original_scope == "dimension":
        confirmation = evidence.get("dimension_confirmation")
        if not isinstance(confirmation, dict) or confirmation != {
            "raw_scope": original_item["偏好范围"], "raw_terms": original_item["确认维度"],
        }:
            return "missing_or_mismatched_dimension_confirmation"
        if item["label"] in POSITIVE_LABELS:
            clauses = re.split(r"[，,。；;！？!?\n]", raw_reason)
            for term in terms:
                if not any(term in clause and not NON_AFFIRMATIVE.search(clause) for clause in clauses):
                    return f"positive_term_negated_or_uncertain: {term}；请在新评审快照中明确肯定的维度"
    return None


def derive_guidance(feedback: list[dict[str, Any]], project_id: str = "") -> dict[str, list[str]]:
    cache: dict[str, str] = {}
    original_count = len(feedback)
    feedback = [item for item in feedback if feedback_issue(item, project_id, source_cache=cache) is None]
    approved = Counter(
        tag for item in feedback if item["label"] in POSITIVE_LABELS for tag in item["evidence"]["confirmed_terms"]
    )
    avoid = Counter(
        tag for item in feedback if item["label"] in NEGATIVE_LABELS for tag in item["evidence"]["confirmed_terms"]
    )
    approved_tags = [tag for tag, _ in approved.most_common(12)]
    avoid_tags = [tag for tag, _ in avoid.most_common(12)]
    guidance = [
        f"原始证据门禁：{len(feedback)} 条可用，{original_count - len(feedback)} 条隔离；旧缓存提示不作为偏好来源。",
        "优先覆盖问题直连、热门前沿、跨领域机制和关联扩散四条路径；不要仅按关键词相似排序。",
        "将用户已知项目保留为锚点，但不把它们计入新发现。",
        "保留至少 20% 的探索候选；负面反馈只降低排序，不自动屏蔽尚未核验的新机制。",
        "将相关性、机制参考和深挖优先级分开；不要把所有正向或相关标注平均成同一优先级。",
    ]
    ordered_feedback = sorted(feedback, key=attention_priority, reverse=True)
    deep_ids = [item["candidate_id"] for item in ordered_feedback if attention_level(item) == "deep_priority"]
    mechanism_ids = [item["candidate_id"] for item in ordered_feedback if attention_level(item) == "mechanism_reference"]
    light_ids = [item["candidate_id"] for item in ordered_feedback if attention_level(item) == "light_reference"]
    if deep_ids:
        guidance.append("明确强信号的优先深挖候选：" + "、".join(deep_ids) + "。")
    if mechanism_ids:
        guidance.append("可用于机制查询扩展、但不自动进入深挖队列的候选：" + "、".join(mechanism_ids) + "。")
    if light_ids:
        guidance.append("相关但不建议平均深入的候选：" + "、".join(light_ids) + "。")
    if approved_tags:
        guidance.append("优先寻找与已确认价值相近的机制或特征：" + "、".join(approved_tags) + "。")
    if avoid_tags:
        guidance.append("降低以下已明确不想重复推荐的特征：" + "、".join(avoid_tags) + "。")
    return {
        "approved_tags": approved_tags,
        "avoid_tags": avoid_tags,
        "next_run_guidance": guidance,
    }


def feedback_id(index: int, item: dict[str, Any]) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", item["candidate_id"]).strip("-") or "candidate"
    return f"FB-{index:03d}-{slug[:40]}"


def merge_feedback(profile: dict[str, Any], incoming: list[dict[str, Any]]) -> dict[str, Any]:
    updated = json.loads(json.dumps(validate_profile(profile), ensure_ascii=False))
    entries = updated["feedback"]
    existing_candidate_ids = {item["candidate_id"] for item in entries}
    project_id = updated["project"].get("id", "")
    source_cache: dict[str, str] = {}
    issues = []
    for item in incoming:
        issue = feedback_issue(item, project_id, source_cache=source_cache)
        if issue:
            issues.append(f"{item.get('candidate_id')}: {issue}")
        if item["candidate_id"] in existing_candidate_ids:
            issues.append(f"candidate already has feedback: {item['candidate_id']}")
        existing_candidate_ids.add(item["candidate_id"])
    if issues:
        raise ValueError("feedback quarantined；整批未写入：" + "; ".join(issues)
                         + "。请补齐问题候选，或将完整候选复制到新的评审快照后重新 extract-review；不要复用旧 proposal。")
    for item in incoming:
        entry = dict(item)
        entry["feedback_id"] = feedback_id(len(entries) + 1, item)
        entry["created_at"] = now_iso()
        entries.append(entry)
    updated["derived_guidance"] = derive_guidance(entries, project_id)
    updated["updated_at"] = now_iso()
    return validate_profile(updated)


def validate_candidates(value: Any) -> list[dict[str, Any]]:
    document = require_keys(value, {"schema_version", "candidates"}, "candidates_document")
    if document["schema_version"] != SCHEMA_VERSION:
        raise ValueError("candidates_document schema_version is unsupported")
    candidates = document["candidates"]
    if not isinstance(candidates, list) or not candidates or len(candidates) > MAX_ITEMS:
        raise ValueError("candidates_document.candidates must be a non-empty bounded list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    expected = {"candidate_id", "title", "url", "tier", "summary", "why_now", "mechanism_tags", "trend_note"}
    for index, item in enumerate(candidates):
        optional = {"source_version", "verified_at", "time_note"}
        candidate = require_keys(item, expected | (set(item) & optional if isinstance(item, dict) else set()), f"candidates_document.candidates[{index}]")
        candidate_id = clean_text(candidate["candidate_id"], f"candidates_document.candidates[{index}].candidate_id")
        if candidate_id in seen:
            raise ValueError("candidates_document contains duplicate candidate_id")
        seen.add(candidate_id)
        if candidate["tier"] not in TIER_TITLES:
            raise ValueError(f"candidates_document.candidates[{index}].tier is unsupported")
        cleaned = {
            "candidate_id": candidate_id,
            "title": clean_text(candidate["title"], f"candidates_document.candidates[{index}].title"),
            "url": clean_text(candidate["url"], f"candidates_document.candidates[{index}].url"),
            "tier": candidate["tier"],
            "summary": clean_text(candidate["summary"], f"candidates_document.candidates[{index}].summary"),
            "why_now": clean_text(candidate["why_now"], f"candidates_document.candidates[{index}].why_now"),
            "mechanism_tags": clean_string_list(candidate["mechanism_tags"], f"candidates_document.candidates[{index}].mechanism_tags"),
            "trend_note": clean_text(candidate["trend_note"], f"candidates_document.candidates[{index}].trend_note", allow_empty=True),
            "source_version": clean_text(candidate.get("source_version", "unverified"), "candidate.source_version"),
            "verified_at": clean_text(candidate.get("verified_at", ""), "candidate.verified_at", allow_empty=True),
            "time_note": clean_text(candidate.get("time_note", "具体发布时间尚未核实；不据此声称近期或热门。"), "candidate.time_note"),
        }
        result.append(cleaned)
    return result


def normalize_review_label(raw_label: str, raw_reason: str) -> str:
    """Map a clearly stated Chinese phrase to a bounded feedback label.

    Mixed language is deliberately treated as ``uncertain``. The caller writes
    an inspectable proposal before any feedback reaches a profile.
    """
    label = clean_text(raw_label, "review label", allow_empty=True)
    reason = clean_text(raw_reason, "review reason", allow_empty=True)
    # Exact explicit labels win. Never infer a positive label from a word in
    # the reason (e.g. "not top-tier"), or silently promote qualified language.
    if label in FEEDBACK_LABELS:
        return label
    if label in FEEDBACK_LABELS.values():
        return next(code for code, title in FEEDBACK_LABELS.items() if title == label)
    if label in COLLOQUIAL_LABELS:
        return COLLOQUIAL_LABELS[label]
    aliases = {"多推荐": "worth_deepening", "好好看看": "worth_deepening",
               "值得做迁移": "worth_deepening", "可以借鉴": "mechanism_to_borrow",
               "可以借鉴机制": "mechanism_to_borrow", "感觉很一般": "reference_only",
               "机制参考": "mechanism_to_borrow", "当前不需要": "not_useful_now"}
    if label in {"可以借鉴", "可以借鉴机制"} and re.search(r"一般|不确定|可能|不知道|需要.*验证", reason):
        return "uncertain"
    return aliases.get(label, "uncertain")


def attention_level(item: dict[str, Any]) -> str:
    """Classify effort level without changing the user's raw feedback."""
    if item["label"] == "worth_deepening":
        return "deep_priority"
    if item["label"] == "mechanism_to_borrow":
        return "mechanism_reference"
    if item["label"] == "reference_only":
        return "light_reference"
    return "unresolved"


def attention_priority(item: dict[str, Any]) -> int:
    """Return the explicit colloquial order when one was provided."""
    raw_label = item.get("evidence", {}).get("raw_label", "")
    if raw_label in COLLOQUIAL_PRIORITY:
        return COLLOQUIAL_PRIORITY[raw_label]
    if item["label"] == "worth_deepening":
        return 4
    if item["label"] == "mechanism_to_borrow":
        return 3
    if item["label"] == "reference_only":
        return 2
    return 0


def extract_review_feedback(review_text: str, candidates: list[dict[str, Any]], *, project_id: str = "", source_ref: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Create an inspectable feedback proposal from a completed Chinese review."""
    candidate_map = {candidate["candidate_id"]: candidate for candidate in candidates}
    parsed = parse_review_blocks(review_text)
    for candidate_id, fields in parsed.items():
        if candidate_id not in candidate_map:
            raise ValueError(f"review contains unknown candidate: {candidate_id}")
        if fields["title"] != candidate_map[candidate_id]["title"]:
            raise ValueError(f"review title does not match candidate: {candidate_id}")

    proposal: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        fields = parsed.get(candidate_id, {})
        raw_label = fields.get("标注", "")
        raw_reason = fields.get("理由", "")
        if not raw_label.strip() or raw_label.strip() == "待填写":
            if any(fields.get(key, "").strip() not in {"", "待填写", "当前候选", "candidate"}
                   for key in ("理由", "偏好范围", "确认维度")):
                raise ValueError(f"{candidate_id}: 有理由或维度确认但缺少标注；整批未写入，请补标注或拆分为新评审快照")
            continue
        try:
            scope, terms = review_dimensions(fields)
        except ValueError as exc:
            raise ValueError(f"{candidate_id}: {exc}") from exc
        proposal.append({
            "candidate_id": candidate_id,
            "title": candidate["title"],
            "label": normalize_review_label(raw_label, raw_reason),
            "reason": raw_reason,
            "tags": candidate["mechanism_tags"],
            "evidence": {
                "project_id": project_id,
                "candidate_id": candidate_id,
                "candidate_title": candidate["title"],
                "source_ref": source_ref or {},
                "source_identity": {"url": candidate["url"], "version": candidate.get("source_version", "unverified")},
                "raw_label": raw_label,
                "raw_reason": raw_reason,
                "ordinal": COLLOQUIAL_PRIORITY.get(raw_label.strip()),
                "verified_at": candidate.get("verified_at", ""),
                "confidence": "user_explicit",
                "status": "unverified",
                "scope": scope,
                "confirmed_terms": terms,
                **({"dimension_confirmation": {"raw_scope": fields["偏好范围"],
                                               "raw_terms": fields["确认维度"]}} if scope == "dimension" else {}),
            },
        })
    return validate_feedback_batch({"schema_version": SCHEMA_VERSION, "feedback": proposal})


def render_review(profile: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    project = profile["project"]
    lines = [
        f"# {project['name']}：研究机会评审卡",
        "",
        "这份卡片用于记录你的明确判断，不代表候选已经被验证有效。请为每个候选选择一个标签：",
        "正式标签：`值得深入看`、`可借鉴机制`、`相关但仅作参考`、`暂时没用`、`已经知道`、`不想再推荐这类` 或 `不确定`。",
        "也可以用有顺序的口语标签：`夯 > 顶级 > 人上人 > NPC > 拉完了`。其中 `夯/顶级`≈优先深挖，`人上人`≈可借鉴机制，`NPC`≈相关但仅作参考，`拉完了`≈暂时没用；`避雷`仍表示不想再推荐这类。系统仍会保留你的原话。",
        "也可以写自然中文；导入时会先生成可检查提案。混合或保留语气会保守归为“不确定”，不会擅自当作正向偏好。",
        "反引号可省略。只有你明确填写 偏好范围：维度 和 确认维度（用顿号分隔，须出现在原始理由中），才按维度使用；不得由模型代填。",
        "",
        "你的理由和标签将只用于生成下一轮可见的中文检索提示；不会读取社交平台历史，也不会训练外部模型。",
        "",
    ]
    for tier in TIER_TITLES:
        items = [item for item in candidates if item["tier"] == tier]
        if not items:
            continue
        lines.extend([f"## {TIER_TITLES[tier]}", ""])
        for item in items:
            lines.extend([
                f"### {item['candidate_id']} · {item['title']}",
                f"来源：{item['url']}",
                f"来源版本：{item.get('source_version', 'unverified')}",
                f"是什么：{item['summary']}",
                f"为什么现在看：{item['why_now']}",
                f"具体时间与依据：{item.get('time_note', '尚未核实，不作近期或热门判断。')}",
                f"机制标签：{'、'.join(item['mechanism_tags'])}",
                f"热度/时效说明：{item['trend_note'] or '未把热度作为主要推荐理由。'}",
                "你的标注：`待填写`",
                "你的理由：`待填写`",
                "你的偏好范围：`待填写`",
                "你的确认维度：`待填写`",
                "",
            ])
    return "\n".join(lines) + "\n"


def command_init(args: argparse.Namespace) -> int:
    profile = make_profile(args.project_name, args.description, args.constraint or [], args.project_id)
    contract.write_json_atomic(Path(args.output).expanduser(), profile)
    print(f"RADAR_PROFILE_READY output={Path(args.output).expanduser()}")
    return 0


def command_render_review(args: argparse.Namespace) -> int:
    profile = validate_profile(contract.load_json(Path(args.profile).expanduser()))
    candidates = validate_candidates(contract.load_json(Path(args.candidates).expanduser()))
    contract.write_text_atomic(Path(args.output).expanduser(), render_review(profile, candidates), default_mode=0o600)
    print(f"RADAR_REVIEW_READY candidates={len(candidates)} output={Path(args.output).expanduser()}")
    return 0


def command_record(args: argparse.Namespace) -> int:
    if not getattr(args, "confirm", False):
        raise ValueError("record-feedback requires --confirm after explicit user confirmation；不能自动导入旧 proposal")
    profile_path = Path(args.profile).expanduser()
    profile = validate_profile(contract.load_json(profile_path))
    incoming = validate_feedback_batch(contract.load_json(Path(args.feedback).expanduser()))
    if args.confirm:
        for item in incoming:
            if isinstance(item.get("evidence"), dict):
                item["evidence"]["status"] = "confirmed"
    updated = merge_feedback(profile, incoming)
    output = Path(args.output).expanduser() if args.output else profile_path
    contract.write_json_atomic(output, updated)
    print(f"RADAR_FEEDBACK_RECORDED added={len(incoming)} total={len(updated['feedback'])} output={output}")
    return 0


def command_replace_feedback(args: argparse.Namespace) -> int:
    """Replace a feedback batch only while preserving an explicit local archive."""
    if not getattr(args, "confirm", False):
        raise ValueError("replace-feedback requires --confirm after explicit user confirmation")
    profile_path = Path(args.profile).expanduser()
    archive_path = Path(args.archive).expanduser()
    if profile_path.resolve() == archive_path.resolve():
        raise ValueError("archive path must differ from profile path")
    profile = validate_profile(contract.load_json(profile_path))
    incoming = validate_feedback_batch(contract.load_json(Path(args.feedback).expanduser()))
    if args.confirm:
        for item in incoming:
            if isinstance(item.get("evidence"), dict):
                item["evidence"]["status"] = "confirmed"
    if archive_path.exists():
        raise ValueError("archive path already exists; choose a new immutable archive path")
    reset = make_profile(
        profile["project"]["name"],
        profile["project"]["description"],
        profile["project"]["constraints"],
        profile["project"].get("id"),
    )
    updated = merge_feedback(reset, incoming)
    contract.write_json_atomic(archive_path, profile)
    contract.write_json_atomic(profile_path, updated)
    print(f"RADAR_FEEDBACK_REPLACED added={len(incoming)} archive={archive_path} output={profile_path}")
    return 0


def command_refresh_guidance(args: argparse.Namespace) -> int:
    """Recompute derived guidance without changing the user's raw feedback."""
    profile_path = Path(args.profile).expanduser()
    profile = validate_profile(contract.load_json(profile_path))
    updated = json.loads(json.dumps(profile, ensure_ascii=False))
    updated["derived_guidance"] = derive_guidance(updated["feedback"], updated["project"].get("id", ""))
    updated["updated_at"] = now_iso()
    contract.write_json_atomic(profile_path, validate_profile(updated))
    print(f"RADAR_GUIDANCE_REFRESHED total={len(updated['feedback'])} output={profile_path}")
    return 0


def command_extract_review(args: argparse.Namespace) -> int:
    candidates = validate_candidates(contract.load_json(Path(args.candidates).expanduser()))
    review_path = Path(args.review).expanduser()
    review_text = review_path.read_text(encoding="utf-8")
    feedback = extract_review_feedback(review_text, candidates, project_id=args.project_id, source_ref={
        "path": str(review_path.resolve()),
        "sha256": hashlib.sha256(review_text.encode("utf-8")).hexdigest(),
    })
    proposal = {
        "schema_version": SCHEMA_VERSION,
        "feedback": feedback,
    }
    output = Path(args.output).expanduser()
    contract.write_json_atomic(output, proposal)
    lines = ["# 用户反馈核对草案", "", "仅是草案；未写入项目画像。缺少版本或证据时不能确认启用。", ""]
    for item in feedback:
        lines.extend([f"## {item['candidate_id']} · {item['title']}",
                      f"原始标注：{item['evidence']['raw_label']}", f"原始理由：{item['evidence']['raw_reason']}",
                      f"拟记录：{FEEDBACK_LABELS[item['label']]}；范围：{item['evidence']['scope']}；状态：待确认。",
                      f"用户确认维度：{'、'.join(item['evidence']['confirmed_terms']) or '无；仅保留候选反馈'}",
                      f"证据：{review_path.resolve()}；SHA256：{item['evidence']['source_ref']['sha256']}", ""])
    contract.write_text_atomic(output.with_suffix(".review.zh-CN.md"), "\n".join(lines) + "\n", default_mode=0o600)
    print(f"RADAR_FEEDBACK_PROPOSAL_READY candidates={len(feedback)} output={output}")
    return 0


def command_show_guidance(args: argparse.Namespace) -> int:
    profile = validate_profile(contract.load_json(Path(args.profile).expanduser()))
    guidance = derive_guidance(profile["feedback"], profile["project"].get("id", ""))
    print("# 下一轮 Radar 中文提示")
    print(f"项目：{profile['project']['name']}")
    print("已确认偏好：" + ("、".join(guidance["approved_tags"]) or "尚无"))
    print("需降权特征：" + ("、".join(guidance["avoid_tags"]) or "尚无"))
    for item in guidance["next_run_guidance"]:
        print(f"- {item}")
    return 0


def main() -> int:
    # Pipes on Windows can default to a code page that cannot represent Chinese.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create a visible Chinese project feedback profile")
    init.add_argument("--output", required=True)
    init.add_argument("--project-name", required=True)
    init.add_argument("--project-id", help="explicit local project identity; generated if omitted")
    init.add_argument("--description", required=True)
    init.add_argument("--constraint", action="append")
    init.set_defaults(handler=command_init)
    render = commands.add_parser("render-review", help="render Chinese candidate cards for human review")
    render.add_argument("--profile", required=True)
    render.add_argument("--candidates", required=True)
    render.add_argument("--output", required=True)
    render.set_defaults(handler=command_render_review)
    record = commands.add_parser("record-feedback", help="append explicit user feedback and refresh guidance")
    record.add_argument("--profile", required=True)
    record.add_argument("--feedback", required=True)
    record.add_argument("--output")
    record.add_argument("--confirm", action="store_true", help="use only after explicit user confirmation of this proposal")
    record.set_defaults(handler=command_record)
    replace = commands.add_parser("replace-feedback", help="replace a misparsed batch while keeping an immutable local archive")
    replace.add_argument("--profile", required=True)
    replace.add_argument("--feedback", required=True)
    replace.add_argument("--archive", required=True)
    replace.add_argument("--confirm", action="store_true", help="use only after explicit user confirmation")
    replace.set_defaults(handler=command_replace_feedback)
    refresh = commands.add_parser("refresh-guidance", help="recompute guidance from raw feedback without changing it")
    refresh.add_argument("--profile", required=True)
    refresh.set_defaults(handler=command_refresh_guidance)
    extract = commands.add_parser("extract-review", help="turn a completed Chinese review into an inspectable feedback proposal")
    extract.add_argument("--review", required=True)
    extract.add_argument("--candidates", required=True)
    extract.add_argument("--output", required=True)
    extract.add_argument("--project-id", required=True)
    extract.set_defaults(handler=command_extract_review)
    show = commands.add_parser("show-guidance", help="print the next-run Chinese guidance")
    show.add_argument("--profile", required=True)
    show.set_defaults(handler=command_show_guidance)
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {contract.display_safe_text(exc, preserve_newlines=True)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
