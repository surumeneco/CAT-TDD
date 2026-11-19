"""CAT-AUD-R01: execute the canonical final Process Closure CLI.

These are strictly synthetic Confirmed-looking Source fixtures. A successful
fixture Gate demonstrates only the currently specified finite local coverage
contract, not author approval for any product or global reachability.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / ".cat-system" / "scripts")]

from test_cat_compile_readable import fm, write_v2
from test_conformance_runtime import base_work


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_confirmed(path):
    """Label isolated test input only; not an authority decision or promotion."""
    source = path.read_text(encoding="utf-8")
    assert source.count("status: draft") == 1
    assert source.count("decision_ref: ''") == 1
    path.write_text(source.replace("status: draft", "status: confirmed")
                    .replace("decision_ref: ''", "decision_ref: synthetic-test-only"),
                    encoding="utf-8")


class R01FinalClosureGateTests(unittest.TestCase):
    def fixture(self, root, unverified_rule=False):
        process, pi, tce = write_v2(root, False)
        for path in (process, pi, tce):
            synthetic_confirmed(path)
        original = process.read_text(encoding="utf-8")
        self.assertEqual(original.count("| state.ready | boolean |"), 1)
        process.write_text(
            original.replace("| state.ready | boolean |",
                             "| state.ready | boolean |\n| state.unused | boolean |"),
            encoding="utf-8")

        work = base_work()
        work["id"] = ("cat-aud-r01-unverified-rule" if unverified_rule
                      else "cat-aud-r01-unused-state")
        work["compilation"] = {
            "schema": "cat-compile/v2",
            "process": "Process.md",
            "pi": "PI.md",
            "tce": "TCE.md",
            "allow_draft": False,
            "allow_partial": True,
        }
        sources = [process, pi, tce]
        if unverified_rule:
            rule = root / "CommonRule.md"
            rule.write_text(
                fm("common-rule", "demo.process.rule", ["demo.process.contract"],
                   language="en")
                + """
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| demo.unproved-rule | submit | Preserve the audit trail | static contract |
""", encoding="utf-8")
            synthetic_confirmed(rule)
            work["compilation"]["common_rules"] = ["CommonRule.md"]
            sources.append(rule)
        work_path = root / "Work.json"
        work_path.write_text(json.dumps(work, ensure_ascii=False), encoding="utf-8")
        return work_path, sources

    def run_final_gate(self, root, with_rule):
        work_path, sources = self.fixture(root, unverified_rule=with_rule)
        argv = [
            sys.executable,
            str(ROOT / ".cat-system" / "scripts" / "cat_flow.py"),
            "conformance", "--work", str(work_path),
            "--kind", "process-closure",
        ]
        run = subprocess.run(argv, text=True, capture_output=True,
                             check=False, timeout=75)
        self.assertEqual(run.returncode, 0,
                         {"argv": argv, "stdout": run.stdout, "stderr": run.stderr})
        gate = json.loads(run.stdout)
        model_path = root / ".cat-flow" / "cache" / "process-closure.model.json"
        evidence_path = root / ".cat-flow" / "conformance" / "process-closure.json"
        self.assertTrue(model_path.is_file())
        self.assertTrue(evidence_path.is_file())
        model = json.loads(model_path.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(evidence["verdict"], gate["status"])
        self.assertEqual(evidence["reason"], gate["reason"])
        self.assertEqual(evidence["input_sha256"]["process"]["sha256"], sha256(sources[0]))
        self.assertEqual(evidence["input_sha256"]["pi"]["sha256"], sha256(sources[1]))
        self.assertEqual(evidence["input_sha256"]["tce:1"]["sha256"], sha256(sources[2]))
        self.assertIn("state.unused", model["source_semantic_map"]["process"]["state"])
        self.assertIn("no-general-reachability-proof", model["limits"])
        self.assertIn("finite-guard-closure-only", model["limits"])
        self.assertEqual(model["coverage_checks"]["submit"]["result"], "proved")
        self.assertEqual(model["coverage_requirement"], "closed")
        print("CAT-AUD-R01-FINAL-GATE " + json.dumps({
            "case": "unverified-rule" if with_rule else "unused-state-no-rule",
            "argv": ["python", ".cat-system/scripts/cat_flow.py", "conformance",
                     "--work", "<isolated>/Work.json", "--kind", "process-closure"],
            "exit_code": run.returncode,
            "source_sha256": {p.name: sha256(p) for p in sources},
            "gate_status": gate["status"],
            "gate_reason": gate["reason"],
            "gate_receipt_sha256": sha256(evidence_path),
            "model_sha256": sha256(model_path),
            "model_status": model["status"],
            "model_limits": model["limits"],
            "coverage_proof_scope": model["coverage_checks"]["submit"].get("proof_scope"),
            "coverage_proof_method": model["coverage_checks"]["submit"].get("proof_method"),
            "unverified_rule_ids": model["unverified_rule_ids"],
        }, ensure_ascii=False, sort_keys=True), flush=True)
        return gate, model, evidence

    def test_unused_state_rule_free_confirmed_final_gate_is_locally_passed(self):
        with tempfile.TemporaryDirectory() as td:
            gate, model, evidence = self.run_final_gate(Path(td), with_rule=False)
            self.assertEqual(gate["status"], "passed", gate)
            self.assertEqual(model["status"], "confirmed")
            self.assertEqual(model["unverified_rule_ids"], [])
            self.assertIn("finite closed-world coverage", gate["reason"])
            self.assertNotIn("least fixed point", gate["reason"].lower())
            self.assertNotIn("global reachability", gate["reason"].lower())

    def test_same_unused_state_with_unverified_normative_rule_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as td:
            gate, model, evidence = self.run_final_gate(Path(td), with_rule=True)
            self.assertEqual(gate["status"], "inconclusive", gate)
            self.assertEqual(model["status"], "draft")
            self.assertEqual(model["unverified_rule_ids"], ["demo.unproved-rule"])
            self.assertIn("unverified", gate["reason"])
            self.assertEqual(
                evidence["input_sha256"]["common_rule:1"]["sha256"],
                sha256(Path(td) / "CommonRule.md"))


if __name__ == "__main__":
    unittest.main()
