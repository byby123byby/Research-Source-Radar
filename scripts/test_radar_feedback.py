#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import radar_feedback as radar


class RadarFeedbackTests(unittest.TestCase):
    def profile(self):
        return radar.make_profile(
            "SuperVision",
            "发现能推动独立 iOS 无障碍 Agent 的研究机会",
            ["非越狱", "中文输出"],
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
                },
            ],
        }

    def feedback(self):
        return {
            "schema_version": 1,
            "feedback": [
                {
                    "candidate_id": "C001",
                    "title": "Graph Memory Example",
                    "label": "worth_deepening",
                    "reason": "能改变记忆架构。",
                    "tags": ["时间记忆", "可审计"],
                },
                {
                    "candidate_id": "C002",
                    "title": "Browser Example",
                    "label": "avoid_similar",
                    "reason": "当前不需要浏览器路线。",
                    "tags": ["浏览器自动化"],
                },
            ],
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
            "feedback": [{
                "candidate_id": "C001",
                "title": "Graph Memory Example",
                "label": "not_useful_now",
                "reason": "当前项目不需要这个实现。",
                "tags": ["图记忆", "截图优先"],
            }],
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
        self.assertIn("原始标注", proposal[1]["reason"])

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
        self.assertEqual("not_useful_now", proposal[0]["label"])
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
            incoming = radar.validate_feedback_batch({
                "schema_version": 1,
                "feedback": [{
                    "candidate_id": "C003",
                    "title": "Corrected Candidate",
                    "label": "mechanism_to_borrow",
                    "reason": "corrected mapping",
                    "tags": ["revision"],
                }],
            })
            original = radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))
            feedback_path = root / "feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": 1, "feedback": incoming}, ensure_ascii=False), encoding="utf-8")
            radar.command_replace_feedback(type("Args", (), {"profile": str(profile_path), "feedback": str(feedback_path), "archive": str(archive_path)})())
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
                "feedback": [{
                    "candidate_id": "C001",
                    "title": "Graph Memory Example",
                    "label": "not_useful_now",
                    "reason": "当前不需要。",
                    "tags": ["截图优先"],
                }],
            }))
            profile["derived_guidance"]["avoid_tags"] = ["截图优先"]
            profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            radar.command_refresh_guidance(type("Args", (), {"profile": str(profile_path)})())
            refreshed = radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))
            self.assertEqual([], refreshed["derived_guidance"]["avoid_tags"])
            self.assertEqual("not_useful_now", refreshed["feedback"][0]["label"])

    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "profile.json"
            candidates_path = root / "candidates.json"
            feedback_path = root / "feedback.json"
            review_path = root / "review.md"
            candidates_path.write_text(json.dumps(self.candidates(), ensure_ascii=False), encoding="utf-8")
            feedback_path.write_text(json.dumps(self.feedback(), ensure_ascii=False), encoding="utf-8")
            script = Path(radar.__file__).resolve()
            init = subprocess.run(
                [sys.executable, str(script), "init", "--output", str(profile_path), "--project-name", "SuperVision", "--description", "中文研究雷达"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, init.returncode, init.stderr)
            review = subprocess.run(
                [sys.executable, str(script), "render-review", "--profile", str(profile_path), "--candidates", str(candidates_path), "--output", str(review_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, review.returncode, review.stderr)
            review_text = review_path.read_text(encoding="utf-8").replace("你的标注：`待填写`", "你的标注：`可借鉴机制`").replace("你的理由：`待填写`", "你的理由：`能迁移`")
            review_path.write_text(review_text, encoding="utf-8")
            proposal_path = root / "proposal.json"
            proposal = subprocess.run(
                [sys.executable, str(script), "extract-review", "--review", str(review_path), "--candidates", str(candidates_path), "--output", str(proposal_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, proposal.returncode, proposal.stderr)
            self.assertEqual(2, len(json.loads(proposal_path.read_text(encoding="utf-8"))["feedback"]))
            recorded = subprocess.run(
                [sys.executable, str(script), "record-feedback", "--profile", str(profile_path), "--feedback", str(feedback_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, recorded.returncode, recorded.stderr)
            self.assertIn("优先看", review_path.read_text(encoding="utf-8"))
            self.assertEqual(2, len(radar.validate_profile(json.loads(profile_path.read_text(encoding="utf-8")))["feedback"]))


if __name__ == "__main__":
    unittest.main()
