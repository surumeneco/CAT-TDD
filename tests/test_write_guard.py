from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cat-system' / 'scripts'))
import cat_flow as flow


def work():
    return {
        'schema': 'cat-work/v1',
        'id': 'demo.guard.work',
        'entry': 'issue',
        'mode': 'implementation',
        'flow': 'issue-work',
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
    def test_native_windows_path_normalization_does_not_rewrite_posix_names(self):
        windows = PureWindowsPath(r'Lifecycle\\CAT\\Draft\\demo.md')
        posix_literal = PurePosixPath(r'Lifecycle\\CAT\\Draft\\demo.md')
        self.assertEqual(flow._guard_relative_name(windows), 'Lifecycle/CAT/Draft/demo.md')
        self.assertEqual(flow._guard_relative_name(posix_literal), r'Lifecycle\\CAT\\Draft\\demo.md')

    def test_posix_literal_backslash_filename_is_not_an_allowed_draft_path(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX allows literal backslashes in filenames, Windows does not')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            w = work()
            wp = root / 'work.json'
            wp.write_bytes(flow.json_bytes(w))
            self.assertEqual(flow.guard_work(wp, w, 'spec', 'start')['status'], 'passed')
            (root / r'Lifecycle\\CAT\\Draft\\fake.md').write_text('outside scope', encoding='utf-8')
            result = flow.guard_work(wp, w, 'spec', 'finish')
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue(any(r'Lifecycle\\CAT\\Draft\\fake.md' in item.get('paths', [])
                                for item in result['violations']))

    def test_recheck_preserves_blocked_evidence_and_original_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            w = work()
            wp = root / 'work.json'
            wp.write_bytes(flow.json_bytes(w))
            self.assertEqual(flow.guard_work(wp, w, 'spec', 'start')['status'], 'passed')
            outside = root / 'unrelated.txt'
            outside.write_text('first unauthorized change', encoding='utf-8')
            first = flow.guard_work(wp, w, 'spec', 'finish')
            self.assertEqual(first['status'], 'blocked')
            outside.unlink()
            recovered = flow.guard_work(wp, w, 'spec', 'finish')
            self.assertEqual(recovered['status'], 'passed')
            evidence = flow.read_json(Path(recovered['guard']))
            self.assertEqual(evidence['workspace_state'], {'work.json': flow.sha(wp.read_bytes())})
            self.assertEqual(evidence['finish_history'][0]['verdict'], 'blocked')
            self.assertEqual(evidence['finish_history'][0]['violations'], first['violations'])
            self.assertEqual(evidence['violations'], [])
            # Repeating finish must retain evidence even if a fresh unauthorized
            # modification appears after the recovery check.
            outside.write_text('second unauthorized change', encoding='utf-8')
            last = flow.guard_work(wp, w, 'spec', 'finish')
            self.assertEqual(last['status'], 'blocked')
            history = flow.read_json(Path(last['guard']))['finish_history']
            self.assertEqual([row['verdict'] for row in history], ['blocked', 'passed'])

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

    def test_handoff_starts_guard_and_blocks_transition_until_finish(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);w=work();wp=root/'work.json';wp.write_bytes(flow.json_bytes(w))
            (root/'Lifecycle'/'CAT'/'Draft').mkdir(parents=True)
            handoff=flow.handoff_work(wp,w,'spec')
            self.assertEqual(handoff['guard']['status'],'passed')
            with self.assertRaisesRegex(flow.Blocked,'prior Agent guard'):
                flow.handoff_work(wp,w,'spec-closure')
            (root/'Lifecycle'/'CAT'/'Draft'/'demo.md').write_text('draft',encoding='utf-8')
            self.assertEqual(flow.guard_work(wp,w,'spec','finish')['status'],'passed')
            self.assertEqual(flow.handoff_work(wp,w,'spec-closure')['route_status'],'ready')

    def test_pending_same_stage_guard_cannot_be_restarted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);w=work();wp=root/'work.json';wp.write_bytes(flow.json_bytes(w))
            (root/'Lifecycle'/'CAT'/'Draft').mkdir(parents=True)
            self.assertEqual(flow.guard_work(wp,w,'spec','start')['status'],'passed')
            with self.assertRaisesRegex(flow.Blocked,'cannot replace its baseline'):
                flow.guard_work(wp,w,'spec','start')


    def test_implementer_guard_allows_production_and_rejects_test_edits(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'app';(repo/'src').mkdir(parents=True);(repo/'tests').mkdir()
            subprocess.run(['git','init',str(repo)],check=True,capture_output=True)
            source=repo/'src'/'main.py';test=repo/'tests'/'test_main.py'
            source.write_text('value=1\n',encoding='utf-8');test.write_text('assert True\n',encoding='utf-8')
            w=work()
            w.update(entry='confirmed-spec',flow='spec-implementation',work_kind='implementation')
            w['specification']={'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']}
            w['repositories']=[{'name':'app','path':'./app','allowed_paths':['src/**','tests/**'],
                                'production_paths':['src/**'],'test_paths':['tests/**']}]
            wp=root/'work.json';wp.write_bytes(flow.json_bytes(w))

            self.assertEqual(flow.guard_work(wp,w,'implementation','start')['status'],'passed')
            source.write_text('value=2\n',encoding='utf-8')
            self.assertEqual(flow.guard_work(wp,w,'implementation','finish')['status'],'passed')

            self.assertEqual(flow.guard_work(wp,w,'implementation','start')['status'],'passed')
            test.write_text('assert False\n',encoding='utf-8')
            result=flow.guard_work(wp,w,'implementation','finish')
            self.assertEqual(result['status'],'blocked')
            self.assertTrue(any('tests/test_main.py' in item.get('paths',[]) for item in result['violations']))


if __name__ == '__main__':
    unittest.main()
