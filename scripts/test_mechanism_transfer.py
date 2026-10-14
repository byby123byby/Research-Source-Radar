#!/usr/bin/env python3

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import mechanism_transfer as mt


SCRIPT = Path(__file__).resolve().parent / "mechanism_transfer.py"
PAPER = """Title line before any heading.

## Abstract
We model reminder timing as a contextual bandit.

## Methods
Reward is an on-time dose within two hours.

### Sampling
```
# not a heading inside a code fence
```

## Methods
Second methods section: Thompson sampling policy with stationary context.

## Results
Coverage improved; see Table S1 and the Supplementary analysis.

## Appendix A
Robustness tables only.
"""
SUPPLEMENT = """# Table S1
Per-site results, no new mechanism.
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Workspace:
    """A temp directory with originals, an inventory, target design and evidence files."""

    def __init__(self, root, *, with_supplement=True):
        self.root = Path(root)
        (self.root / "paper.md").write_text(PAPER, encoding="utf-8")
        (self.root / "supp.md").write_text(SUPPLEMENT, encoding="utf-8")
        (self.root / "design.md").write_text("reward from pill-bottle log\n", encoding="utf-8")
        (self.root / "replay.log").write_text("replay 2026-10-14: matched 48/50; missing log flagged\n", encoding="utf-8")
        specs = [("M1", self.root / "paper.md")] + ([("M2", self.root / "supp.md")] if with_supplement else [])
        self.inventory = mt.build_inventory(specs, self.root)
        (self.root / "inventory.json").write_text(json.dumps(self.inventory), encoding="utf-8")
        self.units = {u["heading"] + f"@{u['line_start']}": u["id"] for m in self.inventory["materials"] for u in m["units"]}

    def unit(self, heading, occurrence=0):
        return [uid for key, uid in self.units.items() if key.split("@")[0] == heading][occurrence]

    def ledger(self):
        methods_1, methods_2 = self.unit("Methods", 0), self.unit("Methods", 1)
        materials = [{"id": "M1", "source_ref": "doi:10.0000/fixture", "version": "v2", "read_status": "read"}]
        links = {}
        if any(m["id"] == "M2" for m in self.inventory["materials"]):
            materials.append({"id": "M2", "source_ref": "doi:10.0000/fixture#supp", "version": "v2", "read_status": "read",
                              "no_relevant_items_reason": "per-site robustness tables only, no new mechanism"})
            links = {"supplementary": {"material_id": "M2"}}
        return {
            "schema_version": 2,
            "inventory_ref": "inventory.json",
            "inventory_sha256": sha(self.root / "inventory.json"),
            "materials": materials,
            "supplement_links": links,
            "excluded_units": {
                self.unit("(preamble)"): "title line only, no claim",
                self.unit("Abstract"): "summarised claims are covered by the Methods units",
                self.unit("Results"): "outcome numbers, not a transferable mechanism",
                self.unit("Appendix A"): "robustness tables only, no new mechanism",
            },
            "items": [
                {"id": "I1", "material_id": "M1", "source_version": "v2", "unit_ids": [methods_1],
                 "quote": "on-time dose within two hours",
                 "claim": "reward = on-time dose within 2h", "conditions": "dose events observable",
                 "limitations": "self-report bias", "decision": "adapt",
                 "target_ref": "design.md#reward", "target_behavior": "reward computed from pill-bottle log",
                 "verification": {"status": "verified", "evidence_ref": "replay.log",
                                  "evidence_sha256": sha(self.root / "replay.log"),
                                  "result": "matched 48/50 historical doses",
                                  "failure_case": "missing log -> reward undefined, flagged for review"}},
                {"id": "I2", "material_id": "M1", "source_version": "v2", "unit_ids": [methods_2, self.unit("Sampling")],
                 "claim": "Thompson sampling policy", "conditions": "stationary context", "limitations": "drift",
                 "decision": "reject", "reason": "clinic forbids adaptive randomization in phase 1"},
            ],
        }

    def audit(self, ledger):
        return mt.audit_reading(ledger, self.root)

    def tampered_ledger(self, mutate):
        """Edit inventory.json, then re-bind the ledger to the edited file's new hash."""
        inventory = json.loads((self.root / "inventory.json").read_text(encoding="utf-8"))
        mutate(inventory)
        (self.root / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
        return self.ledger()


class InventoryTests(unittest.TestCase):
    def test_sections_are_unique_ordered_and_fence_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            paper = ws.inventory["materials"][0]
            headings = [u["heading"] for u in paper["units"]]
            self.assertEqual(["(preamble)", "Abstract", "Methods", "Sampling", "Methods", "Results", "Appendix A"], headings)
            ids = [u["id"] for u in paper["units"]]
            self.assertEqual(len(ids), len(set(ids)))
            for previous, current in zip(paper["units"], paper["units"][1:]):
                self.assertEqual(previous["line_end"] + 1, current["line_start"])
            self.assertNotIn("not a heading inside a code fence", headings)
            self.assertNotEqual(paper["units"][2]["sha256"], paper["units"][4]["sha256"])
            self.assertEqual(sha(ws.root / "paper.md"), paper["sha256"])
            self.assertEqual("paper.md", paper["path"])

    def test_supplement_mentions_are_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys = {m["key"] for m in Workspace(tmp).inventory["materials"][0]["supplement_mentions"]}
            self.assertTrue({"table s1", "supplementary", "appendix a"} <= keys)

    def test_chinese_supplement_mentions(self):
        lines = ["结果见附表S2与补充材料。", "## 附录"]
        keys = {m["key"] for m in mt.supplement_mentions(lines)}
        self.assertTrue({"附表2", "补充材料", "附录"} <= keys)

    def test_duplicate_material_id_and_binary_input_are_clear_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("# A\nx\n", encoding="utf-8")
            (root / "b.pdf").write_bytes(b"%PDF-1.7\xff\xfe\x00")
            with self.assertRaisesRegex(ValueError, "duplicate material id"):
                mt.build_inventory([("M1", root / "a.md"), ("M1", root / "a.md")], root)
            with self.assertRaisesRegex(ValueError, "not UTF-8"):
                mt.build_inventory([("M1", root / "b.pdf")], root)


class AuditTests(unittest.TestCase):
    def assertBlocked(self, result, fragment):
        self.assertEqual("blocked", result["structural_gate"], result["gaps"])
        self.assertTrue(any(fragment in gap for gap in result["gaps"]), result["gaps"])

    def test_complete_ledger_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            result = ws.audit(ws.ledger())
            self.assertEqual("passed", result["structural_gate"], result["gaps"])
            self.assertEqual(0, result["coverage"]["uncovered"])
            self.assertEqual({"adapt": 1, "reject": 1}, result["decisions"])

    # T10: omitted material or section
    def test_unlisted_supplement_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp, with_supplement=False)
            self.assertBlocked(ws.audit(ws.ledger()), "mentions 'table s1'")

    def test_unmapped_unexcluded_section_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            del ledger["excluded_units"][ws.unit("Appendix A")]
            self.assertBlocked(ws.audit(ledger), "neither mapped nor explicitly excluded")

    def test_second_methods_section_is_not_covered_by_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["items"][1]["unit_ids"] = [ws.unit("Sampling")]
            self.assertBlocked(ws.audit(ledger), ws.unit("Methods", 1))

    def test_inventoried_material_missing_from_ledger_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["materials"] = ledger["materials"][:1]
            self.assertBlocked(ws.audit(ledger), "M2: inventoried original missing")

    def test_unavailable_supplement_needs_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp, with_supplement=False)
            ledger = ws.ledger()
            ledger["supplement_links"] = {"table s1": {"status": "unavailable", "reason": "ok"},
                                          "supplementary": {"status": "unavailable", "reason": "publisher SI behind paywall, requested"}}
            self.assertBlocked(ws.audit(ledger), "supplement_links['table s1']")

    def test_unobtained_supplement_stays_a_gap_even_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp, with_supplement=False)
            ledger = ws.ledger()
            reason = "publisher SI behind paywall, requested"
            ledger["supplement_links"] = {"table s1": {"status": "unavailable", "reason": reason},
                                          "supplementary": {"status": "unavailable", "reason": reason}}
            result = ws.audit(ledger)
            self.assertBlocked(result, "supplement 'table s1' is known but not obtained")
            self.assertFalse(result["completion_claim_permitted_by_structure"])
            self.assertEqual(["supplementary", "table s1"], result["unobtained_supplements"])
            self.assertFalse(any("must name an inventoried" in gap for gap in result["gaps"]))

    # T11: placeholder or unbound evidence
    def test_placeholder_verification_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            for value in ("x", "ok", "none", "通过"):
                ledger = ws.ledger()
                ledger["items"][0]["verification"].update(result=value, failure_case="none")
                self.assertBlocked(ws.audit(ledger), "placeholder")

    def test_evidence_must_be_existing_hashed_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["items"][0]["verification"]["evidence_ref"] = "x"
            self.assertBlocked(ws.audit(ledger), "not a local file")
            ledger = ws.ledger()
            ledger["items"][0]["verification"]["evidence_sha256"] = "0" * 64
            self.assertBlocked(ws.audit(ledger), "evidence_sha256")

    def test_placeholder_evidence_file_blocks_even_with_honest_hash(self):
        for content in ("x", "ok", "none\n", "  \n", "", "通过"):
            with tempfile.TemporaryDirectory() as tmp:
                ws = Workspace(tmp)
                (ws.root / "replay.log").write_text(content, encoding="utf-8")
                with self.subTest(content=content):
                    self.assertBlocked(ws.audit(ws.ledger()), "evidence file is empty or only a placeholder")

    def test_placeholder_target_file_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            (ws.root / "design.md").write_text("TODO\n", encoding="utf-8")
            self.assertBlocked(ws.audit(ws.ledger()), "target_ref file is empty or only a placeholder")

    def test_short_non_cs_and_binary_evidence_remain_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            (ws.root / "design.md").write_text("访谈编码整合流程：冲突结果进入整合矩阵并写明裁量理由\n", encoding="utf-8")
            (ws.root / "replay.log").write_text("案例比较：4 份已发表研究中 3 份复现出被忽略的冲突\n", encoding="utf-8")
            self.assertEqual("passed", ws.audit(ws.ledger())["structural_gate"])
            (ws.root / "replay.log").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xffscreenshot")
            self.assertEqual("passed", ws.audit(ws.ledger())["structural_gate"])

    def test_material_wide_irrelevance_cannot_hide_unread_section_of_mapped_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            second_methods = ws.unit("Methods", 1)
            ledger["items"][1]["unit_ids"] = [ws.unit("Sampling")]
            ledger["materials"][0]["no_relevant_items_reason"] = "nothing else in this paper matters for the project"
            result = ws.audit(ledger)
            self.assertBlocked(result, "M1: declared not_applicable/no_relevant_items_reason but has mapped items")
            self.assertBlocked(result, f"{second_methods} (Methods")
            ledger["materials"][0].update(read_status="not_applicable", reason="outside the project's scope entirely")
            del ledger["materials"][0]["no_relevant_items_reason"]
            self.assertBlocked(ws.audit(ledger), "M1: declared not_applicable")

    def test_material_wide_irrelevance_still_works_without_mapped_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            result = ws.audit(ledger)
            self.assertEqual("passed", result["structural_gate"], result["gaps"])
            self.assertFalse(any(item["material_id"] == "M2" for item in ledger["items"]))
            self.assertEqual(0, result["coverage"]["uncovered"])

    def test_target_ref_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["items"][0]["target_ref"] = "src/not-written-yet.py"
            self.assertBlocked(ws.audit(ledger), "target_ref is not an existing local file")

    def test_placeholder_exclusion_and_rejection_reason_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["excluded_units"][ws.unit("Results")] = "none"
            self.assertBlocked(ws.audit(ledger), "exclusion reason is a placeholder")
            ledger = ws.ledger()
            ledger["items"][1]["reason"] = "n/a"
            self.assertBlocked(ws.audit(ledger), "rejection lacks rationale")

    def test_quote_must_appear_in_cited_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["items"][0]["quote"] = "reward is a weekly survey score"
            self.assertBlocked(ws.audit(ledger), "quote not found")

    # T12: original or inventory changed
    def test_changed_original_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            (ws.root / "paper.md").write_text(PAPER + "\n## Erratum\nReward window is 4 hours.\n", encoding="utf-8")
            self.assertBlocked(ws.audit(ledger), "original changed since inventory")

    def test_missing_original_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            (ws.root / "supp.md").unlink()
            self.assertBlocked(ws.audit(ws.ledger()), "original file unavailable")

    def test_edited_inventory_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            inventory = json.loads((ws.root / "inventory.json").read_text(encoding="utf-8"))
            inventory["materials"][0]["units"].pop()
            (ws.root / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
            self.assertBlocked(ws.audit(ledger), "inventory_sha256")

    def test_rehashed_inventory_with_dropped_unit_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            appendix = ws.unit("Appendix A")
            del ledger["excluded_units"][appendix]
            ledger["inventory_sha256"] = ws.tampered_ledger(lambda inv: inv["materials"][0]["units"].pop())["inventory_sha256"]
            result = ws.audit(ledger)
            self.assertBlocked(result, "differ from the structure regenerated from the original")
            self.assertFalse(any("inventory_sha256" in gap for gap in result["gaps"]))

    def test_rehashed_inventory_with_dropped_mention_or_line_count_blocks(self):
        mutations = [
            lambda inv: inv["materials"][0]["supplement_mentions"].pop(),
            lambda inv: inv["materials"][0].update(line_count=3),
            lambda inv: inv["materials"][0]["units"][2].update(line_end=7),
        ]
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as tmp:
                ws = Workspace(tmp)
                self.assertBlocked(ws.audit(ws.tampered_ledger(mutate)), "regenerated from the original")

    def test_duplicate_unit_or_material_ids_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.tampered_ledger(lambda inv: inv["materials"][0]["units"][4].update(id="M1#002"))
            self.assertBlocked(ws.audit(ledger), "inventory repeats unit id M1#002")
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.tampered_ledger(lambda inv: inv["materials"].append(copy.deepcopy(inv["materials"][1])))
            self.assertBlocked(ws.audit(ledger), "inventory lists material M2 more than once")

    def test_target_ref_must_be_a_file_not_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            (ws.root / "src").mkdir()
            ledger = ws.ledger()
            ledger["items"][0]["target_ref"] = "src"
            self.assertBlocked(ws.audit(ledger), "target_ref is not an existing local file")

    def test_free_text_inventory_ref_from_v1_ledger_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger.update(schema_version=1, inventory_ref="paper TOC + supplement index S1-S4")
            result = ws.audit(ledger)
            self.assertBlocked(result, "schema_version must be 2")
            self.assertBlocked(result, "inventory file not found")

    # retained guards
    def test_retained_material_version_and_decision_guards(self):
        cases = [
            (lambda w, l: l["materials"][0].update(read_status="partial"), "not fully reviewed"),
            (lambda w, l: l["items"][0].update(source_version="v1"), "source version mismatch"),
            (lambda w, l: l["materials"][0].update(version="latest"), "unpinned version"),
            (lambda w, l: l["items"][0].update(decision="unverified"), "unresolved source-to-target mapping"),
            (lambda w, l: l["items"][0]["verification"].update(failure_case=""), "failure_case"),
            (lambda w, l: l["items"][0].pop("target_behavior"), "missing target mapping/behavior"),
            (lambda w, l: l["items"][0].update(unit_ids=[]), "no unit_ids"),
            (lambda w, l: l["items"][0].update(unit_ids=["M2#000"]), "belongs to M2"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            for mutate, fragment in cases:
                ledger = ws.ledger()
                mutate(ws, ledger)
                with self.subTest(fragment=fragment):
                    self.assertBlocked(ws.audit(ledger), fragment)

    def test_unverified_items_are_listed_as_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["items"][0]["decision"] = "unverified"
            self.assertEqual(["I1"], ws.audit(ledger)["open_items"])

    def test_all_not_applicable_and_no_items_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["items"] = []
            for material in ledger["materials"]:
                material.update(read_status="not_applicable", reason="outside the project's scope entirely")
            self.assertBlocked(ws.audit(ledger), "empty materials")

    # T14: malformed input
    def test_malformed_types_raise_readable_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            cases = [
                (lambda l: l["materials"].append("M3-as-string"), "materials\\[2\\] must be an object"),
                (lambda l: l.__setitem__("items", {"I1": {}}), "items must be a list"),
                (lambda l: l["items"][0].__setitem__("unit_ids", "M1#002"), "unit_ids must be a list"),
                (lambda l: l["items"][0].__setitem__("verification", "verified"), "verification must be an object"),
                (lambda l: l.__setitem__("excluded_units", ["M1#000"]), "excluded_units must be an object"),
            ]
            for mutate, pattern in cases:
                ledger = ws.ledger()
                mutate(ledger)
                with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                    ws.audit(ledger)
            with self.assertRaisesRegex(ValueError, "ledger must be an object"):
                mt.audit_reading(["not", "a", "ledger"], ws.root)

    def test_unhashable_or_wrong_typed_fields_raise_field_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            cases = [
                (lambda l: l["items"][0].__setitem__("decision", {"adapt": True}), r"items\[0\]\.decision must be text"),
                (lambda l: l["items"][1].__setitem__("decision", ["reject"]), r"items\[1\]\.decision must be text"),
                (lambda l: l["items"][0].__setitem__("material_id", {"id": "M1"}), r"items\[0\]\.material_id must be text"),
                (lambda l: l["items"][0].__setitem__("source_version", ["v2"]), r"items\[0\]\.source_version must be text"),
                (lambda l: l["supplement_links"]["supplementary"].__setitem__("material_id", ["M2"]),
                 r"supplement_links\['supplementary'\]\.material_id must be text"),
            ]
            for mutate, pattern in cases:
                ledger = ws.ledger()
                mutate(ledger)
                with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                    ws.audit(ledger)

    def test_malformed_supplement_mentions_raise_field_errors(self):
        cases = [
            (lambda inv: inv["materials"][0]["supplement_mentions"].append("table s9"), r"supplement_mentions\[3\] must be an object"),
            (lambda inv: inv["materials"][0]["supplement_mentions"][0].__setitem__("key", 7), r"supplement_mentions\[0\]\.key must be text"),
            (lambda inv: inv["materials"][0]["supplement_mentions"][0].__setitem__("lines", "20"), r"supplement_mentions\[0\]\.lines must be a list"),
            (lambda inv: inv["materials"][0]["supplement_mentions"][0].__setitem__("lines", ["20"]), r"lines must contain line numbers"),
            (lambda inv: inv["materials"][0].__setitem__("supplement_mentions", {"key": "table s1"}), r"supplement_mentions must be a list"),
        ]
        for mutate, pattern in cases:
            with tempfile.TemporaryDirectory() as tmp:
                ws = Workspace(tmp)
                ledger = ws.tampered_ledger(mutate)
                with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                    ws.audit(ledger)


class CliTests(unittest.TestCase):
    def run_cli(self, *args, cwd):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, cwd=cwd)

    def test_inventory_then_audit_round_trip_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            built = self.run_cli("inventory", "--material", "M1=paper.md", "--material", "M2=supp.md",
                                 "--output", "inventory.json", cwd=tmp)
            self.assertEqual(0, built.returncode, built.stderr)
            self.assertEqual(sha(ws.root / "inventory.json"), json.loads(built.stdout)["inventory_sha256"])
            (ws.root / "ledger.json").write_text(json.dumps(ws.ledger()), encoding="utf-8")
            legacy_form = self.run_cli("--ledger", "ledger.json", "--output", "audit.json", cwd=tmp)
            self.assertEqual(0, legacy_form.returncode, legacy_form.stdout + legacy_form.stderr)
            ledger = ws.ledger()
            ledger["items"][0]["verification"]["result"] = "ok"
            (ws.root / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
            blocked = self.run_cli("audit", "--ledger", "ledger.json", "--output", "audit.json", cwd=tmp)
            self.assertEqual(1, blocked.returncode)
            self.assertEqual("blocked", json.loads((ws.root / "audit.json").read_text(encoding="utf-8"))["structural_gate"])

    def test_malformed_ledger_exits_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            ledger = ws.ledger()
            ledger["materials"].append("M3-as-string")
            (ws.root / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
            result = self.run_cli("--ledger", "ledger.json", "--output", "audit.json", cwd=tmp)
            self.assertEqual(2, result.returncode)
            self.assertIn("ERROR: materials[2] must be an object", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            (ws.root / "bad.json").write_text("{not json", encoding="utf-8")
            result = self.run_cli("--ledger", "bad.json", "--output", "audit.json", cwd=tmp)
            self.assertEqual(2, result.returncode)
            self.assertIn("not valid JSON", result.stderr)


class BridgeTests(unittest.TestCase):
    def test_bridge_validation_unchanged(self):
        bridge = {"bridge_id": "B1", "source_domain": "computing", "shared_structure": "s", "target_problem": "t",
                  "target_benefit": "b", "minimum_check": "c", "search_terms": ["q"], "assumptions": ["a"],
                  "breaks_when": ["w"], "mapping": [{"source_role": "x", "target_role": "y", "relation": "r"}]}
        self.assertEqual("hypothesis", mt.validate_bridge(copy.deepcopy(bridge))["status"])
        bridge["status"] = "source_supported"
        with self.assertRaisesRegex(ValueError, "original-source evidence"):
            mt.validate_bridge(bridge)


if __name__ == "__main__":
    unittest.main()
