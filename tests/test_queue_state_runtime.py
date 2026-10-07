from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_flow as flow


class QueueStateFlowTest(unittest.TestCase):
    def work(self):
        return {
            'schema':'cat-work/v1','id':'demo.queue.state','entry':'confirmed-spec',
            'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
            'parent':'','depends_on':[],'issue_ref':'spec','project_entry_ref':'project',
            'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
            'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},
            'scope':{'process_ids':['demo'],'changed_ids':[],'preserved_ids':[]},
            'technologies':[],'repositories':[],'checks':[],'gates':[],
            'compilation':{'schema':'cat-compile/v2','queue':'Queue.json'}
        }

    def queue(self):
        return {'schema':'cat-tdd-queue/v1','process':'demo','items':[
            {'id':'case.one','model_ref':'demo.one','vector_ref':'case.one','order':1,'status':'current','evidence_ref':None},
            {'id':'case.two','model_ref':'demo.two','vector_ref':'case.two','order':2,'status':'pending','evidence_ref':None},
        ]}

    def green(self,root,work,qpath,current):
        evidence=root/'.cat-flow'/'evidence'/'green.json'
        evidence.parent.mkdir(parents=True,exist_ok=True)
        evidence.write_bytes(flow.json_bytes({
            'schema':'cat-flow-evidence/v1','work_id':work['id'],'stage':'green','verdict':'passed',
            'queue_context':{'path':str(qpath),'sha256':flow.sha(qpath.read_bytes()),'current_item_id':current},
        }))
        return evidence

    def test_green_evidence_advances_exact_current_item(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=self.work();wp=root/'Work.json';wp.write_bytes(flow.json_bytes(work))
            qpath=root/'Queue.json';qpath.write_text(json.dumps(self.queue()),encoding='utf-8')
            evidence=self.green(root,work,qpath,'case.one')
            result=flow.queue_state_work(wp,work,str(evidence))
            self.assertEqual(result['outcome'],'next-item')
            updated=json.loads(qpath.read_text(encoding='utf-8'))
            self.assertEqual(updated['items'][0]['status'],'done')
            self.assertEqual(updated['items'][1]['status'],'current')
            self.assertEqual(updated['items'][0]['evidence_ref'],str(evidence.resolve()))

    def test_stale_green_evidence_cannot_advance_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=self.work();wp=root/'Work.json';wp.write_bytes(flow.json_bytes(work))
            qpath=root/'Queue.json';qpath.write_text(json.dumps(self.queue()),encoding='utf-8')
            evidence=self.green(root,work,qpath,'case.one')
            q=json.loads(qpath.read_text(encoding='utf-8'));q['items'][1]['evidence_ref']='tamper'
            qpath.write_text(json.dumps(q),encoding='utf-8')
            with self.assertRaisesRegex(flow.Blocked,'Queue changed since Green evidence'):
                flow.queue_state_work(wp,work,str(evidence))


if __name__=='__main__':
    unittest.main()
