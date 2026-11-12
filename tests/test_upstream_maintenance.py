"""Red-first regression tests for CAT-UP-20261113 (W01/W02/W04/W09)."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
import json
import cat_model_conformance as conformance

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import load,parse_domain_text
from catlib import semantic_types
from cat_promote import promote,Blocked
from test_cat_compile_readable import write_v2,fm


class UpstreamMaintenanceTests(unittest.TestCase):
    def test_control_process_closure_with_no_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load(*write_v2(Path(tmp),False),allow_draft=True)
            self.assertEqual(m['coverage_requirement'],'closed')
            self.assertEqual(m['coverage_checks']['submit']['result'],'proved')

    def test_rule_inventory_does_not_erase_proved_local_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t=write_v2(root,False)
            rule=root/'Rule.md'
            rule.write_text(fm('common-rule','demo.process.rule',['demo.process.contract'],language='en')+"""
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| demo.rule | submit | Audit is retained | static contract |
""",encoding='utf-8')
            model=load(p,pi,t,allow_draft=True,common_rules=[rule])
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            self.assertEqual(model['coverage_requirement'],'closed')
            self.assertEqual(model['unverified_rule_ids'],['demo.rule'])
            self.assertEqual(model['status'],'draft')

    def test_nested_enum_with_quoted_comma_and_exact_types(self):
        domain=parse_domain_text('nullable<enum{true,1,"A,B"}>')
        semantic_types.validate(domain)
        self.assertEqual(domain['of']['values'],[True,1,'A,B'])
        self.assertTrue(semantic_types.contains(domain,None))
        self.assertTrue(semantic_types.contains(domain,True))
        self.assertTrue(semantic_types.contains(domain,1))
        self.assertTrue(semantic_types.contains(domain,'A,B'))
        self.assertFalse(semantic_types.contains(domain,False))
        self.assertFalse(semantic_types.contains(domain,'1'))
        sequence=parse_domain_text('sequence<enum{A,B}>')
        self.assertTrue(semantic_types.contains(sequence,['A','B']))
        self.assertFalse(semantic_types.contains(sequence,['C']))

    def test_nested_enum_rejects_duplicates_and_bad_literals(self):
        for spec in ('enum{A,"A"}','nullable<enum{true,true}>','enum{}',
                     'sequence<enum{"unterminated}>'):
            with self.subTest(spec=spec),self.assertRaises((ValueError,)):
                parse_domain_text(spec)
        self.assertEqual(parse_domain_text('enum{"整数"}')['values'],['整数'])

    def test_nominal_record_stays_unresolved_without_authority(self):
        domain=semantic_types.parse('record<CompanyChange>')
        self.assertFalse(domain['resolved'])
        with self.assertRaises(semantic_types.DomainError):
            semantic_types.contains(domain,{'x':1})

    def test_promotion_rebases_reference_and_preserves_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/'Lifecycle'/'CAT'/'Draft'/'Demo.md'
            src.parent.mkdir(parents=True)
            target=root/'docs'/'requirements.md'
            target.parent.mkdir(parents=True)
            target.write_text('requirement',encoding='utf-8')
            src.write_text(fm('tce','demo.process.tce',[],language='en')+
                           '\n[requirements](../../../docs/requirements.md)\n',encoding='utf-8')
            dst=root/'Docs'/'Processes'/'Demo.md'
            result=promote(src,dst,'decision:approved')
            self.assertEqual(result['status'],'passed')
            self.assertFalse(src.exists())
            self.assertIn('[requirements](../../docs/requirements.md)',dst.read_text())

    def test_promotion_missing_local_link_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/'Lifecycle'/'CAT'/'Draft'/'Demo.md'
            src.parent.mkdir(parents=True)
            original=fm('tce','demo.process.tce',[],language='en')+'\n[missing](../../../docs/absent.md)\n'
            src.write_text(original,encoding='utf-8')
            dst=root/'Docs'/'Processes'/'Demo.md'
            with self.assertRaises(Blocked):promote(src,dst,'decision:approved')
            self.assertEqual(src.read_text(),original)
            self.assertFalse(dst.exists())


    def test_nested_enum_model_conformance_rejects_forged_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t=write_v2(root,False)
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                'input.enabled | receive | boolean | required',
                'input.enabled | receive | boolean | required'+'\n'
                '| input.mode | receive | nullable<enum{A,B}> | required'),encoding='utf-8')
            model=load(p,pi,t,allow_draft=True)
            path=root/'model.json'
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(conformance.validate(p,pi,[t],path,allow_draft=True)['status'],'passed')
            field=next(x for x in model['fields'] if x['id']=='input.mode')
            field['domain']['of']['values']=['A','C']
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=conformance.validate(p,pi,[t],path,allow_draft=True)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('domains',result['mismatches'])


if __name__=='__main__':unittest.main()
