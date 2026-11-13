"""An independently compared Source must not inherit a forged Guard proof."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.cat-system'/'scripts'),str(ROOT/'tests')]
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture
from cat_compile_v2 import load
from cat_model_conformance import validate

class SourceGuardConformanceTests(unittest.TestCase):
    def prepare(self,root,uncovered):
        p,pi,tce=write_v2(root,False)
        for f in (p,pi,tce):approve_fixture(f)
        if uncovered:
            tce.write_text('\n'.join(x for x in tce.read_text().splitlines()
                                     if '| demo.reject |' not in x)+'\n',encoding='utf-8')
        return p,pi,tce

    def test_incomplete_source_cannot_forge_coverage_and_confirmed_model(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.prepare(Path(td),uncovered=True)
            m=load(p,pi,tce,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'uncovered')
            m['status']='confirmed';m['coverage_requirement']='closed';m['coverage_claim']='closed'
            m['coverage_checks']['submit']['result']='proved'
            dest=Path(td)/'Model.json';dest.write_text(json.dumps(m),encoding='utf-8')
            result=validate(p,pi,tce,dest)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('source_guard_coverage',result['mismatches'])
            self.assertIn('normative_status_unjustified',result['mismatches'])

    def test_uncovered_source_draft_cannot_forge_local_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.prepare(Path(td),uncovered=True)
            m=load(p,pi,tce,allow_partial=True)
            target=Path(td)/'Model.json';target.write_text(json.dumps(m),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target)['status'],'passed')
            m['coverage_checks']['submit']['result']='proved'
            target.write_text(json.dumps(m),encoding='utf-8')
            self.assertIn('source_guard_coverage',validate(p,pi,tce,target)['mismatches'])

    def test_uncovered_counterexamples_counts_and_unreachable_ids_are_source_bound(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.prepare(Path(td),uncovered=True)
            m=load(p,pi,tce,allow_partial=True)
            target=Path(td)/'Model.json'
            key='submit'
            actual=m['coverage_checks'][key]
            self.assertEqual(actual['result'],'uncovered')
            self.assertGreater(actual['uncovered_count'],0)
            for field,corrupted in (
                ('uncovered_count',0),
                ('uncovered',[]),
                ('unreachable_rules',['phantom.rule']),
                ('guard_refs',[]),
                ('excluded_by_pi_constraints',True),
            ):
                with self.subTest(field=field):
                    forged=json.loads(json.dumps(m))
                    forged['coverage_checks'][key][field]=corrupted
                    target.write_text(json.dumps(forged),encoding='utf-8')
                    result=validate(p,pi,tce,target)
                    self.assertEqual(result['status'],'blocked',result)
                    self.assertIn('source_guard_coverage',result['mismatches'])

    def test_confirmed_guard_receipt_cannot_add_undocumented_witness(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.prepare(Path(td),uncovered=False)
            m=load(p,pi,tce)
            m['coverage_checks']['submit']['uncovered']=[{'input.enabled':False}]
            target=Path(td)/'Model.json';target.write_text(json.dumps(m))
            result=validate(p,pi,tce,target)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('source_guard_coverage',result['mismatches'])

    def test_valid_source_model_remains_confirmed(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.prepare(Path(td),uncovered=False)
            m=load(p,pi,tce)
            self.assertEqual(m['status'],'confirmed')
            target=Path(td)/'Model.json';target.write_text(json.dumps(m),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target)['status'],'passed')

if __name__=='__main__':unittest.main()
