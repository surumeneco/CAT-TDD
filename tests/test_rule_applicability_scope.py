"""CAT41 U03: an explicitly scoped Rule is not an unverified obligation of another Process.

The known owner is obtained only from a complete, syntactically unambiguous
Source condition, not from keywords in a natural-language requirement.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import load
import cat_flow
import cat_model_conformance as independent
from test_intrinsic_rule_proofs import build


class ExplicitRuleScopeTests(unittest.TestCase):
    def _fixture(self,root,condition,rule='demo.rule.check'):
        p,pi,t,r=build(root,requirement='Retain the declared result relation',
                         verification='source-bound-verifier',condition=condition)
        return p,pi,t,r

    def test_other_process_rule_does_not_block_current_process(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p,pi,t,r=self._fixture(root,'demo.process.other; demo.process.another')
            model=load(p,pi,t,common_rules=[r])
            entry=model['rule_obligations'][0]
            self.assertEqual(entry['verification_status'],'not-applicable')
            self.assertEqual(model['unverified_rule_ids'],[])
            self.assertEqual(entry['source_artifact'],'demo.rule.document')
            self.assertEqual(entry['source_sha256'],model['normative_rule_inputs'][0]['sha256'])
            target=root/'Model.json'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],target,common_rules=[r])['status'],'passed')

    def test_process_closure_gate_respects_verified_nonapplicability(self):
        for condition,expected in (
            ('demo.process.other','passed'),
            ('demo.process; demo.process.other','inconclusive'),
        ):
            with self.subTest(condition=condition),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                p,pi,t,r=self._fixture(root,condition)
                work={'id':'test.rule-scope','scope':{'process_ids':['demo.process']},
                      'compilation':{'process':p.name,'pi':pi.name,'tce':t.name,
                                     'common_rules':[r.name],
                                     'allow_partial':True,'allow_draft':False}}
                workpath=root/'Work.json'
                workpath.write_text(json.dumps(work),encoding='utf-8')
                result=cat_flow.conformance_work(workpath,work,'process-closure')
                self.assertEqual(result['status'],expected,result)

    def test_unstructured_natural_language_cannot_be_assumed_not_applicable(self):
        cases=('when demo.process.other is called',
               'demo.process.other; unlisted pseudo scope',
               'all demo.process.other PI data',
               'other business flow',
               'demo.process.other / optional-rule')
        for condition in cases:
            with self.subTest(condition=condition),tempfile.TemporaryDirectory() as d:
                p,pi,t,r=self._fixture(Path(d),condition)
                model=load(p,pi,t,common_rules=[r])
                self.assertEqual(model['unverified_rule_ids'],['demo.rule.check'])
                self.assertEqual(model['rule_obligations'][0]['verification_status'],'unverified')

    def test_rule_for_current_process_must_still_be_verified(self):
        with tempfile.TemporaryDirectory() as d:
            p,pi,t,r=self._fixture(Path(d),'demo.process; demo.process.other')
            model=load(p,pi,t,common_rules=[r])
            self.assertEqual(model['unverified_rule_ids'],['demo.rule.check'])

    def test_not_applicable_or_proven_forgery_detected_against_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p,pi,t,r=self._fixture(root,'demo.process.other')
            model=load(p,pi,t,common_rules=[r])
            model['rule_obligations'][0]['verification_status']='intrinsic-proved'
            model['unverified_rule_ids']=[]
            target=root/'Model.json'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            verdict=independent.validate(p,pi,[t],target,common_rules=[r])
            self.assertEqual(verdict['status'],'blocked')
            self.assertIn('rule_obligations',verdict['mismatches'])

    def test_rule_source_scope_change_invalidates_nonapplicability(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p,pi,t,r=self._fixture(root,'demo.process.other')
            model=load(p,pi,t,common_rules=[r]);target=root/'Model.json'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(independent.validate(p,pi,[t],target,common_rules=[r])['status'],'passed')
            r.write_text(r.read_text(encoding='utf-8').replace('demo.process.other','demo.process'),encoding='utf-8')
            verdict=independent.validate(p,pi,[t],target,common_rules=[r])
            self.assertEqual(verdict['status'],'blocked')

if __name__=='__main__':unittest.main()
