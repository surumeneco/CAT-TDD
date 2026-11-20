"""Bounded Process Closure proof-scope diagnostics.

These test current conservative proof boundaries. They do not certify whole-
process least-fixed-point reachability or independent external effects.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / ".cat-system" / "scripts")]

from test_cat_compile_readable import write_v2, fm
import cat_compile_v2 as compiler
import cat_model_conformance as validator


class CATAuditProofScopeTests(unittest.TestCase):
    def confirmed_fixture(self, root):
        original = ROOT / "tests" / "fixtures" / "minimal"
        result = []
        for name in ("Process.md", "PI.md", "TCE.md"):
            path = root / name
            text = (original / name).read_text(encoding="utf-8")
            text = text.replace("status: draft", "status: confirmed")
            text = text.replace("decision_ref: ''", "decision_ref: test-only:confirmed")
            path.write_text(text, encoding="utf-8")
            result.append(path)
        return result

    def test_r01_local_guard_coverage_is_not_unproved_rule_discharge(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.confirmed_fixture(root)
            process.write_text(
                process.read_text(encoding="utf-8").replace(
                    "| 状態.準備 | 真偽 |",
                    "| 状態.準備 | 真偽 |\n| 状態.未参照 | 真偽 |"),
                encoding="utf-8")
            baseline = compiler.load(process, pi, tce)
            self.assertEqual(baseline["coverage_checks"]["送信"]["result"], "proved")
            self.assertIn("状態.未参照", baseline["source_semantic_map"]["process"]["state"])
            self.assertIn("no-general-reachability-proof", baseline["limits"])
            # This is a declared State; Guard coverage does not claim it was
            # dynamically reached or necessary to observable behavior.
            rule = root / "Rule.md"
            raw = fm("common-rule", "demo.process.rule", ["demo.process.contract"],
                     language="en")
            raw = raw.replace("status: draft", "status: confirmed")
            raw = raw.replace("decision_ref: ''", "decision_ref: test-only:confirmed")
            rule.write_text(raw + """
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| demo.unproved-rule | 送信 | Must retain an audit trail | static contract |
""", encoding="utf-8")
            model = compiler.load(process, pi, tce, common_rules=[rule], allow_draft=True)
            self.assertEqual(model["coverage_checks"]["送信"]["result"], "proved")
            self.assertEqual(model["unverified_rule_ids"], ["demo.unproved-rule"])
            self.assertEqual(model["status"], "draft")
            self.assertIn("no-general-reachability-proof", model["limits"])

    def test_r02_rule_witness_state_values_are_not_a_path_reachability_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.confirmed_fixture(root)
            text = tce.read_text(encoding="utf-8")
            self.assertIn("`入力.有効`", text)
            self.assertIn("`否定(入力.有効)`", text)
            text = text.replace("`入力.有効`", "`状態.準備`")
            text = text.replace("`否定(入力.有効)`", "`否定(状態.準備)`")
            tce.write_text(text, encoding="utf-8")
            model = compiler.load(process, pi, tce)
            self.assertEqual(model["status"], "confirmed")
            self.assertIn("no-general-reachability-proof", model["limits"])
            vectors = compiler.selection_vectors(model)
            self.assertEqual({case["state"]["状態.準備"] for case in vectors["cases"]},
                             {True, False})
            expanded = compiler.expand_cases(model, vectors)
            self.assertEqual(
                {case["initial_state"]["状態.準備"] for case in expanded},
                {True, False})
            # No initial-state or trigger-history witness is included.
            self.assertTrue(all("reachability_proof" not in case for case in expanded))

    def test_r03_changed_effect_semantics_block_independent_model_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.confirmed_fixture(root)
            model = compiler.load(process, pi, tce)
            output = root / "Model.json"
            output.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(validator.validate(process, pi, tce, output)["status"], "passed")
            # The alternative Effect remains type-correct but differs in meaning.
            modified = json.loads(output.read_text(encoding="utf-8"))
            write = modified["rules"][0]["allowed"][0]["write"][0]
            self.assertEqual(write["expr"], {"literal": True})
            write["expr"] = {"literal": False}
            output.write_text(json.dumps(modified, ensure_ascii=False), encoding="utf-8")
            result = validator.validate(process, pi, tce, output)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("effects", result["mismatches"])


if __name__ == "__main__":
    unittest.main()
