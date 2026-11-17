"""A closed Guard does not by itself prove TCE Effect totality."""
import sys, tempfile, unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts')]
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load

class EffectTotalityTests(unittest.TestCase):
    def fixture(self,root,score_domain='integer[0..1]',output_domain='integer[0..1]',effect='input.score + 1'):
        p,pi,tce=write_v2(root,False)
        pi.write_text(pi.read_text().replace(
            '| output.accepted | send | boolean | required |',
            '| input.score | receive | '+score_domain+' | required |\n'
            '| output.accepted | send | '+output_domain+' | required |'))
        tce.write_text(tce.read_text().replace('output.accepted = true',
            'output.accepted = '+effect).replace('output.accepted = false',
            'output.accepted = '+effect))
        for f in p,pi,tce:
            f.write_text(f.read_text().replace('status: draft','status: confirmed')
                .replace("decision_ref: ''",'decision_ref: https://example.org/decision'))
        return p,pi,tce

    def test_out_of_domain_operator_does_not_confirm_closed_guard(self):
        with tempfile.TemporaryDirectory() as td:
            model=load(*self.fixture(Path(td)),allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            self.assertEqual(model['status'],'draft')
            self.assertTrue(model['unverified_effect_ids'])

    def test_bounded_operator_proved_and_status_confirmed(self):
        with tempfile.TemporaryDirectory() as td:
            model=load(*self.fixture(Path(td),output_domain='integer[0..2]'),allow_partial=True)
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['unverified_effect_ids'],[])
            self.assertTrue(all(v['result']=='proved' for v in model['effect_checks'].values()))

    def test_nonfinite_operator_remains_unproven_not_hypothetically_green(self):
        with tempfile.TemporaryDirectory() as td:
            model=load(*self.fixture(Path(td),score_domain='integer',output_domain='integer'),allow_partial=True)
            self.assertEqual(model['status'],'draft')
            self.assertTrue(model['unverified_effect_ids'])

    def test_independent_model_conformance_checks_effect_proofs(self):
        import json
        from cat_model_conformance import validate
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=self.fixture(root)
            model=load(p,pi,tce,allow_partial=True)
            path=root/'TestModel.json'
            path.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,path)['status'],'passed')
            forged=dict(model)
            forged['unverified_effect_ids']=[]
            forged['effect_checks']={k:{'result':'proved'} for k in model['effect_checks']}
            forged['status']='confirmed'
            path.write_text(json.dumps(forged),encoding='utf-8')
            result=validate(p,pi,tce,path)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('effect_checks',result['mismatches'])
            self.assertIn('unverified_effect_ids',result['mismatches'])
            self.assertIn('normative_status_unjustified',result['mismatches'])

    def test_source_proof_changes_with_effect_domain(self):
        import json
        from cat_model_conformance import validate
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=self.fixture(root,output_domain='integer[0..2]')
            model=load(p,pi,tce,allow_partial=True)
            path=root/'Model.json'
            path.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,path)['status'],'passed')
            pi.write_text(pi.read_text().replace('integer[0..2]','integer[0..1]'))
            result=validate(p,pi,tce,path)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('effect_checks',result['mismatches'])

    def test_proved_bounded_effect_reaches_vectors_queue_and_renderer(self):
        import json
        from cat_compile_v2 import selection_vectors,expand_cases,make_queue,emit_vitest
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=self.fixture(root,output_domain='integer[0..2]')
            model=load(p,pi,tce,allow_partial=True)
            self.assertEqual(model['status'],'confirmed')
            vectors=selection_vectors(model)
            self.assertEqual(len(vectors['cases']),2)
            cases=expand_cases(model,vectors)
            self.assertTrue(all(case['allowed'][0]['output']['output.accepted']==1
                                for case in cases))
            queue=make_queue(model,vectors,json.dumps(model).encode(),json.dumps(vectors).encode())
            self.assertEqual(len(queue['items']),2)
            self.assertEqual([x['status'] for x in queue['items']],['current','pending'])
            binding=root/'binding.json'
            binding.write_text(json.dumps({'schema':'cat-test-driver/v2',
                         'process':model['process'],'driver':'./driver'}),encoding='utf-8')
            code=emit_vitest(model,vectors,binding)
            self.assertIn('output.accepted',code)

    def test_implementation_obligations_preserve_effect_gaps(self):
        from cat_implementation_obligations import generate
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.fixture(Path(td))
            obligations=generate(p,pi,[tce])
            self.assertEqual(obligations['model_status'],'draft')
            self.assertTrue(obligations['unresolved_effect_ids'])
            self.assertEqual(obligations['unresolved_rule_ids'],[])

    def test_markdown_model_cannot_hide_unproved_effect_totality(self):
        from cat_compile_v2 import render_model_markdown
        from cat_model_conformance import validate
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=self.fixture(root)
            model=load(p,pi,tce,allow_partial=True)
            path=root/'Model.md'
            path.write_text(render_model_markdown(model),encoding='utf-8')
            result=validate(p,pi,tce,path)
            self.assertEqual(result['status'],'blocked')
            self.assertTrue(any('effect_totality' in x for x in result['mismatches']))

    def test_output_from_nonrequired_input_needs_presence_proof(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.fixture(Path(td),effect='input.score')
            pi.write_text(pi.read_text().replace('| input.score | receive | integer[0..1] | required |',
                                                 '| input.score | receive | integer[0..1] | optional |'))
            model=load(p,pi,tce,allow_partial=True)
            self.assertEqual(model['status'],'draft')
            self.assertTrue(model['unverified_effect_ids'])
            self.assertTrue(any('nonrequired' in x.get('reason','') for x in model['effect_checks'].values()))

if __name__=='__main__':unittest.main()
