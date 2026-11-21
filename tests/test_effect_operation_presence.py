"""Effect proofs must respect the accepted PI Operation's Presence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path[:0]=[str(Path(__file__).resolve().parent),
              str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts')]
from cat_compile_v2 import load
from cat_model_conformance import validate
from test_effect_totality import EffectTotalityTests


class EffectOperationPresenceTests(unittest.TestCase):
    def fixture(self,root,base='required',override='optional'):
        p,pi,tce=EffectTotalityTests().fixture(
            root,score_domain='integer[0..1]',output_domain='integer[0..2]',
            effect='input.score')
        pi.write_text(pi.read_text().replace(
            '| input.score | receive | integer[0..1] | required |',
            '| input.score | receive | integer[0..1] | '+base+' |')+
            '\n## Operation presence\n| Operation | Field | Presence |\n'
            '| --- | --- | --- |\n| submit_op | input.score | '+override+' |\n')
        return p,pi,tce

    def test_effect_reads_operation_optional_or_absent_as_nonrequired(self):
        for override in ('optional','absent','undefined'):
            with self.subTest(override=override),tempfile.TemporaryDirectory() as td:
                root=Path(td)
                p,pi,tce=self.fixture(root,override=override)
                model=load(p,pi,tce,allow_partial=True)
                reads={ident:proof for ident,proof in model['effect_checks'].items()
                       if ident.endswith(':output.accepted')}
                self.assertEqual(len(reads),2)
                self.assertTrue(all(proof['result']=='unproven' for proof in reads.values()),reads)
                self.assertTrue(all(ident in model['unverified_effect_ids'] for ident in reads))
                path=root/'Model.json'
                path.write_text(json.dumps(model))
                self.assertEqual(validate(p,pi,tce,path)['status'],'passed')

    def test_independent_source_rejects_forged_positive_with_absent_input(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=self.fixture(root,override='absent')
            model=load(p,pi,tce,allow_partial=True)
            forged={key:{'result':'proved'} for key in model['effect_checks']}
            model['effect_checks']=forged
            model['unverified_effect_ids']=[]
            model['status']='confirmed'
            path=root/'Forged.json'
            path.write_text(json.dumps(model))
            with patch('cat_model_conformance._effect_totality_checks',return_value=forged):
                result=validate(p,pi,tce,path)
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('effect_totality_independent',result['mismatches'])

    def test_required_operation_override_proves_optional_base_read(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=self.fixture(root,base='optional',override='required')
            model=load(p,pi,tce,allow_partial=True)
            reads={k:v for k,v in model['effect_checks'].items()
                   if k.endswith(':output.accepted')}
            self.assertTrue(all(x['result']=='proved' for x in reads.values()),reads)
            self.assertFalse(model['unverified_effect_ids'])
            self.assertEqual(model['status'],'confirmed')
            dest=root/'Model.json'
            dest.write_text(json.dumps(model))
            self.assertEqual(validate(p,pi,tce,dest)['status'],'passed')

    def test_nonselected_provider_override_must_not_change_accepted_presence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,tce=self.fixture(root,base='required',override='required')
            pi.write_text(pi.read_text().replace(
                '| submit_op | accept | submit |',
                '| submit_op | accept | submit |\n| reply_op | provide | submit |').replace(
                '| submit_op | input.score | required |',
                '| submit_op | input.score | required |\n| reply_op | input.score | absent |'))
            model=load(p,pi,tce,allow_partial=True)
            reads={k:v for k,v in model['effect_checks'].items()
                   if k.endswith(':output.accepted')}
            self.assertTrue(all(x['result']=='proved' for x in reads.values()),reads)
            dest=root/'Model.json'
            dest.write_text(json.dumps(model))
            self.assertEqual(validate(p,pi,tce,dest)['status'],'passed')


    def test_ambiguous_accepted_operation_presence_remains_source_consistent(self):
        # The Guard already marks the ambiguous Trigger unproven. Its Effect
        # proof must not silently fall back to base required Presence when
        # one of the accepted Operations explicitly makes the input absent.
        for other_presence,proved in (('absent',False),('required',True)):
            with self.subTest(other_presence=other_presence),tempfile.TemporaryDirectory() as td:
                root=Path(td)
                p,pi,tce=self.fixture(root,base='required',override='required')
                pi.write_text(pi.read_text().replace(
                    '| submit_op | accept | submit |',
                    '| submit_op | accept | submit |\\n| submit_alt | accept | submit |'
                        .replace('\\n','\n')).replace(
                    '| submit_op | input.score | required |',
                    '| submit_op | input.score | required |\\n'
                    '| submit_alt | input.score | '+other_presence+' |'
                        .replace('\\n','\n')))
                model=load(p,pi,tce,allow_partial=True)
                self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')
                reads=[v for k,v in model['effect_checks'].items()
                       if k.endswith(':output.accepted')]
                self.assertEqual(len(reads),2)
                self.assertTrue(all((v['result']=='proved')==proved for v in reads),reads)
                path=root/'Model.json'
                path.write_text(json.dumps(model))
                result=validate(p,pi,tce,path)
                self.assertEqual(result['status'],'passed',result)


if __name__=='__main__':
    unittest.main()
