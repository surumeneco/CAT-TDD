"""Source-bound nonapplicability must not become a runtime verifier obligation."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import load
from cat_implementation_obligations import generate
from cat_verifier_contracts import VerifierError, evaluate
from test_intrinsic_rule_proofs import build


class NonapplicableRuleObligationTests(unittest.TestCase):
    def _model(self,root):
        p,pi,t,r=build(root,requirement='Retain the result relation',
                       verification='source-bound-verifier',
                       condition='demo.process.other')
        model=load(p,pi,t,common_rules=[r])
        self.assertEqual(model['rule_obligations'][0]['verification_status'],'not-applicable')
        return (p,pi,t,r),model

    def _registry(self,root,model,entries):
        model_path=root/'model.json'
        model_path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
        registry_path=root/'registry.json'
        registry_path.write_text(json.dumps({
            'schema':'cat-verifier-registry/v1',
            'model_sha256':hashlib.sha256(model_path.read_bytes()).hexdigest(),
            'entries':entries},ensure_ascii=False),encoding='utf-8')
        return model_path,registry_path

    def test_nonapplicable_rule_does_not_create_implementation_obligation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (p,pi,t,r),model=self._model(root)
            result=generate(p,pi,[t],common_rules=[r])
            self.assertNotIn('normative-rule.demo.rule.check',
                             [item['id'] for item in result['items']])
            self.assertEqual(result['unresolved_rule_ids'],[])
            self.assertEqual(model['rule_obligations'][0]['source_sha256'],
                             model['normative_rule_inputs'][0]['sha256'])

    def test_nonapplicable_rule_is_reported_without_not_run_verifier_requirement(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            _,model=self._model(root)
            mp,rp=self._registry(root,model,[])
            result=evaluate(mp,rp)
            self.assertEqual([item['status'] for item in result['results']],['not-applicable'])
            entry=result['results'][0]
            self.assertEqual(entry['rule_id'],'demo.rule.check')
            self.assertEqual(entry['source_sha256'],model['normative_rule_inputs'][0]['sha256'])
            self.assertEqual(entry['scope_binding'],model['rule_obligations'][0]['scope_binding'])
            self.assertEqual(result['normative_status'],'inconclusive')

    def test_out_of_scope_rule_cannot_be_registered_for_fixture_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            _,model=self._model(root)
            rule=model['rule_obligations'][0]
            entry={'rule_id':rule['id'],'source_artifact':rule['source_artifact'],
                   'source_sha256':model['normative_rule_inputs'][0]['sha256'],
                   'subject':'static','verifier_id':'wrong-process-fixture',
                   'fixture':{'path':'fixture.json','sha256':'0'*64},
                   'assertions':[{'id':'x','path':'pass','op':'eq','expected':True}]}
            mp,rp=self._registry(root,model,[entry])
            with self.assertRaisesRegex(VerifierError,'not-applicable'):
                evaluate(mp,rp)

    def test_applicable_rule_fixture_pass_does_not_depend_on_other_process_rule(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (p,pi,t,r),_=self._model(root)
            r.write_text(r.read_text(encoding='utf-8')+
                         '| demo.rule.active | demo.process | Verify declared behavior | static checker |\n',
                         encoding='utf-8')
            model=load(p,pi,t,common_rules=[r])
            self.assertEqual(model['unverified_rule_ids'],['demo.rule.active'])
            fixture=b'{"ok":true}'
            (root/'fixture.json').write_bytes(fixture)
            runner=("import json,sys,hashlib\n"
                    "p=sys.argv[1]\n"
                    "a=open(p,'rb').read()\n"
                    "print(json.dumps({'schema':'cat-verifier-observation/v1',"
                    "'rule_id':'demo.rule.active','subject':'static',"
                    "'fixture_sha256':hashlib.sha256(a).hexdigest(),"
                    "'observed':json.loads(a)}))\n")
            (root/'runner.py').write_text(runner,encoding='utf-8')
            entry={'rule_id':'demo.rule.active','source_artifact':'demo.rule.document',
                   'source_sha256':model['normative_rule_inputs'][0]['sha256'],
                   'subject':'static','verifier_id':'test-fixture',
                   'runner':{'type':'python-json-v1','path':'runner.py',
                             'sha256':hashlib.sha256(runner.encode()).hexdigest()},
                   'fixture':{'path':'fixture.json','sha256':hashlib.sha256(fixture).hexdigest()},
                   'assertions':[{'id':'ok','path':'ok','op':'eq','expected':True}]}
            mp,rp=self._registry(root,model,[entry])
            verdict=evaluate(mp,rp)
            self.assertEqual(verdict['status'],'passed')
            self.assertEqual(verdict['normative_status'],'inconclusive')
            self.assertEqual({v['rule_id']:v['status'] for v in verdict['results']},
                             {'demo.rule.active':'passed','demo.rule.check':'not-applicable'})
            generated=generate(p,pi,[t],common_rules=[r])
            self.assertIn('normative-rule.demo.rule.active',
                          [v['id'] for v in generated['items']])
            self.assertNotIn('normative-rule.demo.rule.check',
                             [v['id'] for v in generated['items']])

    def test_nonapplicability_binding_target_and_source_hash_tampering_fails_closed(self):
        for field,value in [('targets',['demo.process.unrelated']),
                            ('source_sha256','0'*64)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                _,model=self._model(root)
                model['rule_obligations'][0]['scope_binding'][field]=value
                mp,rp=self._registry(root,model,[])
                with self.assertRaisesRegex(VerifierError,'scope binding'):
                    evaluate(mp,rp)

    def test_tampered_process_scope_cannot_skip_rule(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            _,model=self._model(root)
            rule=model['rule_obligations'][0]
            rule['scope_binding']['evaluated_process']='demo.process.other'
            mp,rp=self._registry(root,model,[])
            with self.assertRaisesRegex(VerifierError,'scope binding'):
                evaluate(mp,rp)

if __name__=='__main__':
    unittest.main()
