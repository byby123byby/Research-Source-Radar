#!/usr/bin/env python3
"""Maintain a visible Chinese feedback loop for Research Source Radar.

This tool stores only explicit user choices. It does not crawl social feeds,
infer private interests, call a model, or claim that a feedback label proves a
source is correct. The generated guidance is intended to be read by the next
Radar discovery run alongside the project brief.
"""

from __future__ import annotations

import argparse
import json
import re
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
REVIEW_FIELD = re.compile(r"^你的(?P<field>标注|理由)：`(?P<value>.*)`$")


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


def make_profile(project_name: str, project_description: str, constraints: list[str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "language": "zh-CN",
        "project": {
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
    project = require_keys(profile["project"], {"name", "description", "constraints"}, "profile.project")
    clean_text(project["name"], "profile.project.name")
    clean_text(project["description"], "profile.project.description")
    clean_string_list(project["constraints"], "profile.project.constraints", maximum=40)
    if not isinstance(profile["feedback"], list) or len(profile["feedback"]) > MAX_ITEMS:
        raise ValueError("profile.feedback must be a bounded list")
    seen_ids: set[str] = set()
    for index, item in enumerate(profile["feedback"]):
        feedback = require_keys(
            item,
            {"feedback_id", "candidate_id", "title", "label", "reason", "tags", "created_at"},
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
            {"candidate_id", "title", "label", "reason", "tags"},
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
        })
    return parsed


def derive_guidance(feedback: list[dict[str, Any]]) -> dict[str, list[str]]:
    approved = Counter(
        tag for item in feedback if item["label"] in POSITIVE_LABELS for tag in item["tags"]
    )
    avoid = Counter(
        tag for item in feedback if item["label"] in NEGATIVE_LABELS for tag in item["tags"]
    )
    approved_tags = [tag for tag, _ in approved.most_common(12)]
    avoid_tags = [tag for tag, _ in avoid.most_common(12)]
    guidance = [
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
    for item in incoming:
        if item["candidate_id"] in existing_candidate_ids:
            raise ValueError(f"candidate already has feedback: {item['candidate_id']}")
        entry = dict(item)
        entry["feedback_id"] = feedback_id(len(entries) + 1, item)
        entry["created_at"] = now_iso()
        entries.append(entry)
        existing_candidate_ids.add(item["candidate_id"])
    updated["derived_guidance"] = derive_guidance(entries)
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
        candidate = require_keys(item, expected, f"candidates_document.candidates[{index}]")
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
    combined = f"{label} {reason}".strip()
    if label in FEEDBACK_LABELS.values():
        return next(code for code, title in FEEDBACK_LABELS.items() if title == label)
    for colloquial, normalized in COLLOQUIAL_LABELS.items():
        if colloquial in label:
            return normalized
    if any(token in combined for token in ("已经知道", "我知道", "已知")):
        return "already_known"
    if any(token in combined for token in ("不想再推荐", "不要再推荐", "别再推荐", "避免这类", "不看")):
        return "avoid_similar"
    weak_tokens = ("一般般", "可以看看", "值得看看", "不是很重要", "不用重点", "可不看", "不重点", "可能可以", "感觉没用")
    if any(token in combined for token in weak_tokens):
        return "reference_only"
    if any(token in combined for token in ("值得深入", "重点看", "非常想", "很想深入", "夯", "多推荐", "好好看看", "值得做迁移", "多读")):
        return "worth_deepening"
    if any(token in combined for token in ("暂时没用", "没有那么想要", "当前不需要")):
        return "not_useful_now"
    if any(token in combined for token in ("不确定", "不知道")):
        return "uncertain"
    if any(token in combined for token in ("可借鉴机制", "可以借鉴", "可迁移", "迁移机制", "机制参考")):
        return "mechanism_to_borrow"
    if any(token in combined for token in ("值得看", "可以看", "参考", "相关")):
        return "reference_only"
    raise ValueError("could not map a Chinese review label; use one of: " + "、".join(FEEDBACK_LABELS.values()))


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
    text = item["reason"]
    for label, priority in sorted(COLLOQUIAL_PRIORITY.items(), key=lambda pair: len(pair[0]), reverse=True):
        if label in text:
            return priority
    if item["label"] == "worth_deepening":
        return 4
    if item["label"] == "mechanism_to_borrow":
        return 3
    if item["label"] == "reference_only":
        return 2
    return 0


def extract_review_feedback(review_text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create an inspectable feedback proposal from a completed Chinese review."""
    candidate_map = {candidate["candidate_id"]: candidate for candidate in candidates}
    parsed: dict[str, dict[str, str]] = {}
    current_id: str | None = None
    for line in review_text.splitlines():
        heading = REVIEW_HEADING.match(line)
        if heading:
            candidate_id = heading.group("candidate_id")
            if candidate_id not in candidate_map:
                raise ValueError(f"review contains unknown candidate: {candidate_id}")
            if candidate_id in parsed:
                raise ValueError(f"review contains duplicate candidate: {candidate_id}")
            if heading.group("title") != candidate_map[candidate_id]["title"]:
                raise ValueError(f"review title does not match candidate: {candidate_id}")
            parsed[candidate_id] = {}
            current_id = candidate_id
            continue
        field = REVIEW_FIELD.match(line)
        if field and current_id:
            parsed[current_id][field.group("field")] = field.group("value")

    proposal: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        fields = parsed.get(candidate_id, {})
        raw_label = fields.get("标注", "").strip()
        raw_reason = fields.get("理由", "").strip()
        if (not raw_label or raw_label == "待填写") and not raw_reason:
            raise ValueError(f"review has no completed label for {candidate_id}")
        if not raw_reason or raw_reason == "待填写":
            raw_reason = "用户未填写理由；仅保留原始标注，注意力优先级待确认。"
        proposal.append({
            "candidate_id": candidate_id,
            "title": candidate["title"],
            "label": normalize_review_label(raw_label, raw_reason),
            "reason": f"原始标注：{raw_label}。用户理由：{raw_reason}",
            "tags": candidate["mechanism_tags"],
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
                f"是什么：{item['summary']}",
                f"为什么现在看：{item['why_now']}",
                f"机制标签：{'、'.join(item['mechanism_tags'])}",
                f"热度/时效说明：{item['trend_note'] or '未把热度作为主要推荐理由。'}",
                "你的标注：`待填写`",
                "你的理由：`待填写`",
                "",
            ])
    return "\n".join(lines) + "\n"


def command_init(args: argparse.Namespace) -> int:
    profile = make_profile(args.project_name, args.description, args.constraint or [])
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
    profile_path = Path(args.profile).expanduser()
    profile = validate_profile(contract.load_json(profile_path))
    incoming = validate_feedback_batch(contract.load_json(Path(args.feedback).expanduser()))
    updated = merge_feedback(profile, incoming)
    output = Path(args.output).expanduser() if args.output else profile_path
    contract.write_json_atomic(output, updated)
    print(f"RADAR_FEEDBACK_RECORDED added={len(incoming)} total={len(updated['feedback'])} output={output}")
    return 0


def command_replace_feedback(args: argparse.Namespace) -> int:
    """Replace a feedback batch only while preserving an explicit local archive."""
    profile_path = Path(args.profile).expanduser()
    archive_path = Path(args.archive).expanduser()
    if profile_path.resolve() == archive_path.resolve():
        raise ValueError("archive path must differ from profile path")
    profile = validate_profile(contract.load_json(profile_path))
    incoming = validate_feedback_batch(contract.load_json(Path(args.feedback).expanduser()))
    if archive_path.exists():
        raise ValueError("archive path already exists; choose a new immutable archive path")
    contract.write_json_atomic(archive_path, profile)
    reset = make_profile(
        profile["project"]["name"],
        profile["project"]["description"],
        profile["project"]["constraints"],
    )
    updated = merge_feedback(reset, incoming)
    contract.write_json_atomic(profile_path, updated)
    print(f"RADAR_FEEDBACK_REPLACED added={len(incoming)} archive={archive_path} output={profile_path}")
    return 0


def command_refresh_guidance(args: argparse.Namespace) -> int:
    """Recompute derived guidance without changing the user's raw feedback."""
    profile_path = Path(args.profile).expanduser()
    profile = validate_profile(contract.load_json(profile_path))
    updated = json.loads(json.dumps(profile, ensure_ascii=False))
    updated["derived_guidance"] = derive_guidance(updated["feedback"])
    updated["updated_at"] = now_iso()
    contract.write_json_atomic(profile_path, validate_profile(updated))
    print(f"RADAR_GUIDANCE_REFRESHED total={len(updated['feedback'])} output={profile_path}")
    return 0


def command_extract_review(args: argparse.Namespace) -> int:
    candidates = validate_candidates(contract.load_json(Path(args.candidates).expanduser()))
    review_path = Path(args.review).expanduser()
    feedback = extract_review_feedback(review_path.read_text(encoding="utf-8"), candidates)
    proposal = {
        "schema_version": SCHEMA_VERSION,
        "feedback": feedback,
    }
    output = Path(args.output).expanduser()
    contract.write_json_atomic(output, proposal)
    print(f"RADAR_FEEDBACK_PROPOSAL_READY candidates={len(feedback)} output={output}")
    return 0


def command_show_guidance(args: argparse.Namespace) -> int:
    profile = validate_profile(contract.load_json(Path(args.profile).expanduser()))
    guidance = profile["derived_guidance"]
    print("# 下一轮 Radar 中文提示")
    print(f"项目：{profile['project']['name']}")
    print("已确认偏好：" + ("、".join(guidance["approved_tags"]) or "尚无"))
    print("需降权特征：" + ("、".join(guidance["avoid_tags"]) or "尚无"))
    for item in guidance["next_run_guidance"]:
        print(f"- {item}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create a visible Chinese project feedback profile")
    init.add_argument("--output", required=True)
    init.add_argument("--project-name", required=True)
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
    record.set_defaults(handler=command_record)
    replace = commands.add_parser("replace-feedback", help="replace a misparsed batch while keeping an immutable local archive")
    replace.add_argument("--profile", required=True)
    replace.add_argument("--feedback", required=True)
    replace.add_argument("--archive", required=True)
    replace.set_defaults(handler=command_replace_feedback)
    refresh = commands.add_parser("refresh-guidance", help="recompute guidance from raw feedback without changing it")
    refresh.add_argument("--profile", required=True)
    refresh.set_defaults(handler=command_refresh_guidance)
    extract = commands.add_parser("extract-review", help="turn a completed Chinese review into an inspectable feedback proposal")
    extract.add_argument("--review", required=True)
    extract.add_argument("--candidates", required=True)
    extract.add_argument("--output", required=True)
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
