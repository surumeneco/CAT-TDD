from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("git"), "Git CLI is required")
class NumberedRoomLayoutTest(unittest.TestCase):
    def git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True, text=True, check=True,
        )

    def test_parent_git_ignores_numbered_rooms_not_literal_room_n(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            self.git(root, "init", "-q")
            for room in ("Room0", "Room1", "Room2", "Room10", "Room999"):
                path = f"{room}/repo-a/source.py"
                result = self.git(root, "check-ignore", path)
                self.assertEqual(result.stdout.strip(), path)
            result = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "RoomN/repo-a/source.py"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)

    def test_each_numbered_room_can_host_worktrees_of_multiple_repositories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for repo in ("repo-a", "repo-b"):
                origin = root / "Room0" / repo
                origin.mkdir(parents=True)
                self.git(origin, "init", "-q")
                self.git(origin, "config", "user.name", "CAT-TDD Test")
                self.git(origin, "config", "user.email", "test@example.invalid")
                (origin / "source.txt").write_text(repo, encoding="utf-8")
                self.git(origin, "add", "source.txt")
                self.git(origin, "commit", "-qm", "initial")
                for number in (1, 2):
                    target = root / f"Room{number}" / repo
                    target.parent.mkdir(exist_ok=True)
                    self.git(origin, "worktree", "add", "-q", "-b", f"room{number}", str(target))
                    self.assertTrue((target / ".git").is_file())
                    self.assertEqual(self.git(target, "branch", "--show-current").stdout.strip(),
                                     f"room{number}")
                entries = self.git(origin, "worktree", "list", "--porcelain").stdout
                self.assertIn(str(root / "Room1" / repo), entries)
                self.assertIn(str(root / "Room2" / repo), entries)


if __name__ == "__main__":
    unittest.main()
