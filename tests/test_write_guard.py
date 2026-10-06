from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
import cat_flow as flow


def work():
    return {
        'schema': 'cat-work/v1',
        'id': 'demo.guard.work',
        'entry': 'issue',
        'mode': 'implementation',
        'flow': 'specification',
        'work_kind': 'specification',
        'parent': '',
        'depends_on': [],
        'issue_ref': 'issue',
        'project_entry_ref': 'entry',
        'normative': [{'uri': 'spec'}],
        'evidence': [{'uri': 'evidence'}],
        'specification': {'status': 'candidate', 'decision_ref': None, 'artifact_refs': []},
        'scope': {'process_ids': ['demo.process'], 'changed_ids': [], 'preserved_ids': []},
        'technologies': [],
        'repositories': [],
        'checks': [],
        'gates': [],
    }


class WriteGuardTest(unittest.TestCase):
    def test_workspace_guard_allows_owned_path_and_rejects_other_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            w = work()
            wp = root / 'work.json'
            wp.write_bytes(flow.json_bytes(w))
            (root / 'Lifecycle' / 'CAT' / 'Draft').mkdir(parents=True)

            self.assertEqual(flow.guard_work(wp, w, 'spec', 'start')['status'], 'passed')
            (root / 'Lifecycle' / 'CAT' / 'Draft' / 'demo.md').write_text('draft', encoding='utf-8')
            self.assertEqual(flow.guard_work(wp, w, 'spec', 'finish')['status'], 'passed')

            self.assertEqual(flow.guard_work(wp, w, 'spec', 'start')['status'], 'passed')
            (root / 'unrelated.txt').write_text('forbidden', encoding='utf-8')
            result = flow.guard_work(wp, w, 'spec', 'finish')
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue(any('unrelated.txt' in item.get('paths', []) for item in result['violations']))


if __name__ == '__main__':
    unittest.main()
