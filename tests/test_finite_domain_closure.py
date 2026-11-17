"""W07/W08: bounded finite closure and deterministic test selection."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from catlib import semantic_types as types
from cat_compile_v2 import load,selection_vectors,expand_cases
from test_cat_compile_readable import write_v2


class FiniteDomainTests(unittest.TestCase):
    def test_enumerates_only_exact_finite_domains(self):
        self.assertEqual(types.finite_values(types.parse('integer[0..2]')),[0,1,2])
        self.assertEqual(types.finite_values(types.parse('nullable<enum{A,B}>')),[None,'A','B'])
        self.assertEqual(types.finite_values(types.parse('Union<boolean,enum{1,true}>')),[False,True,1])
        self.assertIsNone(types.finite_values(types.parse('real[0..1]')))
        self.assertIsNone(types.finite_values(types.parse('string')))
        self.assertIsNone(types.finite_values(types.parse('integer')))
        self.assertIsNone(types.finite_values(types.parse('integer[0..70000]')))
        self.assertIsNone(types.finite_values(types.parse('sequence<enum{A,B}>')))

    def test_record_product_is_exact_and_capped(self):
        d=types.parse('record<enabled:boolean,mode:enum{A,B}>')
        vals=types.finite_values(d)
        self.assertEqual(len(vals),4)
        self.assertEqual(vals[0],{'enabled':False,'mode':'A'})
        self.assertEqual(vals[-1],{'enabled':True,'mode':'B'})
        self.assertIsNone(types.finite_values(d,max_values=3))

    def test_bounded_integer_closes_and_produces_witnesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,t=write_v2(Path(tmp),False)
            pi.write_text(pi.read_text().replace(
                '| input.enabled | receive | boolean | required |',
                '| input.enabled | receive | integer[0..2] | required |'),encoding='utf-8')
            t.write_text(t.read_text().replace('&#32;',' ').replace(
                '`input.enabled`','`input.enabled > 0`').replace(
                '`not input.enabled`','`input.enabled <= 0`'),encoding='utf-8')
            m=load(p,pi,t,allow_draft=True)
            self.assertEqual(m['coverage_requirement'],'closed')
            self.assertEqual(m['coverage_checks']['submit']['result'],'proved')
            m['status']='confirmed'  # synthetic selector fixture, not source approval
            vec=selection_vectors(m)
            self.assertEqual(len(vec['cases']),2)
            cases=expand_cases(m,vec)
            self.assertEqual({c['source_tce'] for c in cases},{'demo.accept','demo.reject'})
            self.assertTrue(all(c['input']['input.enabled'] in (0,1,2) for c in cases))

    def test_nullable_enum_partition_includes_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,t=write_v2(Path(tmp),False)
            pi.write_text(pi.read_text().replace(
                '| input.enabled | receive | boolean | required |',
                '| input.enabled | receive | nullable<enum{A,B}> | required |'),encoding='utf-8')
            t.write_text(t.read_text().replace(
                '`input.enabled`','`input.enabled == "A"`').replace(
                '`not input.enabled`','`input.enabled != "A"`'),encoding='utf-8')
            m=load(p,pi,t,allow_draft=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'proved')
            m['status']='confirmed'  # synthetic selector fixture, not a normative decision
            v=selection_vectors(m)
            self.assertEqual(len(expand_cases(m,v)),2)

    def test_optional_presence_not_mistaken_for_finite_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,t=write_v2(Path(tmp),False)
            pi.write_text(pi.read_text().replace(
                '| input.enabled | receive | boolean | required |',
                '| input.enabled | receive | boolean | optional |'),encoding='utf-8')
            m=load(p,pi,t,allow_draft=True)
            self.assertEqual(m['coverage_claim'],'partial')
            self.assertIn('input.enabled',m['presence_unproven'])


if __name__=='__main__':unittest.main()
