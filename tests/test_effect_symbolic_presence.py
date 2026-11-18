"""P0: exact nonfinite Effect inclusion and Guard-scoped input Presence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.cat-system'/'scripts'),str(ROOT/'tests')]
from cat_compile_v2 import load,Blocked
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2


def sample(root, *, score='integer', output='integer', expression='input.score + 1',
           presence='required', present_guard=None, absent_expression=None):
    p,pi,tce=write_v2(root,False)
    pi.write_text(pi.read_text().replace(
        '| output.accepted | send | boolean | required |',
        f'| input.score | receive | {score} | {presence} |\n'
        f'| output.accepted | send | {output} | required |'),encoding='utf-8')
    t=tce.read_text()
    t=t.replace('output.accepted = true','output.accepted = '+expression)
    t=t.replace('output.accepted = false',
                'output.accepted = '+(absent_expression if absent_expression is not None else expression))
    if present_guard is not None:
        t=t.replace('`input.enabled`',f'`{present_guard}`')
        t=t.replace('`not input.enabled`',f'`not({present_guard})`')
    tce.write_text(t,encoding='utf-8')
    return p,pi,tce


def snapshot(args):
    p,pi,tce=args
    model=load(p,pi,tce,allow_draft=True,allow_partial=True)
    target=p.parent/'model.json'
    target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
    return model,validate(p,pi,tce,target,allow_draft=True)


class ExactNonfiniteEffectTests(unittest.TestCase):
    def test_unbounded_integer_successor_is_proved_and_source_validated(self):
        with tempfile.TemporaryDirectory() as td:
            model,result=snapshot(sample(Path(td)))
            self.assertTrue(all(x['result']=='proved' for x in model['effect_checks'].values()))
            self.assertTrue(all(x.get('proof_method')=='typed-domain-closure/v1'
                                for key,x in model['effect_checks'].items()
                                if key.endswith('output.accepted')))
            self.assertEqual(result['status'],'passed')

    def test_bounded_successor_still_rejects_overflow(self):
        with tempfile.TemporaryDirectory() as td:
            model,result=snapshot(sample(Path(td),score='integer[0..2]',output='integer[0..2]'))
            self.assertTrue(model['unverified_effect_ids'])
            self.assertTrue(all(x['result']=='unproven' for key,x in model['effect_checks'].items()
                                if key.endswith('output.accepted')))
            self.assertEqual(result['status'],'passed')

    def test_unbounded_integer_lower_limit_can_be_proved(self):
        with tempfile.TemporaryDirectory() as td:
            model,result=snapshot(sample(Path(td),score='integer[0..]',output='integer[1..]'))
            self.assertTrue(all(x['result']=='proved' for x in model['effect_checks'].values()))
            self.assertEqual(result['status'],'passed')

    def test_wrong_target_lower_bound_does_not_prove(self):
        with tempfile.TemporaryDirectory() as td:
            model,_=snapshot(sample(Path(td),score='integer[..3]',output='integer[1..]'))
            self.assertTrue(model['unverified_effect_ids'])

    def test_nonfinite_real_does_not_gain_false_integer_proof(self):
        with tempfile.TemporaryDirectory() as td:
            model,_=snapshot(sample(Path(td),score='real',output='real',expression='input.score + 1'))
            self.assertTrue(model['unverified_effect_ids'])

    def test_typed_set_insertion_is_proved_only_for_matching_elements(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=sample(Path(td),score='string',output='set<string>',
                            expression='set_add(input.current, input.score)')
            pi.write_text(pi.read_text().replace(
                '| input.score | receive | string | required |',
                '| input.current | receive | set<string> | required |\n'
                '| input.score | receive | string | required |'))
            model,result=snapshot((p,pi,tce))
            self.assertTrue(all(x['result']=='proved' for x in model['effect_checks'].values()))
            self.assertEqual(result['status'],'passed')
            pi.write_text(pi.read_text().replace(
                '| input.score | receive | string | required |',
                '| input.score | receive | integer | required |'))
            # The operator is syntactically valid, but an integer element cannot
            # enter a declared string set under the normative type contract.
            rejected=load(p,pi,tce,allow_draft=True,allow_partial=True)
            self.assertTrue(rejected['unverified_effect_ids'])

    def test_tampered_proof_is_rejected_by_source_model_conformance(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=sample(Path(td))
            model,_=snapshot((p,pi,tce))
            model['effect_checks']={key:{'result':'unproven'} for key in model['effect_checks']}
            model_path=Path(td)/'forged.json'
            model_path.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pi,tce,model_path,allow_draft=True)['status'],'blocked')


class PresenceGuardTotalityTests(unittest.TestCase):
    def test_positive_presence_and_absent_alternative_close_guard(self):
        with tempfile.TemporaryDirectory() as td:
            model,result=snapshot(sample(Path(td),score='string',output='string',
                expression='input.score',presence='optional',
                present_guard='is_present(input.score)',absent_expression='"missing"'))
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            self.assertEqual(model['presence_unproven'],[])
            self.assertEqual(model['unverified_effect_ids'],[])
            self.assertEqual(result['status'],'passed')

    def test_without_presence_guard_still_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            model,result=snapshot(sample(Path(td),score='string',output='string',
                expression='input.score',presence='optional'))
            self.assertTrue(model['unverified_effect_ids'])
            self.assertEqual(result['status'],'passed')

    def test_or_with_absent_possible_does_not_prove(self):
        with tempfile.TemporaryDirectory() as td:
            model,_=snapshot(sample(Path(td),score='string',output='string',
                expression='input.score',presence='optional',
                present_guard='is_present(input.score) or input.enabled',
                absent_expression='"missing"'))
            self.assertTrue(model['unverified_effect_ids'])

    def test_another_field_presence_is_not_a_proof(self):
        with tempfile.TemporaryDirectory() as td:
            model,_=snapshot(sample(Path(td),score='string',output='string',
                expression='input.score',presence='optional',
                present_guard='is_present(input.enabled)',absent_expression='"missing"'))
            self.assertTrue(model['unverified_effect_ids'])

    def test_dereference_before_presence_is_not_safe(self):
        with tempfile.TemporaryDirectory() as td:
            model,_=snapshot(sample(Path(td),score='string',output='string',
                expression='input.score',presence='optional',
                present_guard='input.score == "x" and is_present(input.score)',
                absent_expression='"missing"'))
            self.assertTrue(model['unverified_effect_ids'])


if __name__=='__main__':unittest.main()
