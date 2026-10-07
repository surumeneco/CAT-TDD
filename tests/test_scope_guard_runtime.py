from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_flow as flow


def work(identifier,parent=''):
    return {
        'schema':'cat-work/v1','id':identifier,'entry':'issue','mode':'implementation',
        'flow':'issue-work','work_kind':'specification','parent':parent,'depends_on':[],
        'issue_ref':'issue','project_entry_ref':'project',
        'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
        'specification':{'status':'candidate','decision_ref':None,'artifact_refs':[]},
        'scope':{'process_ids':['demo'],'changed_ids':[],'preserved_ids':[]},
        'technologies':[],'repositories':[],'checks':[],'gates':[]
    }


class ScopeGuardRuntimeTest(unittest.TestCase):
    def write(self,root,state,w):
        d=root/'Lifecycle'/'Works'/state/w['id'];d.mkdir(parents=True,exist_ok=True)
        p=d/'work.json';p.write_bytes(flow.json_bytes(w));return p

    def test_parent_agent_cannot_start_until_deeper_child_completed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for state in ('New','InProgress','Blocked','Completed','Cancelled'):
                (root/'Lifecycle'/'Works'/state).mkdir(parents=True)
            (root/'Lifecycle'/'CAT'/'Draft').mkdir(parents=True)
            parent=work('demo.parent')
            child=work('demo.child','demo.parent')
            pp=self.write(root,'InProgress',parent)
            cp=self.write(root,'InProgress',child)

            with self.assertRaisesRegex(flow.Blocked,'not a deepest ready scope'):
                flow.guard_work(pp,parent,'spec','start')

            self.assertEqual(flow.guard_work(cp,child,'spec','start')['status'],'passed')
            self.assertEqual(flow.guard_work(cp,child,'spec','finish')['status'],'passed')

            old=cp.parent
            new=root/'Lifecycle'/'Works'/'Completed'/child['id']
            os.replace(old,new)

            self.assertEqual(flow.guard_work(pp,parent,'spec','start')['status'],'passed')


if __name__=='__main__':
    unittest.main()
