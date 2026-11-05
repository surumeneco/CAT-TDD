"""Direct regression checks for the independent spec-test-sync file boundary."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
from cat_suite_manifest import create_plan, synchronize, verify_plan, checked_path
from cat_spec_test_sync import run_tests, run_declared_check

HASHES = {
    "source_sha256": "a" * 64, "model_sha256": "b" * 64,
    "vectors_sha256": "c" * 64, "selection_rule": "rule-witness/v1",
    "renderer_version": "vitest/v1", "binding_version": "binding/v1",
}
MANIFEST = ".cat-flow/test-suite-manifest.json"

def make_case(value=b"one", id="v1", path="tests/generated/a.test.ts"):
    return ({"test_id": id, "model_ref": "rule.1", "vector_ref": id,
             "path": path, "content_sha256": hashlib.sha256(value).hexdigest()},
            {path: value})

def plan(root, cases, rendered):
    return create_plan(root, MANIFEST, "tests/generated/", cases, rendered, HASHES, "base")

class SyncEngineTests(unittest.TestCase):
    def test_create_and_idempotent_verify(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case, data = make_case()
            proposal, before = plan(root, [case], data)
            self.assertEqual(proposal["entries"][0]["action"], "create")
            outcome = synchronize(root, MANIFEST, proposal, before, data)
            self.assertEqual(outcome["actions"]["create"], 1)
            self.assertEqual((root / case["path"]).read_bytes(), b"one")
            proposal, before = plan(root, [case], data)
            self.assertEqual(proposal["entries"][0]["action"], "unchanged")
            self.assertEqual(verify_plan(proposal, before)["status"], "test-suite-verified")
            self.assertEqual(synchronize(root, MANIFEST, proposal, before, data)["actions"]["unchanged"], 1)


    def test_regeneration_preserves_handwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case, data = make_case()
            p, old = plan(root, [case], data)
            synchronize(root, MANIFEST, p, old, data)
            handwritten = root / "tests/manual.test.ts"
            handwritten.parent.mkdir(parents=True, exist_ok=True)
            handwritten.write_bytes(b"manual")
            updated, replacement = make_case(b"two")
            p, old = plan(root, [updated], replacement)
            self.assertEqual(p["entries"][0]["action"], "update")
            synchronize(root, MANIFEST, p, old, replacement)
            self.assertEqual((root / updated["path"]).read_bytes(), b"two")
            self.assertEqual(handwritten.read_bytes(), b"manual")

    def test_unowned_file_and_local_modifications_are_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case, data = make_case()
            target = root / case["path"]
            target.parent.mkdir(parents=True)
            target.write_bytes(b"handwritten")
            p, old = plan(root, [case], data)
            self.assertEqual(p["entries"][0]["action"], "blocked")
            with self.assertRaises(ValueError):
                synchronize(root, MANIFEST, p, old, data)
            self.assertEqual(target.read_bytes(), b"handwritten")
            target.unlink()
            p, old = plan(root, [case], data)
            synchronize(root, MANIFEST, p, old, data)
            target.write_bytes(b"local change")
            p, old = plan(root, [case], data)
            self.assertEqual(p["entries"][0]["action"], "blocked")


    def test_preflight_blocks_all_writes_and_retains_old_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, a = make_case()
            second, b = make_case(b"two", "v2", "tests/generated/b.test.ts")
            p, old = plan(root, [first, second], {**a, **b})
            target = root / second["path"]
            target.parent.mkdir(parents=True)
            target.write_bytes(b"external")
            with self.assertRaises(ValueError):
                synchronize(root, MANIFEST, p, old, {**a, **b})
            self.assertFalse((root / first["path"]).exists())
            target.unlink()
            p, old = plan(root, [first], a)
            synchronize(root, MANIFEST, p, old, a)
            p, old = plan(root, [], {})
            self.assertEqual(p["entries"][0]["action"], "retain")
            synchronize(root, MANIFEST, p, old, {})
            self.assertTrue((root / first["path"]).is_file())

    def test_symlinks_and_unsafe_paths_are_blocked(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
            root = Path(folder)
            (root / "tests").mkdir()
            (root / "tests/generated").symlink_to(other, target_is_directory=True)
            case, data = make_case()
            with self.assertRaises(ValueError):
                plan(root, [case], data)
            for path in ("/tmp/x", "../escape", "tests/generated/../bad",
                         "tests/generated/control\x01.ts"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    checked_path(root, path)


    def test_generated_namespace_cannot_target_source_or_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case, body = make_case()
            for prefix in ("src/", "src/generated/", ".cat-flow/evidence/",
                           "production/test/generated/", "tests/../generated/"):
                with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                    create_plan(root, MANIFEST, prefix, [case], body, HASHES, "base")

    def test_new_commit_requires_new_manifest_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case, body = make_case()
            p, old = plan(root, [case], body)
            synchronize(root, MANIFEST, p, old, body)
            newer, old = create_plan(root, MANIFEST, "tests/generated/",
                                     [case], body, HASHES, "new-head")
            with self.assertRaisesRegex(ValueError, "revision"):
                verify_plan(newer, old)
            synchronize(root, MANIFEST, newer, old, body)
            again, old = create_plan(root, MANIFEST, "tests/generated/",
                                     [case], body, HASHES, "new-head")
            self.assertEqual(verify_plan(again, old)["status"], "test-suite-verified")


    def test_runner_rejects_undeclared_commands_and_wrong_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workpath = root / "Work.json"
            workpath.write_text("{}")
            work = {"id": "demo.sync", "flow": "spec-test-sync",
                    "mode": "implementation", "technologies": [],
                    "specification": {"status": "confirmed", "decision_ref": "approved"},
                    "repositories": [{"name": "app", "path": str(root)}], "checks": []}
            with self.assertRaisesRegex(ValueError, "declared JUnit"):
                run_declared_check(workpath, work, root, ["v1"], "untrusted")
            cmd = [sys.executable, "-c", "pass", "{report}"]
            check = {"id": "test", "stage": "suite-run", "runner": "junit",
                     "cwd": "@repo:app", "test_ids": ["wrong"],
                     "argv": cmd}
            work["checks"] = [check]
            with self.assertRaisesRegex(ValueError, "test IDs"):
                run_declared_check(workpath, work, root, ["v1"], "test")
            check["test_ids"] = ["v1"]
            check["cwd"] = "@work"
            with self.assertRaisesRegex(ValueError, "declared target repository"):
                run_declared_check(workpath, work, root, ["v1"], "test")

    def test_declared_runner_captures_fresh_junit_success_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workpath = root / "Work.json"
            work = {"id": "demo.sync", "flow": "spec-test-sync",
                    "mode": "implementation", "technologies": [],
                    "specification": {"status": "confirmed", "decision_ref": "approved"},
                    "repositories": [{"name": "app", "path": str(root)}], "checks": []}
            def check(xml, code):
                snippet = "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(" + repr(xml) + ");sys.exit(" + str(code) + ")"
                return {"id": "suite", "stage": "suite-run", "runner": "junit",
                        "cwd": "@repo:app", "test_ids": ["v1"],
                        "argv": [sys.executable, "-c", snippet, "{report}"]}
            work["checks"] = [check('<testsuite><testcase name="v1"/></testsuite>', 0)]
            workpath.write_text("{}")
            passed = run_declared_check(workpath, work, root, ["v1"], "suite")
            self.assertEqual(passed["status"], "test-execution-passed")
            self.assertEqual(passed["observed_targets"], {"v1": "passed"})
            work["checks"] = [check('<testsuite><testcase name="v1"><failure/></testcase></testsuite>', 1)]
            failed = run_declared_check(workpath, work, root, ["v1"], "suite")
            self.assertEqual(failed["status"], "test-execution-failed")
            self.assertEqual(failed["observed_targets"], {"v1": "failed"})

    def test_runner_outcomes_are_separate_from_suite_sync(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            passed = run_tests(root, [sys.executable, "-c", "raise SystemExit(0)"], 10)
            failed = run_tests(root, [sys.executable, "-c", "raise SystemExit(1)"], 10)
            missing = run_tests(root, ["not-a-real-command-123456"], 10)
            self.assertEqual(passed["status"], "test-execution-passed")
            self.assertEqual(failed["status"], "test-execution-failed")
            self.assertEqual(missing["status"], "test-execution-not-run")

if __name__ == "__main__":
    unittest.main()
