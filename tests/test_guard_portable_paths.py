"""Cross-platform guard path assertions."""
import fnmatch
import sys
import unittest
import tempfile
from pathlib import Path, PureWindowsPath, PurePosixPath
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
import cat_flow as flow

class PortableGuardPathTest(unittest.TestCase):
    def test_windows_relative_name(self):
        p = PureWindowsPath('Lifecycle', 'CAT', 'Draft', 'demo.md')
        self.assertEqual(flow._guard_relative_name(p), 'Lifecycle/CAT/Draft/demo.md')

    def test_posix_backslash_is_literal(self):
        p = PurePosixPath('Lifecycle'+chr(92)+'CAT'+chr(92)+'Draft'+chr(92)+'demo.md')
        name = flow._guard_relative_name(p)
        self.assertFalse(fnmatch.fnmatchcase(name, 'Lifecycle/CAT/Draft/**'))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'POSIX filename test')
    def test_literal_backslash_file_is_blocked(self):
        from test_write_guard import work
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            w = work()
            wp = root / 'work.json'
            wp.write_bytes(flow.json_bytes(w))
            (root / 'Lifecycle' / 'CAT' / 'Draft').mkdir(parents=True)
            flow.guard_work(wp, w, 'spec', 'start')
            bad = root / ('Lifecycle' + chr(92) + 'CAT' + chr(92) + 'Draft' + chr(92) + 'bad.md')
            bad.write_text('unauthorized', encoding='utf-8')
            self.assertEqual(flow.guard_work(wp, w, 'spec', 'finish')['status'], 'blocked')
