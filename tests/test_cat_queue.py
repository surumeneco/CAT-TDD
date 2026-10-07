from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
if not SCRIPTS.exists(): SCRIPTS=ROOT/'.cat-system'/'scripts'
sys.path.insert(0,str(SCRIPTS))
import cat_compile_v2 as compiler
import cat_queue

class QueueRuntimeTest(unittest.TestCase):
    def model(self):
        return {
            'schema':'cat-test-model/v2','process':'demo','status':'confirmed',
            'semantic_authority':'cat-markdown/v2','definitions':[],'pi_constraints':[],
            'triggers':[{'id':'submit','origin':'demo'}],
            'fields':[
                {'id':'input.enabled','role':'input','domain':{'type':'boolean'}},
                {'id':'state.active','role':'state','domain':{'type':'boolean'}}],
            'rules':[
                {'id':'demo.on','trigger':'submit','when':{'ref':'input.enabled'},
                 'allowed':[{'write':[{'target':'state.active','expr':{'literal':True}}],
                             'unchanged':[],'absent_outputs':[]}]},
                {'id':'demo.off','trigger':'submit','when':{'op':'not','args':[{'ref':'input.enabled'}]},
                 'allowed':[{'write':[{'target':'state.active','expr':{'literal':False}}],
                             'unchanged':[],'absent_outputs':[]}]}]
        }

    def vectors(self):
        return {'schema':'cat-test-vectors/v2','process':'demo','cases':[
            {'id':'case.on','trigger':'submit','input':{'input.enabled':True},'state':{'state.active':False}},
            {'id':'case.off','trigger':'submit','input':{'input.enabled':False},'state':{'state.active':True}}]}

    def test_queue_contains_lifecycle_refs_only_and_one_current(self):
        m=self.model();v=self.vectors();mb=b'model';vb=b'vectors'
        q=compiler.make_queue(m,v,mb,vb)
        self.assertEqual([x['status'] for x in q['items']],['current','pending'])
        self.assertEqual(set(q['items'][0]),{'id','model_ref','vector_ref','order','status','evidence_ref'})
        selected=compiler.current_vectors(m,v,q,mb,vb)
        self.assertEqual([x['id'] for x in selected['cases']],['case.on'])

    def test_state_manager_advances_mechanically(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'Queue.json'
            q=compiler.make_queue(self.model(),self.vectors(),b'model',b'vectors')
            p.write_text(json.dumps(q),encoding='utf-8')
            evidence=Path(td)/'green.json'
            evidence.write_text(json.dumps({
                'schema':'cat-flow-evidence/v1','work_id':'demo','stage':'green','verdict':'passed',
                'queue_context':{
                    'current_item_id':'case.on',
                    'sha256':__import__('hashlib').sha256(p.read_bytes()).hexdigest(),
                },
            }),encoding='utf-8')
            self.assertEqual(cat_queue.main(['--queue',str(p),'done','--evidence-file',str(evidence)]),0)
            updated=json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(updated['items'][0]['status'],'done')
            self.assertEqual(updated['items'][1]['status'],'current')


    def test_queue_becomes_stale_when_test_model_changes(self):
        model=self.model();vectors=self.vectors()
        original=b'original-model';vb=b'vectors'
        q=compiler.make_queue(model,vectors,original,vb)
        with self.assertRaisesRegex(compiler.Blocked,'Queue is stale: TestModel changed'):
            compiler.current_vectors(model,vectors,q,b'changed-model',vb)


    def test_queue_rejects_semantic_payload(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'Queue.json'
            q=compiler.make_queue(self.model(),self.vectors(),b'model',b'vectors')
            q['items'][0]['oracle']='forbidden'
            p.write_text(json.dumps(q),encoding='utf-8')
            with self.assertRaises(cat_queue.Blocked):
                cat_queue.load(p)
    def test_deterministic_selection_generates_rule_witnesses(self):
        selected=compiler.selection_vectors(self.model())
        self.assertEqual(selected['selection_rule'],'rule-witness/v1')
        self.assertEqual({x['id'] for x in selected['cases']},{'case.demo.on','case.demo.off'})
        q=compiler.make_queue(self.model(),selected,b'model',json.dumps(selected,sort_keys=True).encode())
        self.assertEqual({x['model_ref'] for x in q['items']},{'demo.on','demo.off'})

    def test_queue_rejects_selection_that_omits_model_rule(self):
        vectors=self.vectors()
        vectors['cases']=vectors['cases'][:1]
        with self.assertRaisesRegex(compiler.Blocked,'omitted TestModel rule'):
            compiler.make_queue(self.model(),vectors,b'model',b'vectors')


    def test_state_manager_rejects_missing_evidence_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'Queue.json'
            q=compiler.make_queue(self.model(),self.vectors(),b'model',b'vectors')
            p.write_text(json.dumps(q),encoding='utf-8')
            code=cat_queue.main(['--queue',str(p),'done','--evidence-file',str(Path(td)/'missing.json')])
            self.assertNotEqual(code,0)
            self.assertEqual(json.loads(p.read_text(encoding='utf-8'))['items'][0]['status'],'current')


if __name__=='__main__': unittest.main()
