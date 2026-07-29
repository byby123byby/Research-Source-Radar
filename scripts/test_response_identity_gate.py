#!/usr/bin/env python3

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import response_identity_gate as gate


def source(title: str, url: str) -> dict[str, str]:
    return {"rank": 1, "title": title, "url": url, "source_type": "preprint"}


class ResponseIdentityGateTests(unittest.TestCase):
    def test_display_title_accepts_normal_source_variants(self):
        self.assertTrue(
            gate.display_title_matches(
                "Lightweight LLM Agent Memory with Small Language Models (ExampleMem)",
                "Lightweight LLM Agent Memory with Small Language Models",
                "arxiv",
            )
        )
        self.assertTrue(
            gate.display_title_matches(
                "Safari Web Extensions",
                "Safari web extensions | Apple Developer Documentation",
                "official_url",
            )
        )
        self.assertTrue(
            gate.display_title_matches(
                "A Self-Report Measure of Engagement With Digital Behavior Change Interventions: Development and Psychometric Evaluation of the DBCI Engagement Scale",
                "A self-report measure of engagement with digital behavior change interventions (DBCIs): development and psychometric evaluation of the DBCI Engagement Scale - PMC",
                "official_url",
            )
        )

    def test_display_title_rejects_materially_different_paper_title(self):
        self.assertFalse(
            gate.display_title_matches(
                "Cost and Accuracy of Long-Term Graph Memory in Distributed LLM-Based Multi-Agent Systems",
                "Cost and Accuracy of Long-Term Memory in Distributed Multi-Agent Systems Based on Large Language Models",
                "arxiv",
            )
        )

    def test_identity_for_url_extracts_supported_locators(self):
        self.assertEqual(
            {"kind": "arxiv", "value": "2601.02553"},
            gate.identity_for_url("https://arxiv.org/abs/2601.02553"),
        )
        self.assertEqual(
            {"kind": "github", "value": "owner/repository"},
            gate.identity_for_url("https://github.com/owner/repository"),
        )
        self.assertEqual(
            {"kind": "official_url", "value": "https://www.w3.org/TR/prov-o/"},
            gate.identity_for_url("https://www.w3.org/TR/prov-o/"),
        )
        self.assertEqual(
            {"kind": "pmid", "value": "21393123"},
            gate.identity_for_url("https://pubmed.ncbi.nlm.nih.gov/21393123/"),
        )

    def test_official_page_without_title_metadata_is_unresolved(self):
        item = source("A Specific Paper Title", "https://example.org/paper")
        verified = {
            "status": "verified",
            "resolved_title": "example.org",
            "canonical_id": "url:https://example.org/paper",
        }
        with mock.patch.object(gate.contract, "verify_candidate_source", return_value=verified):
            result = gate.verify_source(item, 1.0)
        self.assertEqual("unresolved", result["status"])
        self.assertIn("no usable title metadata", result["reason"])

    def test_gate_removes_failed_candidates_and_renumbers_primary(self):
        payload = {
            "summary": "fixture",
            "sources": [
                source("kept", "https://arxiv.org/abs/2601.02553"),
                source("removed", "https://arxiv.org/abs/2601.02554"),
            ],
            "gaps": [],
            "discovery_trace": {},
        }

        def fake_verify(item, timeout):
            return {
                "status": "verified" if "kept" in item["title"] else "failed",
                "reason": "fixture mismatch",
                "title": item["title"],
                "url": item["url"],
            }

        with mock.patch.object(gate, "verify_source", side_effect=fake_verify):
            filtered, report = gate.gate(copy.deepcopy(payload), 1.0)

        self.assertEqual(1, len(filtered["sources"]))
        self.assertEqual(1, filtered["sources"][0]["rank"])
        self.assertEqual(2, report["sources_checked"])
        self.assertEqual(1, report["sources_kept"])
        self.assertEqual("filtered", report["status"])
        self.assertTrue(any("identity_gate_removed" in gap for gap in filtered["gaps"]))


if __name__ == "__main__":
    unittest.main()
