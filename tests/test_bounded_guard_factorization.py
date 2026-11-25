"""Exact Guard coverage beyond the direct Cartesian budget; no sampled proof."""
import json
import tempfile
import unittest
from pathlib import Path
from test_projection_unused_typed_sibling import fixture, closure, load, validate, Blocked
from cat_compile_v2 import selection_vectors, expand_cases


def large_fixture(root, gap=False, oversized=False):
    p, pi, tce=fixture(root,'string',guard='input.request == 0',gap=gap)
    upper=2047 if oversized else 1439
    pi.write_text(pi.read_text(encoding='utf8').replace('record<version:integer,metadata:string>',f'integer[0..{upper}]').replace('| output.answer |','| input.extra | receive | integer[0..1023] | required |\n| output.answer |')
                  .replace('## Constraints\n| Expression |\n| --- |','## Constraints\n| Expression |\n| --- |\n| `input.extra >= 0` |'),encoding='utf8')
    return p,pi,tce


class BoundedGuardFactorizationTests(unittest.TestCase):
    def test_large_exact_finite_and_negative(self):
        for gap in (False,True):
            with self.subTest(gap=gap), tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,tce=large_fixture(root,gap=gap)
                model=load(p,pi,tce,allow_partial=True); check=model['coverage_checks']['compare']
                self.assertEqual(check['result'],'uncovered' if gap else 'proved')
                self.assertEqual(check['uncovered_count'],1439*1024 if gap else 0)
                self.assertEqual(check['overlap_count'],0)
                self.assertEqual(len(check['uncovered']),64 if gap else 0)
                out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8')
                self.assertEqual(validate(p,pi,tce,out)['status'],'passed')
                self.assertEqual(closure(root)=='passed',not gap)
                if gap:
                    # A correctly represented partial Model can conform to Source;
                    # it must not be misrepresented as a proof of closure.
                    check.update(result='proved',uncovered_count=0,uncovered=[])
                    out.write_text(json.dumps(model),encoding='utf8')
                    self.assertNotEqual(validate(p,pi,tce,out)['status'],'passed')

    def test_budget_stays_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=large_fixture(Path(td),oversized=True)
            model=load(p,pi,tce,allow_partial=True)
            self.assertEqual(model['coverage_checks']['compare']['result'],'unproven')

    def test_null_partition_and_negative(self):
        for guard,gap,expected in [('input.request == null',False,'proved'),('input.request == null',True,'uncovered'),('input.request == "value"',False,'unproven')]:
            with self.subTest(guard=guard,gap=gap), tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,tce=fixture(root,'string',guard=guard,gap=gap)
                pi.write_text(pi.read_text(encoding='utf8').replace('record<version:integer,metadata:string>','nullable<string>'),encoding='utf8')
                model=load(p,pi,tce,allow_partial=True);check=model['coverage_checks']['compare']
                self.assertEqual(check['result'],expected)
                out=root/'Model.json';out.write_text(json.dumps(model),encoding='utf8')
                if expected=='proved':
                    self.assertEqual(check['proof_method'],'nullable-string-null-partition/v1')
                    self.assertEqual(check['abstract_state_count'],2)
                    self.assertEqual(validate(p,pi,tce,out)['status'],'passed')
                    self.assertEqual(closure(root),'passed')
                    # Only concrete, legal input values may reach test selection.
                    cases=expand_cases(model,selection_vectors(model))
                    self.assertEqual({c['input']['input.request'] for c in cases},{None,''})
                else:
                    self.assertNotEqual(closure(root),'passed')

if __name__=='__main__':unittest.main()
