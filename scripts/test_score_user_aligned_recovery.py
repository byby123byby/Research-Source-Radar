#!/usr/bin/env python3

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import score_user_aligned_recovery as scorer


class HiddenLeadCompletenessTests(unittest.TestCase):
    def manifest(self):
        return {
            "trials": [
                {
                    "trial_id": "baseline-1",
                    "task_id": "TASK-1",
                    "condition": "baseline",
                    "repetition": 1,
                },
                {
                    "trial_id": "skill-1",
                    "task_id": "TASK-1",
                    "condition": "skill",
                    "repetition": 1,
                },
            ]
        }

    @staticmethod
    def write_response(root: Path, trial_id: str, task_id: str, condition: str, status: str):
        (root / f"{trial_id}.json").write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "condition": condition,
                    "execution": {"status": status},
                }
            ),
            encoding="utf-8",
        )

    def test_complete_pair_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_response(root, "baseline-1", "TASK-1", "baseline", "completed")
            self.write_response(root, "skill-1", "TASK-1", "skill", "completed")
            self.assertEqual([], scorer.validate_complete_pairs(self.manifest(), root))

    def test_missing_or_failed_response_blocks_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_response(root, "baseline-1", "TASK-1", "baseline", "failed")
            errors = scorer.validate_complete_pairs(self.manifest(), root)
            self.assertTrue(any("expected 'completed'" in item for item in errors))
            self.assertTrue(any("response is missing" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
