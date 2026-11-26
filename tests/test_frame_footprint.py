"""The Frame predicate proves declared Outcomes, never live provider execution."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from test_structural_copy_relation import fixture, flow, load, validate


class FrameFootprintTests(unittest.TestCase):
    def test_formal_gate_and_independent_source_reconstruction(self):
        for variant in ('positive', 'wrong-peer', 'wrong-provide', 'missing-required',
                        'extra-forbidden', 'state-write', 'empty-scope', 'different-trigger',
                        'wrong-accept', 'wrong-guard', 'two-outcomes'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as td:
                d = Path(td)
                p, pi, tce, spec = fixture(d)
                p.write_text(p.read_text().replace('| --- | --- |\n## Observations',
                    '| --- | --- |\n| state.saved | boolean |\n## Observations').replace(
                    '| --- | --- | --- |\n## Triggers',
                    '| --- | --- | --- |\n| action.extra | extra | boolean |\n## Triggers'), encoding='utf-8')
                scope = {'trigger':'receive', 'pi':'copyprobe.pi', 'accept':'request',
                         'peer':'copycaller', 'cases':[{'when':'true', 'provide':'reply',
                         'required':['output.items'], 'allowed':['output.items']}]}
                case = scope['cases'][0]
                if variant == 'wrong-peer': scope['peer'] = 'othercaller'
                if variant == 'wrong-provide': case['provide'] = None
                if variant == 'missing-required':
                    case['required'].append('action.extra'); case['allowed'].append('action.extra')
                if variant == 'extra-forbidden':
                    tce.write_text(tce.read_text().replace('output.items = input.items',
                        'output.items = input.items; action.extra = true'), encoding='utf-8')
                if variant == 'state-write':
                    tce.write_text(tce.read_text().replace('output.items = input.items',
                        'output.items = input.items; state.saved = not state.saved'), encoding='utf-8')
                if variant == 'empty-scope': scope['cases'] = []
                if variant == 'different-trigger': scope['trigger'] = 'unknown'
                if variant == 'wrong-accept': scope['accept'] = 'unknown'
                if variant == 'wrong-guard': case['when'] = 'false'
                if variant == 'two-outcomes':
                    tce.write_text(tce.read_text() + '| copy | receive | `true` | 2 | `output.items = input.other; state.saved = state.saved` |\n', encoding='utf-8')
                spec.write_text(spec.read_text().split('| exact-copy |')[0] +
                    f'| exact-frame | trigger-frame-footprint {json.dumps(scope,separators=(",",":"))} | @cat:trigger-frame-footprint/v1 | cat:intrinsic-model/v1 |\n', encoding='utf-8')
                expected = 'passed' if variant in ('positive','two-outcomes') else 'inconclusive'
                run, result = flow(d,'conformance','--kind','process-closure')
                self.assertEqual(result['status'], expected, (run.stdout, run.stderr))
                model = load(p,pi,tce,domain_specs=[spec],allow_partial=True)
                model_path = d/'Independent.json'
                model_path.write_text(json.dumps(model),encoding='utf-8')
                self.assertEqual(validate(p,pi,tce,model_path,domain_specs=[spec])['status'],'passed')
                self.assertEqual(bool(model['intrinsic_rule_proofs']),expected=='passed')
                if expected == 'passed':
                    forged=copy.deepcopy(model)
                    forged['intrinsic_rule_proofs'][0]['source_sha256']='0'*64
                    model_path.write_text(json.dumps(forged),encoding='utf-8')
                    self.assertNotEqual(validate(p,pi,tce,model_path,domain_specs=[spec])['status'],'passed')
