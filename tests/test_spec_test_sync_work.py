#!/usr/bin/env python3
"""Adversarial Work-boundary tests for the adopted spec-test-sync flow."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
import cat_flow


def confirmed_test_work():
    return {
        "schema": "cat-work/v1",
        "id": "demo.test.sync",
        "entry": "confirmed-spec",
        "mode": "implementation",
        "flow": "spec-test-sync",
        "work_kind": "test-maintenance",
        "issue_ref": "issue:42",
        "project_entry_ref": "https://example.org/project",
        "normative": [{"uri": "https://example.org/confirmed"}],
        "evidence": [{"uri": "https://example.org/source"}],
        "specification": {
            "status": "confirmed",
            "decision_ref": "https://example.org/decision/42",
            "artifact_refs": [],
        },
        "scope": {
            "process_ids": ["demo.test"],
            "changed_ids": ["demo.test.vector"],
            "preserved_ids": [],
        },
        "technologies": ["Python", "pytest"],
        "repositories": [],
        "checks": [],
        "gates": [],
    }


class SpecTestSyncWorkTests(unittest.TestCase):
    def test_confirmed_test_maintenance_work_is_valid(self):
        work = confirmed_test_work()
        self.assertEqual(cat_flow.validate(work), [])
        self.assertEqual(cat_flow.infer_flow(work), "spec-test-sync")

    def test_suite_sync_route_is_usable_without_tdd_queue(self):
        work = confirmed_test_work()
        with tempfile.TemporaryDirectory() as d:
            workpath = Path(d) / "Work.json"
            workpath.write_bytes(cat_flow.json_bytes(work))
            result = cat_flow.route(work, "suite-sync")
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["flow"], "spec-test-sync")
            self.assertFalse(result["guard_required"])
            self.assertNotIn("production-source", result["permissions"]["write"])
            self.assertIn("production-source", result["permissions"]["prohibited"])

    def test_red_and_implementation_are_not_stages_in_sync_flow(self):
        work = confirmed_test_work()
        for stage in ("red", "implementation", "green", "queue-state"):
            with self.subTest(stage=stage):
                result = cat_flow.route(work, stage)
                self.assertNotEqual(result["status"], "ready")


    def test_vector_handoff_uses_suite_plan_and_never_tdd_queue(self):
        work = confirmed_test_work()
        r = cat_flow.route(work, "vectors")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["on_result"]["passed"], "suite-plan")
        implementation = dict(work, flow="spec-implementation",
                              work_kind="implementation")
        r = cat_flow.route(implementation, "vectors")
        self.assertEqual(r["on_result"]["passed"], "queue")

    def test_unconfirmed_source_cannot_enable_sync(self):
        work = confirmed_test_work()
        work["specification"]["status"] = "candidate"
        work["specification"]["decision_ref"] = None
        # Validation may accept candidate as a Work record, but normative
        # synchronization must not become executable without confirmation.
        self.assertNotEqual(cat_flow.route(work, "suite-sync")["status"], "ready")


if __name__ == "__main__":
    unittest.main()
