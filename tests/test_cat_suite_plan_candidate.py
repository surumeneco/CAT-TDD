"""Isolated, non-normative suite planning contract tests (TaskQueue TASK-20261102-003)."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
from cat_suite_plan_candidate import plan_suite

S = "a" * 64
M = "b" * 64
V = "c" * 64
H1 = "1" * 64
H2 = "2" * 64


def item(id="vector-01", path="generated-tests/test_vector_01.py", digest=H1):
    return {
        "test_id": id,
        "model_ref": "process.test-model#rule-01",
        "vector_ref": id,
        "path": path,
        "content_sha256": digest,
    }


def manifest_entry(record=None, *, digest=H1, owner="generated", **overrides):
    record = record or item()
    result = {
        "test_id": record["test_id"],
        "owner": owner,
        "file_sha256": digest,
        "source_sha256": S,
        "model_sha256": M,
        "vectors_sha256": V,
        "renderer_version": "python-v1",
        "binding_version": "pytest-v1",
    }
    result.update(overrides)
    return result


def plan(desired=None, disk=None, existing=None, **overrides):
    arguments = dict(
        source_sha256=S,
        model_sha256=M,
        vectors_sha256=V,
        selection_rule="rule-witness/v1",
        renderer_version="python-v1",
        binding_version="pytest-v1",
        repo_revision="deadbeef",
        allowed_prefix="generated-tests/",
        desired=[item()] if desired is None else desired,
        disk_hashes={} if disk is None else disk,
        manifest={} if existing is None else existing,
    )
    arguments.update(overrides)
    return plan_suite(**arguments)


class TestSuitePlanCandidate(unittest.TestCase):
    def test_empty_owned_namespace_creates_no_files_or_tdd_queue(self):
        result = plan()
        self.assertEqual(result["entries"][0]["action"], "create")
        self.assertEqual(result["entries"][0]["test_id"], "vector-01")
        self.assertNotIn("queue", result)
        self.assertNotIn("execution_status", result)

    def test_matching_owned_generated_test_is_unchanged(self):
        result = plan(disk={item()["path"]: H1}, existing={item()["path"]: manifest_entry()})
        self.assertEqual(result["entries"][0]["action"], "unchanged")
        self.assertEqual(result, plan(disk={item()["path"]: H1}, existing={item()["path"]: manifest_entry()}))

    def test_owned_hash_change_proposes_update_without_touching_disk(self):
        desired = item(digest=H2)
        disk = {desired["path"]: H1}
        existing = {desired["path"]: manifest_entry()}
        snapshot = copy.deepcopy((desired, disk, existing))
        result = plan(desired=[desired], disk=disk, existing=existing)
        self.assertEqual(result["entries"][0]["action"], "update")
        self.assertEqual((desired, disk, existing), snapshot)

    def test_unowned_path_cannot_be_replaced_even_if_hash_matches(self):
        target = item()
        for known in ({}, {target["path"]: manifest_entry(owner="handwritten")}):
            with self.subTest(manifest=known):
                result = plan(disk={target["path"]: H1}, existing=known)
                self.assertEqual(result["entries"][0]["action"], "blocked")

    def test_modified_owned_file_and_missing_owned_file_are_blocked(self):
        target = item()
        existing = {target["path"]: manifest_entry()}
        for disk in ({target["path"]: H2}, {}):
            with self.subTest(disk=disk):
                self.assertEqual(plan(disk=disk, existing=existing)["entries"][0]["action"], "blocked")

    def test_stale_generated_unselected_files_are_retained_not_deleted(self):
        obsolete = "generated-tests/older.py"
        old = item(id="old", path=obsolete)
        manifest = {obsolete: manifest_entry(old)}
        result = plan(desired=[], disk={obsolete: H1}, existing=manifest)
        self.assertEqual([(x["path"], x["action"]) for x in result["entries"]],
                         [(obsolete, "retain")])

    def test_duplicate_test_ids_paths_and_oracle_fields_fail_closed(self):
        with self.assertRaises(ValueError):
            plan(desired=[item(), item(path="generated-tests/another.py")])
        with self.assertRaises(ValueError):
            plan(desired=[item(), item(id="vector-02")])
        with self.assertRaises(ValueError):
            plan(desired=[dict(item(), oracle="pretend rule")])

    def test_absolute_parent_and_backslash_paths_fail_closed(self):
        for path in ("/tmp/test.py", "generated-tests/../src/main.py",
                     "generated-tests\\unsafe.py", "src/test.py", "generated-tests//bad.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                plan(desired=[item(path=path)])

    def test_invalid_hash_and_ambiguous_manifest_owner_fail_closed(self):
        with self.assertRaises(ValueError):
            plan(source_sha256="not-a-hash")
        with self.assertRaises(ValueError):
            plan(disk={item()["path"]: "xx"})
        with self.assertRaises(ValueError):
            plan(existing={item()["path"]: manifest_entry(owner="?", digest=H1)})

    def test_sorted_results_independent_of_input_order(self):
        first = item(id="first", path="generated-tests/a.py")
        last = item(id="last", path="generated-tests/z.py", digest=H2)
        a = plan(desired=[last, first])
        b = plan(desired=[first, last])
        self.assertEqual(a, b)
        self.assertEqual([x["path"] for x in a["entries"]], [first["path"], last["path"]])


if __name__ == "__main__":
    unittest.main()
