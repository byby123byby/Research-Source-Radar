#!/usr/bin/env python3
"""Validate structural bridges, inventory local source text, and audit a reading ledger.

`inventory` splits already-obtained local Markdown/text (extracted full text,
supplements) into hashed section units. `audit` checks that a reading ledger
covers or explicitly excludes every unit, that the originals are unchanged, and
that adopted items cite real local evidence. This checks declared, hash-bound
coverage and correspondence, not scientific equivalence. It never fetches
sources, executes target code, or certifies semantic completeness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


INVENTORY_SCHEMA = 1
LEDGER_SCHEMA = 2
PLACEHOLDERS = {
    "x", "xx", "ok", "okay", "none", "null", "nil", "n/a", "na", "tbd", "todo", "-", "--", "...", "…",
    "pass", "passed", "done", "yes", "fine", "same", "see above", "unknown", "unverified",
    "无", "暂无", "略", "待补", "待定", "见上", "同上", "通过", "已完成", "完成", "是", "好",
}
UNPINNED_VERSIONS = {"unknown", "unverified", "latest", "head", "main", "master"}
MIN_EVIDENCE_TEXT = 6
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
FENCE = re.compile(r"^[ \t]*(```|~~~)")
SUPPLEMENT_PATTERNS = (
    (re.compile(r"\b(Table|Fig(?:ure)?\.?)\s*S(\d+)\b", re.I), lambda m: ("table" if m.group(1).lower().startswith("t") else "figure") + f" s{m.group(2)}"),
    (re.compile(r"\bAppendix\s+([A-Z]|\d+)\b"), lambda m: f"appendix {m.group(1).lower()}"),
    (re.compile(r"\b(Supplementary|Supplemental|Supporting Information|SI Appendix|Online Appendix)\b", re.I), lambda m: "supplementary"),
    (re.compile(r"(附表|附图)\s*S?(\d+)"), lambda m: f"{m.group(1)}{m.group(2)}"),
    (re.compile(r"(补充材料|补充信息|在线附录|附录)"), lambda m: m.group(1)),
)


# ---------------------------------------------------------------- shared validation

def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(f"{field} must be non-empty text, at most 4000 characters")
    return value.strip()


def strings(value: Any, field: str, *, required: bool = True) -> list[str]:
    if not isinstance(value, list) or len(value) > 40 or (required and not value):
        raise ValueError(f"{field} must be a bounded {'non-empty ' if required else ''}list")
    return list(dict.fromkeys(text(item, field) for item in value))


def is_placeholder(value: Any, *, min_length: int = 1) -> bool:
    """True when a declared field is missing, a stock filler word, or too short to be evidence."""
    if not isinstance(value, str):
        return True
    stripped = " ".join(value.split())
    return not stripped or stripped.casefold().strip(".。!！") in PLACEHOLDERS or len(stripped) < min_length


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def validate_bridge(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("bridge must be an object")
    result: dict[str, Any] = {key: text(value.get(key), f"bridge.{key}") for key in (
        "bridge_id", "source_domain", "shared_structure", "target_problem",
        "target_benefit", "minimum_check",
    )}
    for key in ("search_terms", "assumptions", "breaks_when"):
        result[key] = strings(value.get(key), f"bridge.{key}")
    result["evidence_refs"] = strings(value.get("evidence_refs", []), "bridge.evidence_refs", required=False)
    result["relation_type"] = value.get("relation_type", "analogy")
    if result["relation_type"] not in {"formal_equivalence", "conditional_approximation", "method_transfer", "analogy"}:
        raise ValueError("bridge.relation_type is unsupported")
    result["status"] = value.get("status", "hypothesis")
    if result["status"] not in {"hypothesis", "source_supported"}:
        raise ValueError("bridge.status must be hypothesis or source_supported")
    if result["status"] == "source_supported" and not result["evidence_refs"]:
        raise ValueError("source_supported bridge needs original-source evidence references")
    mapping = value.get("mapping")
    if not isinstance(mapping, list) or not 1 <= len(mapping) <= 30:
        raise ValueError("bridge.mapping must contain role/relation correspondences")
    result["mapping"] = [
        {key: text(row.get(key), f"bridge.mapping.{key}") for key in ("source_role", "target_role", "relation")}
        for row in mapping if isinstance(row, dict)
    ]
    if len(result["mapping"]) != len(mapping):
        raise ValueError("bridge.mapping entries must be objects")
    return result


# ---------------------------------------------------------------- inventory

def split_units(material_id: str, lines: list[str]) -> list[dict[str, Any]]:
    """Partition text into non-overlapping units: optional preamble, then one unit per heading.

    Units are numbered in document order, so repeated headings (two "Methods",
    several "Appendix") keep distinct IDs instead of overwriting each other.
    """
    starts: list[tuple[int, int, str]] = []  # (0-based line, level, heading)
    in_fence = False
    for index, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else HEADING.match(line)
        if match:
            starts.append((index, len(match.group(1)), match.group(2).strip()))
    bounds: list[tuple[int, int, int, str]] = []
    first = starts[0][0] if starts else len(lines)
    if any(line.strip() for line in lines[:first]):
        bounds.append((0, first, 0, "(preamble)"))
    for position, (start, level, heading) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        bounds.append((start, end, level, heading))
    units = []
    for number, (start, end, level, heading) in enumerate(bounds):
        body = lines[start + (1 if level else 0):end]
        chunk = "\n".join(lines[start:end])
        units.append({
            "id": f"{material_id}#{number:03d}",
            "heading": heading,
            "level": level,
            "line_start": start + 1,
            "line_end": max(start + 1, end),
            "sha256": sha256_bytes(chunk.encode("utf-8")),
            "empty": not any(line.strip() for line in body),
        })
    return units


def supplement_mentions(lines: list[str]) -> list[dict[str, Any]]:
    found: dict[str, list[int]] = {}
    for number, line in enumerate(lines, 1):
        for pattern, key_of in SUPPLEMENT_PATTERNS:
            for match in pattern.finditer(line):
                found.setdefault(key_of(match), []).append(number)
    return [{"key": key, "lines": sorted(set(numbers))[:20]} for key, numbers in sorted(found.items())]


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: not UTF-8 text; extract the source to Markdown/text first") from exc


def build_inventory(specs: list[tuple[str, Path]], base: Path) -> dict[str, Any]:
    if not specs:
        raise ValueError("inventory needs at least one --material ID=PATH")
    materials, seen = [], set()
    for material_id, path in specs:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", material_id):
            raise ValueError(f"material id {material_id!r} must use letters, digits, '.', '_' or '-'")
        if material_id in seen:
            raise ValueError(f"duplicate material id: {material_id}")
        seen.add(material_id)
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise ValueError(f"material {material_id}: file not found: {path}")
        lines = read_lines(resolved)
        try:
            stored = str(resolved.relative_to(base.resolve()))
        except ValueError:
            stored = str(resolved)
        materials.append({
            "id": material_id,
            "path": stored,
            "sha256": sha256_file(resolved),
            "line_count": len(lines),
            "units": split_units(material_id, lines),
            "supplement_mentions": supplement_mentions(lines),
        })
    return {"schema_version": INVENTORY_SCHEMA, "kind": "source_inventory", "materials": materials}


def parse_material_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise ValueError(f"--material must be ID=PATH, got {spec!r}")
    material_id, path = spec.split("=", 1)
    return material_id.strip(), Path(path.strip())


# ---------------------------------------------------------------- ledger typing

def _expect(value: Any, kind: type, field: str) -> Any:
    if not isinstance(value, kind):
        raise ValueError(f"{field} must be {'an object' if kind is dict else 'a list' if kind is list else 'text'}, got {type(value).__name__}")
    return value


def check_ledger_types(ledger: Any) -> None:
    """Reject malformed structure with a readable error instead of a traceback."""
    _expect(ledger, dict, "ledger")
    for key in ("materials", "items"):
        _expect(ledger.get(key, []), list, key)
    for index, material in enumerate(ledger.get("materials", [])):
        _expect(material, dict, f"materials[{index}]")
        _expect(material.get("id"), str, f"materials[{index}].id")
    for index, item in enumerate(ledger.get("items", [])):
        _expect(item, dict, f"items[{index}]")
        _expect(item.get("id"), str, f"items[{index}].id")
        for key in ("material_id", "decision", "source_version"):
            if key in item:
                _expect(item[key], str, f"items[{index}].{key}")
        if "unit_ids" in item:
            units = _expect(item["unit_ids"], list, f"items[{index}].unit_ids")
            for position, unit in enumerate(units):
                _expect(unit, str, f"items[{index}].unit_ids[{position}]")
        if "verification" in item:
            _expect(item["verification"], dict, f"items[{index}].verification")
    for key in ("excluded_units", "supplement_links"):
        mapping = _expect(ledger.get(key, {}), dict, key)
        for name, value in mapping.items():
            if key == "excluded_units":
                _expect(value, str, f"excluded_units[{name!r}]")
            else:
                _expect(value, dict, f"supplement_links[{name!r}]")
                if "material_id" in value:
                    _expect(value["material_id"], str, f"supplement_links[{name!r}].material_id")


def resolve(base: Path, ref: Any) -> Path | None:
    if not isinstance(ref, str) or not ref.strip():
        return None
    path = Path(ref.split("#", 1)[0].strip()).expanduser()
    return path if path.is_absolute() else (base / path)


# ---------------------------------------------------------------- audit

def load_inventory(ledger: dict[str, Any], base: Path, gaps: list[str]) -> tuple[dict[str, Any] | None, Path]:
    path = resolve(base, ledger.get("inventory_ref"))
    if path is None:
        gaps.append("missing inventory_ref: run `mechanism_transfer.py inventory` on the obtained originals first")
        return None, base
    if not path.is_file():
        gaps.append(f"inventory file not found: {ledger.get('inventory_ref')}")
        return None, base
    expected = ledger.get("inventory_sha256")
    actual = sha256_file(path)
    if not isinstance(expected, str) or expected != actual:
        gaps.append("inventory_sha256 missing or does not match the inventory file")
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"inventory is not valid JSON: {exc}") from exc
    if not isinstance(inventory, dict) or inventory.get("kind") != "source_inventory" or not isinstance(inventory.get("materials"), list):
        raise ValueError("inventory_ref does not point to a source_inventory produced by `inventory`")
    for index, material in enumerate(inventory["materials"]):
        _expect(material, dict, f"inventory.materials[{index}]")
        for key in ("id", "path", "sha256"):
            _expect(material.get(key), str, f"inventory.materials[{index}].{key}")
        for position, unit in enumerate(_expect(material.get("units"), list, f"inventory.materials[{index}].units")):
            _expect(unit, dict, f"inventory.materials[{index}].units[{position}]")
            if not isinstance(unit.get("id"), str) or not all(isinstance(unit.get(k), int) for k in ("line_start", "line_end")):
                raise ValueError(f"inventory.materials[{index}].units[{position}] needs id and integer line range")
        for position, mention in enumerate(_expect(material.get("supplement_mentions", []), list,
                                                   f"inventory.materials[{index}].supplement_mentions")):
            field = f"inventory.materials[{index}].supplement_mentions[{position}]"
            _expect(mention, dict, field)
            _expect(mention.get("key"), str, f"{field}.key")
            lines = _expect(mention.get("lines"), list, f"{field}.lines")
            if not all(isinstance(line, int) and not isinstance(line, bool) for line in lines):
                raise ValueError(f"{field}.lines must contain line numbers")
    return inventory, path.parent


def recheck_originals(inventory: dict[str, Any], inv_base: Path, gaps: list[str]) -> dict[str, dict[str, Any]]:
    """Re-hash each original; a changed or missing file invalidates every coverage claim on it."""
    units: dict[str, dict[str, Any]] = {}
    material_ids = [material["id"] for material in inventory["materials"]]
    for duplicate in sorted({mid for mid in material_ids if material_ids.count(mid) > 1}):
        gaps.append(f"inventory lists material {duplicate} more than once")
    unit_ids = [unit["id"] for material in inventory["materials"] for unit in material["units"]]
    for duplicate in sorted({uid for uid in unit_ids if unit_ids.count(uid) > 1}):
        gaps.append(f"inventory repeats unit id {duplicate}")
    for material in inventory["materials"]:
        mid = material.get("id")
        path = resolve(inv_base, material.get("path"))
        current_lines = None
        if path is None or not path.is_file():
            gaps.append(f"{mid}: original file unavailable ({material.get('path')}); re-obtain it and rebuild the inventory")
        elif sha256_file(path) != material.get("sha256"):
            gaps.append(f"{mid}: original changed since inventory (sha256 mismatch); rebuild the inventory and re-review")
        else:
            current_lines = read_lines(path)
            # A matching file hash proves nothing about an edited inventory: regenerate
            # the structure from the original and require an exact match.
            if (material["units"] != split_units(mid, current_lines)
                    or material.get("supplement_mentions", []) != supplement_mentions(current_lines)
                    or material.get("line_count") != len(current_lines)):
                gaps.append(f"{mid}: inventory units/mentions/line_count differ from the structure regenerated from the original; rebuild the inventory")
        for unit in material.get("units", []):
            record = dict(unit, material_id=mid, text=None)
            if current_lines is not None:
                record["text"] = "\n".join(current_lines[unit["line_start"] - 1:unit["line_end"]])
            units[unit["id"]] = record
    return units


def audit_reading(ledger: dict[str, Any], base: Path | None = None) -> dict[str, Any]:
    """Fail closed on unlisted units, changed originals, placeholder evidence and missing decisions."""
    check_ledger_types(ledger)
    base = (base or Path.cwd()).resolve()
    gaps: list[str] = []
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        gaps.append(f"ledger schema_version must be {LEDGER_SCHEMA} (hash-bound inventory); older ledgers cannot support a completion claim")
    inventory, inv_base = load_inventory(ledger, base, gaps)
    units = recheck_originals(inventory, inv_base, gaps) if inventory else {}
    inventoried = {m["id"]: m for m in inventory["materials"]} if inventory else {}

    materials = ledger.get("materials", [])
    items = ledger.get("items", [])
    if not materials or not items:
        gaps.append("empty materials or mechanism/claim inventory")
    by_id: dict[str, dict[str, Any]] = {}
    for material in materials:
        mid = text(material.get("id"), "material.id")
        if mid in by_id:
            raise ValueError(f"duplicate material: {mid}")
        by_id[mid] = material
        if inventory and mid not in inventoried:
            gaps.append(f"{mid}: listed in ledger but absent from the hash-bound inventory")
        if is_placeholder(material.get("source_ref")):
            gaps.append(f"{mid}: missing source_ref")
        version = material.get("version")
        if is_placeholder(version) or str(version).strip().casefold() in UNPINNED_VERSIONS:
            gaps.append(f"{mid}: missing or unpinned version")
        status = material.get("read_status")
        if status == "not_applicable":
            if is_placeholder(material.get("reason"), min_length=MIN_EVIDENCE_TEXT):
                gaps.append(f"{mid}: not_applicable without a substantive reason")
        elif status != "read":
            gaps.append(f"{mid}: material not fully reviewed ({status})")
    for mid in inventoried:
        if mid not in by_id:
            gaps.append(f"{mid}: inventoried original missing from ledger materials (unlisted source)")

    covered: dict[str, list[str]] = {}
    seen: set[str] = set()
    decisions: dict[str, int] = {}
    open_items: list[str] = []
    for item in items:
        iid = text(item.get("id"), "item.id")
        if iid in seen:
            raise ValueError(f"duplicate inventory item: {iid}")
        seen.add(iid)
        material = by_id.get(item.get("material_id"))
        if not material:
            gaps.append(f"{iid}: unknown material")
        elif item.get("source_version") != material.get("version"):
            gaps.append(f"{iid}: source version mismatch")
        unit_ids = item.get("unit_ids") or []
        if not unit_ids:
            gaps.append(f"{iid}: no unit_ids locating the claim in the inventoried original")
        for unit_id in unit_ids:
            unit = units.get(unit_id)
            if unit is None:
                gaps.append(f"{iid}: unit {unit_id} is not in the inventory")
            elif material and unit["material_id"] != material.get("id"):
                gaps.append(f"{iid}: unit {unit_id} belongs to {unit['material_id']}, not {material.get('id')}")
            else:
                covered.setdefault(unit_id, []).append(iid)
        quote = item.get("quote")
        if quote is not None:
            haystack = " ".join(" ".join(units[u]["text"].split()) for u in unit_ids if u in units and units[u]["text"])
            if not isinstance(quote, str) or " ".join(quote.split()) not in haystack:
                gaps.append(f"{iid}: quote not found in the cited units")
        for key in ("claim", "conditions", "limitations"):
            if is_placeholder(item.get(key), min_length=2):
                gaps.append(f"{iid}: missing {key}")
        if is_placeholder(item.get("source_location")) and not unit_ids:
            gaps.append(f"{iid}: missing source_location")
        decision = item.get("decision")
        decisions[str(decision)] = decisions.get(str(decision), 0) + 1
        if decision not in {"direct", "adapt", "reject", "unverified"}:
            gaps.append(f"{iid}: invalid decision")
        if decision == "unverified":
            open_items.append(iid)
            gaps.append(f"{iid}: unresolved source-to-target mapping")
        if decision == "reject" and is_placeholder(item.get("reason"), min_length=MIN_EVIDENCE_TEXT):
            gaps.append(f"{iid}: rejection lacks rationale")
        if decision in {"direct", "adapt"}:
            gaps.extend(f"{iid}: {problem}" for problem in target_evidence_problems(item, base))

    # A material-wide "nothing relevant here" only holds when nothing from it was mapped;
    # otherwise each leftover unit still needs its own explanation.
    mapped_materials = {item.get("material_id") for item in items} | {units[u]["material_id"] for u in covered}
    blanket: set[str] = set()
    for mid, material in by_id.items():
        declares = material.get("read_status") == "not_applicable" or not is_placeholder(
            material.get("no_relevant_items_reason"), min_length=MIN_EVIDENCE_TEXT)
        if declares and mid in mapped_materials:
            gaps.append(f"{mid}: declared not_applicable/no_relevant_items_reason but has mapped items; exclude leftover units individually")
        elif declares:
            blanket.add(mid)
    excluded: set[str] = set()
    for unit_id, unit in units.items():
        if unit_id in covered or unit["empty"]:
            continue
        if unit["material_id"] in blanket:
            excluded.add(unit_id)
            continue
        reason = ledger.get("excluded_units", {}).get(unit_id)
        if reason is not None:
            if is_placeholder(reason, min_length=MIN_EVIDENCE_TEXT):
                gaps.append(f"{unit_id}: exclusion reason is a placeholder")
            else:
                excluded.add(unit_id)
            continue
        gaps.append(f"{unit_id} ({unit['heading']}, lines {unit['line_start']}-{unit['line_end']}): neither mapped nor explicitly excluded")
    for unit_id in ledger.get("excluded_units", {}):
        if units and unit_id not in units:
            gaps.append(f"excluded unit {unit_id} is not in the inventory")

    headings = " ".join(unit["heading"].casefold() for unit in units.values())
    links = ledger.get("supplement_links", {})
    unobtained: list[str] = []
    for material in (inventory or {}).get("materials", []):
        for mention in material.get("supplement_mentions", []):
            key = mention["key"]
            link = links.get(key)
            if link is None:
                if key in headings:
                    continue
                gaps.append(f"{material['id']} mentions '{key}' (lines {mention['lines'][:5]}) but no inventoried material or supplement_links entry resolves it")
            elif "material_id" in link:
                if link["material_id"] not in inventoried:
                    gaps.append(f"supplement_links['{key}'] points to {link['material_id']}, which is not inventoried")
            elif link.get("status") != "unavailable" or is_placeholder(link.get("reason"), min_length=MIN_EVIDENCE_TEXT):
                gaps.append(f"supplement_links['{key}'] must name an inventoried material_id or status=unavailable with a reason")
            else:
                # Recorded honestly, but a known unread supplement is still a gap:
                # discovery may report partial reading, a migration cannot be called complete.
                unobtained.append(key)
                gaps.append(f"supplement '{key}' is known but not obtained ({link['reason']}); full-migration claim not permitted")

    countable = [u for u in units.values() if not u["empty"]]
    return {
        "structural_gate": "blocked" if gaps else "passed",
        "completion_claim_permitted_by_structure": not gaps,
        "gaps": gaps,
        "coverage": {
            "units": len(countable),
            "mapped": sum(1 for u in countable if u["id"] in covered),
            "excluded": sum(1 for u in countable if u["id"] in excluded),
            "uncovered": sum(1 for u in countable if u["id"] not in covered and u["id"] not in excluded),
        } if units else {},
        "decisions": decisions,
        "open_items": open_items,
        "unobtained_supplements": sorted(set(unobtained)),
        "boundary": "Checks hash-bound coverage of the inventoried text and declared evidence. It cannot see material that was never obtained or inventoried, judge whether a claim was understood correctly, or confirm that a cited result is true; a reviewer must still compare with the originals.",
    }


def placeholder_file(path: Path) -> bool:
    """True for an empty file or one whose whole text is a stock filler word.

    Only obvious non-evidence is rejected; length is not treated as truth, and
    non-text evidence (images, recordings) is accepted when non-empty.
    """
    data = path.read_bytes()
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return not data
    return is_placeholder(content)


def target_evidence_problems(item: dict[str, Any], base: Path) -> list[str]:
    problems = []
    target = resolve(base, item.get("target_ref"))
    if target is None or is_placeholder(item.get("target_behavior"), min_length=MIN_EVIDENCE_TEXT):
        problems.append("missing target mapping/behavior")
    elif not target.is_file():
        problems.append(f"target_ref is not an existing local file: {item.get('target_ref')}")
    elif placeholder_file(target):
        problems.append(f"target_ref file is empty or only a placeholder: {item.get('target_ref')}")
    verification = item.get("verification") or {}
    if verification.get("status") != "verified":
        problems.append("target behavior has no complete verification record")
        return problems
    evidence = resolve(base, verification.get("evidence_ref"))
    if evidence is None or not evidence.is_file():
        problems.append(f"verification evidence_ref is not a local file: {verification.get('evidence_ref')!r}")
    elif verification.get("evidence_sha256") != sha256_file(evidence):
        problems.append("verification evidence_sha256 missing or does not match the evidence file")
    elif placeholder_file(evidence):
        problems.append("verification evidence file is empty or only a placeholder")
    for key in ("result", "failure_case"):
        if is_placeholder(verification.get(key), min_length=MIN_EVIDENCE_TEXT):
            problems.append(f"verification {key} is missing or a placeholder")
    if not problems and " ".join(str(verification["result"]).split()) == " ".join(str(verification["failure_case"]).split()):
        problems.append("verification failure_case repeats the result")
    return problems


# ---------------------------------------------------------------- CLI

def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_inventory(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mechanism_transfer.py inventory",
                                     description="Hash and section local Markdown/text originals.")
    parser.add_argument("--material", action="append", required=True, metavar="ID=PATH",
                        help="obtained original as Markdown/text; repeat for full text, supplements, appendices")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser()
    inventory = build_inventory([parse_material_spec(spec) for spec in args.material], output.resolve().parent)
    write_json(output, inventory)
    print(json.dumps({"status": "inventory_ready", "output": str(output), "inventory_sha256": sha256_file(output),
                      "units": {m["id"]: len(m["units"]) for m in inventory["materials"]}}, ensure_ascii=False))
    return 0


def command_audit(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mechanism_transfer.py [audit]",
                                     description="Audit a hash-bound reading ledger; exit 1 when blocked.")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    ledger_path = Path(args.ledger).expanduser()
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"ledger is not valid JSON: {exc}") from exc
    result = audit_reading(ledger, ledger_path.resolve().parent)
    write_json(Path(args.output).expanduser(), result)
    print(json.dumps({"structural_gate": result["structural_gate"], "gaps": len(result["gaps"])}, ensure_ascii=False))
    return 1 if result["gaps"] else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv[:1] == ["inventory"]:
            return command_inventory(argv[1:])
        return command_audit(argv[1:] if argv[:1] == ["audit"] else argv)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
