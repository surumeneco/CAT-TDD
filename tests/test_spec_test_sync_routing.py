#!/usr/bin/env python3
"""Contract tests for the adopted spec-test-sync flow (Draft until normative Gate).

These tests intentionally exercise routing/permissions only. They do not claim
that test generation, suite synchronization or a CAT semantic Gate has passed.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTING = ROOT / ".cat-system" / "config" / "routing.json"

SYNC_STAGES = (
    "process-closure", "model", "model-conformance", "vectors",
    "suite-plan", "suite-sync", "suite-validate", "suite-run", "suite-result",
)
FORBIDDEN_WRITES = {
    "production-source", "confirmed-spec", "TDD/Queue", "queue",
    "queue-state", "handwritten-test", "TestModels", "test-model",
}
FORBIDDEN_STAGES = {"queue", "tests", "red", "implementation", "green",
                    "queue-state", "implementation-conformance", "integration"}


class SpecTestSyncRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(ROUTING.read_text(encoding="utf-8"))

    def test_fifth_flow_has_independent_order_without_tdd_red(self):
        flows = self.catalog["flows"]
        self.assertEqual(
            list(flows["spec-test-sync"]["stages"]), list(SYNC_STAGES))
        self.assertEqual(flows["spec-test-sync"]["entries"], ["confirmed-spec"])
        self.assertTrue(FORBIDDEN_STAGES.isdisjoint(SYNC_STAGES))
        self.assertIn("red", flows["spec-implementation"]["stages"])
        self.assertIn("queue-state", flows["spec-implementation"]["stages"])

    def test_issue_test_maintenance_handoffs_without_changing_existing_kinds(self):
        handoffs = self.catalog["flows"]["issue-work"]["handoff_by_work_kind"]
        self.assertEqual(handoffs["test-maintenance"], "spec-test-sync")
        self.assertEqual(handoffs["implementation"], "spec-implementation")
        self.assertEqual(handoffs["specification"], "issue-work")
        for kind in ("analysis", "documentation", "verification"):
            self.assertEqual(handoffs[kind], "complete-in-flow")

    def test_sync_stages_are_deterministic_and_cannot_modify_production(self):
        stages = self.catalog["stages"]
        for name in SYNC_STAGES[4:]:
            with self.subTest(stage=name):
                stage = stages[name]
                self.assertIn(stage["executor"]["type"],
                              {"script", "compiler", "validator", "runner"})
                permissions = stage["permissions"]
                self.assertFalse(
                    FORBIDDEN_WRITES.intersection(permissions["write"]))
                self.assertIn("production-source", permissions["prohibited"])
                self.assertIn("confirmed-spec", permissions["prohibited"])
                self.assertFalse(stage.get("conditional", {}).get("passed"))
                self.assertEqual(
                    stage["evidence_policy"]["execution_evidence_owner"],
                    "executor")
                self.assertFalse(
                    stage["evidence_policy"]["agent_may_edit_execution_evidence"])

    def test_suite_sync_owns_only_generated_tests_and_manifest(self):
        stage = self.catalog["stages"]["suite-sync"]
        writes = set(stage["permissions"]["write"])
        self.assertEqual(writes, {"generated-test-suite", "TestSuiteManifest"})
        for protected in ("handwritten-test", "production-source",
                          "TDD/Queue", "confirmed-spec"):
            self.assertIn(protected, stage["permissions"]["prohibited"])


if __name__ == "__main__":
    unittest.main()
