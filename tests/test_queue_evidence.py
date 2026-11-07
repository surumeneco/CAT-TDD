#!/usr/bin/env python3
"""Green execution receipts must match prior Queue bytes, model, vectors and Work."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_compile_v2 as compiler
import cat_queue
import cat_queue_evidence
import cat_implementation_obligations as obligations
from catlib.common import Blocked,json_bytes,sha


def spec():
    model={
      'schema':compiler.M,'process':'demo.process','status':'confirmed',
      'triggers':[{'id':'submit','origin':'demo.pi'}],
      'fields':[{'id':'input.flag','role':'input','presence':'required','domain':{'type':'boolean'}},
                {'id':'state.ready','role':'state','domain':{'type':'boolean'}},
                {'id':'output.ok','role':'output','presence':'required','domain':{'type':'boolean'}}],
      'pi_constraints':[],'definitions':[],
      'rules':[{'id':'demo.rule','trigger':'submit','when':{'literal':True},
                'allowed':[{'write':[{'target':'output.ok','expr':{'literal':True}}],
                            'unchanged':['state.ready'],'absent_outputs':[]}]}]
    }
    vectors={'schema':compiler.V,'process':'demo.process','cases':[
      {'id':'case.demo.rule','trigger':'submit',
       'input':{'input.flag':True},'state':{'state.ready':False}}]}
    return model,vectors


class QueueEvidenceTest(unittest.TestCase):
    def prepare(self,root):
        model,vectors=spec()
        model_path=root/'model.json';model_path.write_bytes(json_bytes(model))
        vector_path=root/'vectors.json';vector_path.write_bytes(json_bytes(vectors))
        queue=compiler.make_queue(model,vectors,model_path.read_bytes(),vector_path.read_bytes())
        queue_path=root/'queue.json';queue_path.write_bytes(json_bytes(queue))
        evidence_dir=root/'.cat-flow'/'evidence';evidence_dir.mkdir(parents=True)
        evidence_path=evidence_dir/'green.json'
        receipt={'schema':'cat-flow-evidence/v1','stage':'green','verdict':'passed',
                 'work_id':'demo.work','queue_context':{
                     'current_item_id':queue['items'][0]['id'],
                     'sha256':sha(queue_path.read_bytes())}}
        evidence_path.write_bytes(json_bytes(receipt))
        return model_path,vector_path,queue_path,evidence_dir,evidence_path

    def test_real_queue_transition_is_verified(self):
        with tempfile.TemporaryDirectory() as td:
            m,v,q,root,e=self.prepare(Path(td))
            cat_queue.done_from_green(q,e,expected_work_id='demo.work',
                                      allowed_evidence_root=root)
            verified=cat_queue_evidence.verify('demo.work',q,m,v,root)
            self.assertEqual(len(verified['demo.rule']),1)
            self.assertIn('#sha256=',verified['demo.rule'][0])
            obligation={'schema':'cat-implementation-obligations/v1',
                        'items':[{'id':'behavior.demo.rule','category':'behavior',
                                  'source_ref':'demo.tce#demo.rule','method':'generated-test',
                                  'status':'not-run','reason':'not-run','limitation':'none'}]}
            without=obligations.aggregate(obligation)
            self.assertEqual(without['items'][0]['status'],'inconclusive')
            with_proof=obligations.aggregate(obligation,verified_green=verified)
            self.assertEqual(with_proof['items'][0]['status'],'passed')

    def test_evidence_mutation_or_wrong_work_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            m,v,q,root,e=self.prepare(Path(td))
            cat_queue.done_from_green(q,e,expected_work_id='demo.work',
                                      allowed_evidence_root=root)
            rec=json.loads(e.read_text())
            rec['verdict']='failed';e.write_bytes(json_bytes(rec))
            with self.assertRaisesRegex(Blocked,'does not prove'):
                cat_queue_evidence.verify('demo.work',q,m,v,root)
            rec['verdict']='passed';e.write_bytes(json_bytes(rec))
            with self.assertRaisesRegex(Blocked,'does not prove'):
                cat_queue_evidence.verify('different.work',q,m,v,root)

    def test_changed_queue_pretransition_hash_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            m,v,q,root,e=self.prepare(Path(td))
            cat_queue.done_from_green(q,e,expected_work_id='demo.work',
                                      allowed_evidence_root=root)
            rec=json.loads(e.read_text());rec['queue_context']['sha256']='0'*64
            e.write_bytes(json_bytes(rec))
            with self.assertRaisesRegex(Blocked,'pre-transition'):
                cat_queue_evidence.verify('demo.work',q,m,v,root)

    def test_model_change_after_queue_generation_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            m,v,q,root,e=self.prepare(Path(td))
            cat_queue.done_from_green(q,e,expected_work_id='demo.work',
                                      allowed_evidence_root=root)
            data=json.loads(m.read_text());data['fields'][0]['presence']='optional'
            m.write_bytes(json_bytes(data))
            with self.assertRaisesRegex(compiler.Blocked,'stale'):
                cat_queue_evidence.verify('demo.work',q,m,v,root)


if __name__=='__main__':unittest.main()
