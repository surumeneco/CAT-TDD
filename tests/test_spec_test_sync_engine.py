"""Direct regression checks for the independent spec-test-sync file boundary."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
from cat_suite_manifest import create_plan, synchronize, verify_plan, checked_path
from cat_spec_test_sync import run_tests

HASHES = {
    "source_sha256": "a" * 64, "model_sha256": "b" * 64,
    "vectors_sha256": "c" * 64, "selection_rule": "rule-witness/v1",
    "renderer_version": "vitest/v1", "binding_version": "binding/v1",
}
MANIFEST = ".cat-flow/manifest.json"

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

