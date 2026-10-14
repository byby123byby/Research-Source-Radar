#!/usr/bin/env python3

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import radar_feedback as radar


class RadarFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.review_index = 0

    def review_feedback(self, labels, reasons, terms=None, candidates=None, confirm=True):
        candidates = candidates or radar.validate_candidates(self.candidates())[:len(labels)]
        terms = terms or [[] for _ in labels]
        lines = []
        for candidate, label, reason, dimensions in zip(candidates, labels, reasons, terms):
            lines.extend([
                f"### {candidate['candidate_id']} · {candidate['title']}",
                f"来源：{candidate['url']}",
                f"来源版本：{candidate['source_version']}",
                f"你的标注：{label}", f"你的理由：{reason}",
                "你的偏好范围：" + ("维度" if dimensions else "当前候选"),
                "你的确认维度：" + "、".join(dimensions),
            ])
        text = "\n".join(lines) + "\n"
        self.review_index += 1
        path = self.root / f"review-{self.review_index}.md"
        path.write_text(text, encoding="utf-8")
        items = radar.extract_review_feedback(text, candidates, project_id="test-project", source_ref={
            "path": str(path), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
        if confirm:
            for item in items:
                item["evidence"]["status"] = "confirmed"
        return items

    def cli(self, *args):
        return subprocess.run([sys.executable, str(Path(radar.__file__).resolve()), *args],
                              capture_output=True, encoding="utf-8", check=False,
                              env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"})

    def profile(self):
        return radar.make_profile(
            "ExampleProject",
            "发现能推动独立 iOS 无障碍 Agent 的研究机会",
            ["非越狱", "中文输出"],
            "test-project",
        )

    def candidates(self):
        return {
            "schema_version": 1,
            "candidates": [
                {
                    "candidate_id": "C001",
                    "title": "Graph Memory Example",
                    "url": "https://github.com/example/graph-memory",
                    "tier": "priority_now",
                    "summary": "带时间证据的图记忆。",
                    "why_now": "可改进 App 位置记忆和纠错。",
                    "mechanism_tags": ["时间记忆", "可审计"],
                    "trend_note": "近期有独立技术讨论。",
                    "source_version": "v1.0.0",
                    "verified_at": "2020-01-01T00:00:00+00:00",
                },
                {
                    "candidate_id": "C002",
                    "title": "Browser Example",
                    "url": "https://github.com/example/browser",
                    "tier": "cross_domain",
                    "summary": "网页技能复用。",
                    "why_now": "可启发 Safari 辅助流程。",
                    "mechanism_tags": ["技能编译"],
                    "trend_note": "",
                    "source_version": "v1.0.0",
                    "verified_at": "2020-01-01T00:00:00+00:00",
                },
            ],
        }

    def feedback(self):
        return {
            "schema_version": 1,
            "feedback": self.review_feedback(
                ["worth_deepening", "avoid_similar"],
                ["时间记忆和可审计能改变记忆架构。", "不想再推荐浏览器自动化路线。"],
                [["时间记忆", "可审计"], ["浏览器自动化"]]),
        }

    def test_profile_feedback_and_guidance_are_visible_and_explicit(self):
        updated = radar.merge_feedback(self.profile(), radar.validate_feedback_batch(self.feedback()))
        self.assertEqual(["时间记忆", "可审计"], updated["derived_guidance"]["approved_tags"])
        self.assertEqual(["浏览器自动化"], updated["derived_guidance"]["avoid_tags"])
        self.assertTrue(any("至少 20%" in item for item in updated["derived_guidance"]["next_run_guidance"]))
        self.assertEqual(2, len(updated["feedback"]))
        self.assertEqual([], radar.validate_profile(updated)["derived_guidance"]["approved_tags"][:0])

    def test_profiles_are_isolated_between_projects(self):
        supervision = radar.merge_feedback(self.profile(), radar.validate_feedback_batch(self.feedback()))
        finance = radar.make_profile(
            "Factor Research",
            "发现股票因子研究的可复现实证方法",
            ["金融数据", "研究可复现"],
        )
        self.assertEqual(2, len(supervision["feedback"]))
        self.assertEqual([], finance["feedback"])
        self.assertEqual([], finance["derived_guidance"]["approved_tags"])
        self.assertNotEqual(supervision["project"]["name"], finance["project"]["name"])

    def test_feedback_rejects_duplicate_candidate_and_unknown_label(self):
        profile = radar.merge_feedback(self.profile(), radar.validate_feedback_batch(self.feedback()))
        with self.assertRaises(ValueError):
            radar.merge_feedback(profile, radar.validate_feedback_batch({
                "schema_version": 1,
                "feedback": [self.feedback()["feedback"][0]],
            }))
        invalid = self.feedback()
        invalid["feedback"][0]["label"] = "great"
        with self.assertRaises(ValueError):
            radar.validate_feedback_batch(invalid)

    def test_not_useful_now_does_not_blacklist_all_candidate_mechanisms(self):
        feedback = {
            "schema_version": 1,
            "feedback": self.review_feedback(["not_useful_now"], ["当前项目不需要截图优先。"], [["截图优先"]]),
        }
        updated = radar.merge_feedback(self.profile(), radar.validate_feedback_batch(feedback))
        self.assertEqual([], updated["derived_guidance"]["avoid_tags"])
        self.assertIn("C001", [item["candidate_id"] for item in updated["feedback"]])

    def test_candidate_cards_are_chinese_and_show_no_hidden_score(self):
        profile = radar.merge_feedback(self.profile(), radar.validate_feedback_batch(self.feedback()))
        rendered = radar.render_review(profile, radar.validate_candidates(self.candidates()))
        self.assertIn("研究机会评审卡", rendered)
        self.assertIn("优先看", rendered)
        self.assertIn("跨域启发", rendered)
        self.assertIn("你的标注", rendered)
        self.assertIn("自然中文", rendered)
        self.assertNotIn("score=", rendered)

    def test_natural_chinese_review_generates_conservative_proposal(self):
        review = radar.render_review(self.profile(), radar.validate_candidates(self.candidates()))
        review = review.replace("你的标注：`待填写`", "你的标注：`可以借鉴机制`", 1)
        review = review.replace("你的理由：`待填写`", "你的理由：`有明确机制桥接`", 1)
        second = review.find("你的标注：`待填写`")
        review = review[:second] + review[second:].replace("你的标注：`待填写`", "你的标注：`可能有用但不知道是否适配`", 1)
        second_reason = review.find("你的理由：`待填写`")
        review = review[:second_reason] + review[second_reason:].replace("你的理由：`待填写`", "你的理由：`需要先验证`", 1)
        proposal = radar.extract_review_feedback(review, radar.validate_candidates(self.candidates()))
        self.assertEqual("mechanism_to_borrow", proposal[0]["label"])
        self.assertEqual("uncertain", proposal[1]["label"])
        self.assertEqual("可能有用但不知道是否适配", proposal[1]["evidence"]["raw_label"])
        self.assertEqual("需要先验证", proposal[1]["reason"])

    def test_review_reason_can_downgrade_a_weak_positive_label(self):
        review = radar.render_review(self.profile(), radar.validate_candidates(self.candidates()))
        review = review.replace("你的标注：`待填写`", "你的标注：`可以借鉴`", 1)
        review = review.replace("你的理由：`待填写`", "你的理由：`但目前感觉一般般`", 1)
        first_label = review.find("你的标注：`待填写`")
        review = review[:first_label] + review[first_label:].replace("你的标注：`待填写`", "你的标注：`可借鉴机制`", 1)
        first_reason = review.find("你的理由：`待填写`")
        review = review[:first_reason] + review[first_reason:].replace("你的理由：`待填写`", "你的理由：`有稳定机制桥接`", 1)
        proposal = radar.extract_review_feedback(review, radar.validate_candidates(self.candidates()))
        self.assertEqual("uncertain", proposal[0]["label"])
        self.assertEqual("mechanism_to_borrow", proposal[1]["label"])

    def test_explicit_very_average_label_is_not_promoted(self):
        review = radar.render_review(self.profile(), radar.validate_candidates(self.candidates()))
        review = review.replace("你的标注：`待填写`", "你的标注：`感觉很一般`", 1)
        review = review.replace("你的理由：`待填写`", "你的理由：`当前没有明确价值`", 1)
        first_label = review.find("你的标注：`待填写`")
        review = review[:first_label] + review[first_label:].replace("你的标注：`待填写`", "你的标注：`可借鉴机制`", 1)
        first_reason = review.find("你的理由：`待填写`")
        review = review[:first_reason] + review[first_reason:].replace("你的理由：`待填写`", "你的理由：`直接相关`", 1)
        proposal = radar.extract_review_feedback(review, radar.validate_candidates(self.candidates()))
        self.assertEqual("reference_only", proposal[0]["label"])
        self.assertEqual("mechanism_to_borrow", proposal[1]["label"])

    def test_original_uncertainty_overrides_a_borrow_keyword(self):
        review = radar.render_review(self.profile(), radar.validate_candidates(self.candidates()))
        review = review.replace("你的标注：`待填写`", "你的标注：`可能可以迁移`", 1)
        review = review.replace("你的理由：`待填写`", "你的理由：`还需要验证`", 1)
        first_label = review.find("你的标注：`待填写`")
        review = review[:first_label] + review[first_label:].replace("你的标注：`待填写`", "你的标注：`可借鉴机制`", 1)
        first_reason = review.find("你的理由：`待填写`")
        review = review[:first_reason] + review[first_reason:].replace("你的理由：`待填写`", "你的理由：`直接相关`", 1)
        proposal = radar.extract_review_feedback(review, radar.validate_candidates(self.candidates()))
        self.assertEqual("uncertain", proposal[0]["label"])
        self.assertEqual("mechanism_to_borrow", proposal[1]["label"])

    def test_replacement_archives_misparsed_profile_before_rebuilding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "profile.json"
            archive_path = root / "profile-misparsed.json"
            profile_path.write_text(json.dumps(radar.merge_feedback(self.profile(), radar.validate_feedback_batch(self.feedback())), ensure_ascii=False), encoding="utf-8")
            candidate = radar.validate_candidates(self.candidates())[0]
            candidate.update(candidate_id="C003", title="Corrected Candidate")
            incoming = radar.validate_feedback_batch({
                "schema_version": 1,
                "feedback": self.review_feedback(["mechanism_to_borrow"], ["corrected mapping"], candidates=[candidate]),
            })
            original = radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))
            feedback_path = root / "feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": 1, "feedback": incoming}, ensure_ascii=False), encoding="utf-8")
            radar.command_replace_feedback(type("Args", (), {"profile": str(profile_path), "feedback": str(feedback_path), "archive": str(archive_path), "confirm": True})())
            archived = radar.validate_profile(json.loads(archive_path.read_text(encoding="utf-8")))
            corrected = radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))
            self.assertEqual(original, archived)
            self.assertEqual(["C003"], [item["candidate_id"] for item in corrected["feedback"]])

    def test_refresh_guidance_keeps_raw_feedback_and_removes_legacy_overbroad_penalty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "profile.json"
            profile = radar.merge_feedback(self.profile(), radar.validate_feedback_batch({
                "schema_version": 1,
                "feedback": self.review_feedback(["not_useful_now"], ["当前不需要截图优先。"], [["截图优先"]]),
            }))
            profile["derived_guidance"]["avoid_tags"] = ["截图优先"]
            profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            radar.command_refresh_guidance(type("Args", (), {"profile": str(profile_path)})())
            refreshed = radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))
            self.assertEqual([], refreshed["derived_guidance"]["avoid_tags"])
            self.assertEqual("not_useful_now", refreshed["feedback"][0]["label"])

    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "中文目录"
            root.mkdir()
            profile_path = root / "profile.json"
            candidates_path = root / "candidates.json"
            review_path = root / "review.md"
            candidates_path.write_text(json.dumps(self.candidates(), ensure_ascii=False), encoding="utf-8")
            init = self.cli(
                "init", "--output", str(profile_path), "--project-id", "test-project",
                "--project-name", "ExampleProject", "--description", "中文研究雷达",
            )
            self.assertEqual(0, init.returncode, init.stderr)
            self.assertIn(str(profile_path), init.stdout)
            review = self.cli(
                "render-review", "--profile", str(profile_path), "--candidates", str(candidates_path),
                "--output", str(review_path),
            )
            self.assertEqual(0, review.returncode, review.stderr)
            review_text = review_path.read_text(encoding="utf-8").replace("你的标注：`待填写`", "你的标注：可借鉴机制").replace("你的理由：`待填写`", "你的理由：可审计机制能迁移")
            review_text = review_text.replace("你的偏好范围：`待填写`", "你的偏好范围：维度").replace("你的确认维度：`待填写`", "你的确认维度：可审计")
            review_path.write_text(review_text, encoding="utf-8")
            proposal_path = root / "proposal.json"
            proposal = self.cli(
                "extract-review", "--review", str(review_path), "--candidates", str(candidates_path),
                "--project-id", "test-project", "--output", str(proposal_path),
            )
            self.assertEqual(0, proposal.returncode, proposal.stderr)
            self.assertEqual(2, len(json.loads(proposal_path.read_text(encoding="utf-8"))["feedback"]))
            recorded = self.cli(
                "record-feedback", "--profile", str(profile_path), "--feedback", str(proposal_path), "--confirm",
            )
            self.assertEqual(0, recorded.returncode, recorded.stderr)
            self.assertIn("优先看", review_path.read_text(encoding="utf-8"))
            self.assertEqual(2, len(radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))["feedback"]))
            saved = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(["可审计"], saved["derived_guidance"]["approved_tags"])
            self.assertTrue(all(radar.feedback_issue(item, "test-project") is None for item in saved["feedback"]))
            shown = self.cli("show-guidance", "--profile", str(profile_path))
            self.assertEqual(0, shown.returncode, shown.stdout + shown.stderr)
            self.assertIn("已确认偏好：可审计", shown.stdout)

    def test_cli_argument_errors_preserve_unicode(self):
        result = self.cli("不存在的命令")
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("不存在的命令", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_unquoted_label_is_retained_as_uncertain(self):
        item = self.review_feedback(["说不上来，先观察"], ["图记忆或许有用"], [["图记忆"]])[0]
        self.assertEqual("uncertain", item["label"])
        self.assertEqual("说不上来，先观察", item["evidence"]["raw_label"])
        self.assertIsNone(radar.feedback_issue(item, "test-project"))
        guidance = radar.derive_guidance([item], "test-project")
        self.assertEqual([], guidance["approved_tags"])
        self.assertEqual([], guidance["avoid_tags"])

    def test_reason_without_label_is_not_silently_skipped(self):
        with self.assertRaisesRegex(ValueError, "C001.*缺少标注"):
            self.review_feedback(["待填写"], ["这个有内容的理由必须保留"])

    def test_forged_dimension_confirmation_is_rejected(self):
        item = self.review_feedback(["夯"], ["可审计值得借鉴"])[0]
        item["evidence"].update(scope="dimension", confirmed_terms=["可审计"],
                                dimension_confirmation={"raw_scope": "维度", "raw_terms": "可审计"})
        self.assertEqual("original_dimension_confirmation_mismatch", radar.feedback_issue(item, "test-project"))

    def test_negated_substring_cannot_become_positive_dimension(self):
        for reason, term in [("不是喜欢图记忆，而是可审计有用。", "图记忆"),
                             ("不要截图优先。", "截图"), ("not useful graph memory", "graph memory")]:
            with self.subTest(reason=reason):
                item = self.review_feedback(["夯"], [reason], [[term]])[0]
                self.assertIn("positive_term_negated_or_uncertain", radar.feedback_issue(item, "test-project"))
                self.assertEqual([], radar.derive_guidance([item], "test-project")["approved_tags"])
        good = self.review_feedback(["夯"], ["不是喜欢图记忆，而是可审计有用。"], [["可审计"]])[0]
        self.assertEqual(["可审计"], radar.derive_guidance([good], "test-project")["approved_tags"])

    def test_dimension_needs_original_reason_and_explicit_scope(self):
        item = self.review_feedback(["夯"], ["只有图记忆值得借鉴"], [["可审计"]])[0]
        self.assertEqual("preference_terms_not_grounded_in_user_reason", radar.feedback_issue(item, "test-project"))
        valid = self.review_feedback(["夯"], ["可审计值得借鉴"], [["可审计"]])[0]
        del valid["evidence"]["dimension_confirmation"]
        self.assertEqual("missing_or_mismatched_dimension_confirmation", radar.feedback_issue(valid, "test-project"))
        with self.assertRaisesRegex(ValueError, "偏好范围"):
            radar.review_dimensions({"偏好范围": "随便", "确认维度": "可审计"})
        with self.assertRaises(ValueError):
            radar.review_dimensions({"偏好范围": "当前候选", "确认维度": "可审计"})

    def test_candidate_tags_do_not_expand_without_user_dimensions(self):
        item = self.review_feedback(["夯"], ["整体有用"])[0]
        self.assertEqual("candidate", item["evidence"]["scope"])
        self.assertEqual([], radar.derive_guidance([item], "test-project")["approved_tags"])

    def test_original_evidence_identity_and_hash_tampering_is_rejected(self):
        item = self.feedback()["feedback"][0]
        for field, value in [("project_id", "other"), ("candidate_id", "C999"),
                             ("candidate_title", "Other title"), ("raw_label", "NPC"),
                             ("raw_reason", "伪造理由"), ("verified_at", "invalid")]:
            changed = json.loads(json.dumps(item))
            changed["evidence"][field] = value
            with self.subTest(field=field):
                self.assertIsNotNone(radar.feedback_issue(changed, "test-project"))
        for field, value in [("url", "https://example.com/other"), ("version", "v2.0.0"), ("version", "main")]:
            changed = json.loads(json.dumps(item))
            changed["evidence"]["source_identity"][field] = value
            self.assertIsNotNone(radar.feedback_issue(changed, "test-project"))
        path = Path(item["evidence"]["source_ref"]["path"])
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
        self.assertEqual("original_input_changed", radar.feedback_issue(item, "test-project"))

    def test_duplicate_original_field_and_candidate_are_rejected(self):
        item = self.review_feedback(["夯"], ["可审计有用"])[0]
        original = Path(item["evidence"]["source_ref"]["path"]).read_text(encoding="utf-8")
        for text in [original + "你的标注：NPC\n", original + original]:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    radar.extract_review_feedback(text, radar.validate_candidates(self.candidates()))

    def test_legacy_schema_is_readable_but_never_active_without_evidence(self):
        legacy = {key: value for key, value in self.feedback()["feedback"][0].items() if key != "evidence"}
        parsed = radar.validate_feedback_batch({"schema_version": 1, "feedback": [legacy]})
        self.assertNotIn("evidence", parsed[0])
        self.assertEqual("legacy_or_missing_user_evidence", radar.feedback_issue(parsed[0], "test-project"))
        profile = self.profile()
        profile["feedback"] = [dict(legacy, feedback_id="old-1", created_at=radar.now_iso())]
        del profile["project"]["id"]
        profile["derived_guidance"]["approved_tags"] = ["不可相信的旧缓存"]
        self.assertEqual(profile, radar.validate_profile(profile))
        self.assertEqual([], radar.derive_guidance(profile["feedback"])["approved_tags"])
        with self.assertRaisesRegex(ValueError, "legacy_or_missing_user_evidence"):
            radar.merge_feedback(self.profile(), parsed)

    def test_raw_labels_ordinals_and_old_pinned_sources_are_preserved(self):
        for raw, ordinal in [("夯", 5), ("顶级", 4), ("人上人", 3), ("NPC", 2), ("拉完了", 1)]:
            item = self.review_feedback([raw], ["可审计  机制"])[0]
            self.assertEqual(raw, item["evidence"]["raw_label"])
            self.assertEqual(ordinal, item["evidence"]["ordinal"])
            self.assertEqual("可审计  机制", item["evidence"]["raw_reason"])
            self.assertIsNone(radar.feedback_issue(item, "test-project"))
        candidate = radar.validate_candidates(self.candidates())[0]
        candidate.update(source_version="2011-published-edition", verified_at="2012-01-01T00:00:00Z")
        old = self.review_feedback(["可借鉴机制"], ["可审计有用"], candidates=[candidate])[0]
        self.assertIsNone(radar.feedback_issue(old, "test-project"))

    def test_cli_requires_confirmation_and_rejects_mixed_batch_atomically(self):
        profile_path, batch_path = self.root / "profile.json", self.root / "batch.json"
        before = json.dumps(self.profile(), ensure_ascii=False)
        profile_path.write_text(before, encoding="utf-8")
        batch = self.feedback()
        batch_path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        missing_confirmation = self.cli("record-feedback", "--profile", str(profile_path), "--feedback", str(batch_path))
        self.assertEqual(1, missing_confirmation.returncode)
        self.assertIn("--confirm", missing_confirmation.stdout)
        self.assertIn("不能自动导入旧 proposal", missing_confirmation.stdout)
        self.assertEqual("", missing_confirmation.stderr)
        batch["feedback"][1]["evidence"]["source_identity"]["version"] = "unverified"
        batch_path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        archive = self.root / "archive.json"
        for command, extra in [("record-feedback", []), ("replace-feedback", ["--archive", str(archive)])]:
            result = self.cli(command, "--profile", str(profile_path), "--feedback", str(batch_path), "--confirm", *extra)
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("C002", result.stdout)
            self.assertIn("unpinned_source_version", result.stdout)
            self.assertIn("整批未写入", result.stdout)
            self.assertIn("重新 extract-review", result.stdout)
            self.assertEqual(before, profile_path.read_text(encoding="utf-8"))
            self.assertFalse(archive.exists())


if __name__ == "__main__":
    unittest.main()
