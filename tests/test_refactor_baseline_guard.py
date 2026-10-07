from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_flow as flow


def work():
    return {
        'schema':'cat-work/v1','id':'demo.refactor.guard','entry':'refactor',
        'mode':'implementation','flow':'refactor','work_kind':'refactor',
        'parent':'','depends_on':[],'issue_ref':'refactor','project_entry_ref':'project',
        'normative':[{'uri':'spec'}],'evidence':[{'uri':'diff'}],
        'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},
        'scope':{'process_ids':['demo'],'changed_ids':[],'preserved_ids':['demo.behavior']},
        'technologies':[],'repositories':[],
        'checks':[{'id':'baseline','stage':'refactor-baseline','runner':'exit-zero',
                   'cwd':'@work','argv':[sys.executable,'-c','pass']}],
        'gates':[]
    }


class RefactorBaselineGuardTest(unittest.TestCase):
    def test_refactor_agent_requires_current_passed_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);w=work();wp=root/'work.json';wp.write_bytes(flow.json_bytes(w))
            (root/'source.txt').write_text('before',encoding='utf-8')

            with self.assertRaisesRegex(flow.Blocked,'baseline evidence missing'):
                flow.handoff_work(wp,w,'refactor')

            self.assertEqual(flow.command_work(wp,w,'baseline',True)['verdict'],'passed')
            handoff=flow.handoff_work(wp,w,'refactor')
            self.assertEqual(handoff['guard']['status'],'passed')
            self.assertTrue(handoff['guard']['guard'])
            self.assertEqual(flow.guard_work(wp,w,'refactor','finish')['status'],'passed')

            (root/'source.txt').write_text('changed-before-refactor',encoding='utf-8')
            with self.assertRaisesRegex(flow.Blocked,'baseline is stale'):
                flow.handoff_work(wp,w,'refactor')


if __name__=='__main__':
    unittest.main()
