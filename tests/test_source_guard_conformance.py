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

    def test_valid_source_model_remains_confirmed(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.prepare(Path(td),uncovered=False)
            m=load(p,pi,tce)
            self.assertEqual(m['status'],'confirmed')
            target=Path(td)/'Model.json';target.write_text(json.dumps(m),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target)['status'],'passed')

if __name__=='__main__':unittest.main()
