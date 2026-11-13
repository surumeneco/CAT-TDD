"""Required PI outputs must be emitted by every TCE alternative.

The obligation exists even when every output is required and no explicit
PI provide operation is declared. Source Model Conformance cannot trust a
forged presence_unproven=[] or confirmed status for an incomplete Effect.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.cat-system'/'scripts'),str(ROOT/'tests')]
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture
from cat_compile_v2 import load
from cat_model_conformance import validate


class RequiredOutputClosureTests(unittest.TestCase):
    def setup_sources(self,root,omit):
        p,pi,tce=write_v2(root,False)
        for f in (p,pi,tce):
            approve_fixture(f)
        if omit:
            tce.write_text(
                tce.read_text(encoding='utf-8').replace(
                    'output.accepted = false','state.ready = false'),
                encoding='utf-8')
        return p,pi,tce

    def test_missing_required_output_keeps_finite_guard_model_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,tce=self.setup_sources(Path(tmp),True)
            model=load(p,pi,tce,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            self.assertEqual(model['status'],'draft')
            self.assertIn('output.accepted',model['presence_unproven'])
            target=Path(tmp)/'Model.json'
            target.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target)['status'],'passed')

    def test_forged_required_output_closure_is_rejected_by_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,tce=self.setup_sources(Path(tmp),True)
            model=load(p,pi,tce,allow_partial=True)
            model.update(status='confirmed',coverage_requirement='closed',
                         coverage_claim='closed',presence_unproven=[])
            target=Path(tmp)/'Model.json'
            target.write_text(json.dumps(model),encoding='utf-8')
            result=validate(p,pi,tce,target)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('source_output_presence',result['mismatches'])
            self.assertIn('normative_status_unjustified',result['mismatches'])

    def test_source_output_gap_cannot_be_substituted_with_another_valid_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,tce=self.setup_sources(Path(tmp),True)
            model=load(p,pi,tce,allow_partial=True)
            self.assertIn('output.accepted',model['presence_unproven'])
            model['presence_unproven']=['state.ready']
            target=Path(tmp)/'Model.json'
            target.write_text(json.dumps(model),encoding='utf-8')
            result=validate(p,pi,tce,target)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('source_output_presence',result['mismatches'])

    def test_source_output_gap_does_not_accept_forged_or_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,tce=self.setup_sources(Path(tmp),True)
            original=load(p,pi,tce,allow_partial=True)
            target=Path(tmp)/'Model.json'
            for pending in (['imaginary.output'],
                            ['output.accepted','output.accepted']):
                with self.subTest(pending=pending):
                    forged=dict(original)
                    forged['presence_unproven']=pending
                    target.write_text(json.dumps(forged),encoding='utf-8')
                    result=validate(p,pi,tce,target)
                    self.assertEqual(result['status'],'blocked',result)
                    self.assertIn('source_output_presence',result['mismatches'])

    def test_required_outputs_without_provide_operation_remain_valid_when_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,tce=self.setup_sources(Path(tmp),False)
            model=load(p,pi,tce)
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['presence_unproven'],[])
            target=Path(tmp)/'Model.json'
            target.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,target)['status'],'passed')


if __name__=='__main__':
    unittest.main()
