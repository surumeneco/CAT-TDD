"""Candidate guard regression for control characters in suite-plan paths.

This test protects planning metadata only. No CAT semantic Gate is claimed.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
from cat_suite_plan_candidate import plan_suite

S, M, V, H = "a" * 64, "b" * 64, "c" * 64, "1" * 64


def entry(path="generated-tests/vector.py"):
    return {"test_id": "v-001", "model_ref": "model#01",
            "vector_ref": "v-001", "path": path, "content_sha256": H}


def owned():
    return {"test_id": "v-001", "owner": "generated", "file_sha256": H,
            "source_sha256": S, "model_sha256": M, "vectors_sha256": V,
            "renderer_version": "python-v1", "binding_version": "pytest-v1"}


def plan(*, desired=None, disk=None, manifest=None, prefix="generated-tests/"):
    return plan_suite(source_sha256=S, model_sha256=M, vectors_sha256=V,
                      selection_rule="all/v1", renderer_version="python-v1",
                      binding_version="pytest-v1", repo_revision="example-sha",
                      allowed_prefix=prefix, desired=[] if desired is None else desired,
                      disk_hashes={} if disk is None else disk,
                      manifest={} if manifest is None else manifest)


class CandidateControlPathBoundary(unittest.TestCase):
    def test_control_characters_in_generated_paths_fail_closed(self):
        for char in ("\t", "\x01", "\x1b", "\x1f", "\x7f"):
            with self.subTest(character=ord(char)), self.assertRaises(ValueError):
                plan(desired=[entry("generated-tests/a" + char + "b.py")])

    def test_control_characters_in_disk_paths_fail_closed(self):
        with self.assertRaises(ValueError):
            plan(disk={"generated-tests/record\x1f.py": H})

    def test_control_characters_in_manifest_paths_fail_closed(self):
        with self.assertRaises(ValueError):
            plan(manifest={"generated-tests/record\x7f.py": owned()})

    def test_control_characters_in_prefix_fail_even_for_empty_plan(self):
        for prefix in ("generated\t-tests/", "generated-tests/escape\x1b/"):
            with self.subTest(prefix=repr(prefix)), self.assertRaises(ValueError):
                plan(prefix=prefix)

    def test_valid_nested_unicode_and_punctuation_paths_remain_allowed(self):
        result = plan(desired=[entry("generated-tests/日本語/v-01_test.py")])
        self.assertEqual(result["entries"][0]["action"], "create")
        self.assertEqual(result["entries"][0]["path"], "generated-tests/日本語/v-01_test.py")


if __name__ == "__main__":
    unittest.main()
