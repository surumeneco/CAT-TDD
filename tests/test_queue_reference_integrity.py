"""A TDD Queue is an exact source-to-vector plan, not a bag of valid IDs."""
import sys, unittest
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'),str(Path(__file__).resolve().parent)]
import test_cat_queue
from cat_compile_v2 import make_queue,validate_queue,Blocked

class QueueReferenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        fixtures=test_cat_queue.QueueRuntimeTest()
        self.m=fixtures.model();self.v=fixtures.vectors()
        self.mb=b'model';self.vb=b'vectors'
        self.q=make_queue(self.m,self.v,self.mb,self.vb)

    def check(self):
        return validate_queue(self.q,self.m,self.v,self.mb,self.vb)

    def test_pending_model_ref_cannot_claim_unrelated_rule(self):
        self.q['items'][1]['model_ref']=self.q['items'][0]['model_ref']
        with self.assertRaisesRegex(Blocked,'Queue model_ref does not match vector'):
            self.check()

    def test_duplicate_or_omitted_vector_is_rejected(self):
        self.q['items'][1]['vector_ref']=self.q['items'][0]['vector_ref']
        with self.assertRaisesRegex(Blocked,'Queue vectors do not match'):
            self.check()
        self.q['items']=self.q['items'][:1]
        with self.assertRaisesRegex(Blocked,'Queue vectors do not match'):
            self.check()

    def test_reordered_complete_queue_cannot_change_tdd_execution_order(self):
        self.q['items'].reverse()
        for index, item in enumerate(self.q['items'],1):
            item['order']=index
        with self.assertRaisesRegex(Blocked,'Queue order or vector sequence'):
            self.check()

    def test_item_id_cannot_hide_different_vector_ref(self):
        self.q['items'][1]['id']='case.altered'
        with self.assertRaisesRegex(Blocked,'Queue item ID'):
            self.check()

    def test_true_is_not_integer_queue_order(self):
        self.q['items'][0]['order']=True
        with self.assertRaisesRegex(Blocked,'Queue order'):
            self.check()

    def test_unmodified_and_advanced_queue_are_valid(self):
        self.assertEqual(self.check()['id'],'case.on')
        self.q['items'][0]['status']='done';self.q['items'][1]['status']='current'
        self.assertEqual(self.check()['id'],'case.off')

if __name__=='__main__': unittest.main()
