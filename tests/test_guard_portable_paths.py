"""Cross-platform guard path assertions."""
import fnmatch
import sys
import unittest
from pathlib import Path, PureWindowsPath, PurePosixPath
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
import cat_flow as flow

class PortableGuardPathTest(unittest.TestCase):
    def test_windows_relative_name(self):
        p = PureWindowsPath('Lifecycle', 'CAT', 'Draft', 'demo.md')
        self.assertEqual(flow._guard_relative_name(p), 'Lifecycle/CAT/Draft/demo.md')
