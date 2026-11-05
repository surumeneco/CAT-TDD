"""Cross-platform guard path assertions."""
import fnmatch
import sys
import unittest
from pathlib import Path, PureWindowsPath, PurePosixPath
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
import cat_flow as flow

class PortableGuardPathTest(unittest.TestCase):
    pass
