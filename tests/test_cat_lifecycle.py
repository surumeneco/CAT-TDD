#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cat-system" / "skills" / "cycle-management" / "scripts"))
from cat_lifecycle import Blocked, locate, move


class LifecycleTests(unittest.TestCase):
    def tree(self, root: Path):
        for kind in ("Issues", "Tasks", "Works"):
            for state in ("New", "InProgress", "Blocked", "Completed", "Cancelled"):
                (root / kind / state).mkdir(parents=True, exist_ok=True)

    def test_locate_and_move_preserve_directory_contents(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Lifecycle"; self.tree(root)
            entry = root / "Works" / "New" / "work.demo"; entry.mkdir()
            (entry / "Work.md").write_text("demo", encoding="utf-8")
            self.assertEqual(locate(root, "work", "work.demo")["state"], "New")
            result = move(root, "work", "work.demo", "InProgress", "New")
            self.assertEqual(result["from"], "New")
            self.assertEqual((root / "Works" / "InProgress" / "work.demo" / "Work.md").read_text(), "demo")
            self.assertFalse(entry.exists())

    def test_duplicate_state_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Lifecycle"; self.tree(root)
            (root / "Tasks" / "New" / "task.demo").mkdir()
            (root / "Tasks" / "Blocked" / "task.demo").mkdir()
            with self.assertRaisesRegex(Blocked, "multiple states"):
                locate(root, "task", "task.demo")

    def test_source_mismatch_and_existing_destination_are_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Lifecycle"; self.tree(root)
            (root / "Issues" / "New" / "issue.demo").mkdir()
            with self.assertRaisesRegex(Blocked, "source state mismatch"):
                move(root, "issue", "issue.demo", "InProgress", "Blocked")
            (root / "Issues" / "InProgress" / "issue.demo").mkdir()
            with self.assertRaisesRegex(Blocked, "multiple states"):
                move(root, "issue", "issue.demo", "Completed")


if __name__ == "__main__":
    unittest.main()
