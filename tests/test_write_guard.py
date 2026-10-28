from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    def test_windows_snapshot_keys_match_portable_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            wp = Path(td) / 'work.json'; w = work(); wp.write_bytes(flow.json_bytes(w))
            with patch.object(flow, '_workspace_state', side_effect=[{}, {'Lifecycle\\CAT\\Draft\\demo.md': 'new'}]):
                flow.guard_work(wp, w, 'spec', 'start')
                self.assertEqual(flow.guard_work(wp, w, 'spec', 'finish')['status'], 'passed')

    def test_authorized_external_change_is_hash_bound_and_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            wp = Path(td) / 'work.json'; w = work(); wp.write_bytes(flow.json_bytes(w))
            with patch.object(flow, '_workspace_state', side_effect=[{}, {'outside.txt': 'a'*64}, {'outside.txt': 'a'*64}, {'outside.txt': 'b'*64}]):
                flow.guard_work(wp, w, 'spec', 'start')
                self.assertEqual(flow.guard_work(wp, w, 'spec', 'finish')['status'], 'blocked')
                accepted = [{'scope': 'workspace', 'path': 'outside.txt', 'sha256': 'a'*64}]
                result = flow.guard_work(wp, w, 'spec', 'finish', accepted_changes=accepted, decision_ref='user:external-change')
                self.assertEqual(result['status'], 'passed')
                data = flow.read_json(Path(result['guard']))
                self.assertEqual(data['workspace_state'], {})
                self.assertEqual(data['finish_history'][0]['verdict'], 'blocked')
                self.assertEqual(data['accepted_changes'][0]['decision_ref'], 'user:external-change')
                self.assertEqual(flow.guard_work(wp, w, 'spec', 'finish')['status'], 'blocked')

    def test_external_change_requires_decision_and_cannot_accept_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            wp = Path(td) / 'work.json'; w = work(); wp.write_bytes(flow.json_bytes(w))
            with patch.object(flow, '_workspace_state', return_value={}):
                flow.guard_work(wp, w, 'spec', 'start')
                accepted = [{'scope': 'workspace', 'path': 'outside.txt', 'sha256': 'a'*64}]
                with self.assertRaisesRegex(flow.Blocked, 'decision'):
                    flow.guard_work(wp, w, 'spec', 'finish', accepted_changes=accepted)
                accepted[0]['path'] = '.cat-flow/evidence/result.json'
                with self.assertRaisesRegex(flow.Blocked, 'evidence'):
                    flow.guard_work(wp, w, 'spec', 'finish', accepted_changes=accepted, decision_ref='user:decision')

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
