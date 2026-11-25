"""Ordered collection updates are total without enumerating list values."""
import sys, tempfile, unittest, json
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts')]
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load,eval_expr,parse_expr_text,render_model_markdown,Blocked
from cat_model_conformance import validate
from unittest.mock import patch

class SequenceEffects(unittest.TestCase):
    def fixture(self,root,expr,target='sequence<record<id:string,name:string>>',item='record<id:string,name:string>',presence='required'):
        p,pi,tce=write_v2(root,False)
        pi.write_text(pi.read_text(encoding='utf-8').replace('| output.accepted | send | boolean | required |',
            '| input.items | receive | sequence<record<id:string,name:string>> | required |\n'
            '| input.item | receive | '+item+' | '+presence+' |\n'
            '| input.index | receive | integer | required |\n'
            '| output.accepted | send | '+target+' | required |'),encoding='utf-8')
        tce.write_text(tce.read_text(encoding='utf-8').replace('output.accepted = true','output.accepted = '+expr).replace('output.accepted = false','output.accepted = '+expr),encoding='utf-8')
        for f in (p,pi,tce):
            f.write_text(f.read_text(encoding='utf-8').replace('status: draft','status: confirmed').replace("decision_ref: ''",'decision_ref: https://example.org/decision'),encoding='utf-8')
        return p,pi,tce
    def test_semantics(self):
        rows=[{'id':'a','name':'A'},{'id':'b','name':'B'},{'id':'c','name':'C'}]
        env={'input.items':rows,'input.item':{'id':'d','name':''},'input.index':1}
        def evaluate(s):return eval_expr(parse_expr_text(s),env,{})
        self.assertEqual(evaluate('sequence_append(input.items, input.item)'),rows+[env['input.item']])
        self.assertEqual(evaluate('sequence_swap(input.items, input.index, 0)'),[rows[1],rows[0],rows[2]])
        self.assertEqual(evaluate('列交換(input.items, input.index, 2)'),[rows[0],rows[2],rows[1]])
        self.assertEqual(evaluate('列項目更新(input.items,input.index,"name","new")'),[rows[0],{'id':'b','name':'new'},rows[2]])
        self.assertEqual(evaluate('列項目更新(input.items,-1,"name","new")'),rows)
        for i,j in [(-1,0),(0,-1),(3,1),(1,99),(1,1)]:
            self.assertEqual(evaluate(f'sequence_swap(input.items,{i},{j})'),rows)
        self.assertEqual(rows,[{'id':'a','name':'A'},{'id':'b','name':'B'},{'id':'c','name':'C'}])
        env['input.items']=[];self.assertEqual(evaluate('sequence_swap(input.items,0,1)'),[])
    def test_exact_effect_and_independent_source(self):
        for expr in ['sequence_append(input.items,input.item)','sequence_swap(input.items,input.index,input.index + 1)','列交換(input.items,input.index,input.index - 1)', 'sequence_append(input.items,{"id":"new","name":""})','sequence_replace_member(input.items,input.index,"name","new")']:
            with self.subTest(expr=expr), tempfile.TemporaryDirectory() as td:
                p,pi,tce=self.fixture(Path(td),expr);m=load(p,pi,tce,allow_partial=True)
                self.assertEqual(m['status'],'confirmed');self.assertEqual(m['unverified_effect_ids'],[])
                for name,data in [('model.json',json.dumps(m)),('model.md',render_model_markdown(m))]:
                    dest=Path(td)/name;dest.write_text(data,encoding='utf-8');self.assertEqual(validate(p,pi,tce,dest)['status'],'passed')
    def test_narrow_or_nonrequired_rejected(self):
        for expr,target,item,presence in [
            ('sequence_append(input.items,input.item)','sequence<record<id:string,name:string>>','record<id:string,name:integer>','required'),
            ('sequence_append(input.items,{"id":"new"})','sequence<record<id:string,name:string>>','record<id:string,name:string>','required'),
            ('sequence_append(input.items,{"id":"new","name":1})','sequence<record<id:string,name:string>>','record<id:string,name:string>','required'),
            ('sequence_append(input.items,input.item)','sequence<record<id:string,name:string>>','record<id:string,name:string>','optional'),
            ('sequence_replace_member(input.items,input.index,"name",1)','sequence<record<id:string,name:string>>','record<id:string,name:string>','required'),
            ('sequence_replace_member(input.items,input.index,"missing","new")','sequence<record<id:string,name:string>>','record<id:string,name:string>','required'),
            ('sequence_swap(input.items,input.index,0)','sequence<record<id:integer,name:string>>','record<id:string,name:string>','required')]:
            with self.subTest(expr=expr,presence=presence), tempfile.TemporaryDirectory() as td:
                p,pi,tce=self.fixture(Path(td),expr,target,item,presence)
                try:m=load(p,pi,tce,allow_partial=True)
                except Blocked:continue
                self.assertNotEqual(m['status'],'confirmed');self.assertTrue(m['unverified_effect_ids'])
    def test_length_partition_and_gap(self):
        from test_projection_unused_typed_sibling import fixture,closure
        from cat_compile_v2 import selection_vectors,expand_cases
        for gap in (False,True):
            with self.subTest(gap=gap), tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,tce=fixture(root,'string',guard='length(input.request) < 50',gap=gap)
                pi.write_text(pi.read_text(encoding='utf-8').replace('record<version:integer,metadata:string>','sequence<record<id:string,name:string>>'),encoding='utf-8')
                m=load(p,pi,tce,allow_partial=True);check=m['coverage_checks']['compare']
                self.assertEqual(check['result'],'uncovered' if gap else 'proved')
                self.assertEqual(check['proof_method'],'sequence-length-literal-partition/v1')
                self.assertEqual(check['abstract_state_count'],4)
                path=root/'Model.json';path.write_text(json.dumps(m),encoding='utf-8');self.assertEqual(validate(p,pi,tce,path)['status'],'passed')
                self.assertEqual(closure(root)=='passed',not gap)
                if not gap:
                    self.assertEqual({len(c['input']['input.request']) for c in expand_cases(m,selection_vectors(m))},{0,50})
    def test_length_unsupported_comparison(self):
        from test_projection_unused_typed_sibling import fixture
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pi,tce=fixture(root,'string',guard='length(input.request) == state.version')
            pi.write_text(pi.read_text(encoding='utf-8').replace('record<version:integer,metadata:string>','sequence<record<id:string,name:string>>'),encoding='utf-8')
            self.assertEqual(load(p,pi,tce,allow_partial=True)['coverage_checks']['compare']['result'],'unproven')
    def test_independent_rejects_false_positive(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.fixture(Path(td),'sequence_append(input.items,input.item)',item='record<id:string,name:integer>');m=load(p,pi,tce,allow_partial=True)
            self.assertTrue(m['unverified_effect_ids']); forged={k:{'result':'proved'} for k in m['effect_checks']}
            m.update(status='confirmed',effect_checks=forged,unverified_effect_ids=[]);dest=Path(td)/'model.json';dest.write_text(json.dumps(m),encoding='utf-8')
            with patch('cat_model_conformance._effect_totality_checks',return_value=forged):
                r=validate(p,pi,tce,dest)
            self.assertEqual(r['status'],'blocked');self.assertIn('effect_totality_independent',r['mismatches'])
if __name__=='__main__':unittest.main()
