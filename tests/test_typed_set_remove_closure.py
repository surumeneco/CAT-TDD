"""CAT37 regression: removing an element preserves a typed nonfinite set domain.

These are Compiler/Model proof tests, not evidence of external effects or a
product Process Closure gate.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / '.cat-system' / 'scripts')]
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load
from cat_model_conformance import validate


class TypedSetRemoveClosureTests(unittest.TestCase):
    def fixture(self, root, element_domain='string', state_domain='set<string>',
                presence='required', source='state.members', item='input.member'):
        process, pi, tce = write_v2(root, False)
        process.write_text(process.read_text(encoding='utf-8').replace(
            '| state.ready | boolean |',
            '| state.members | ' + state_domain + ' |'), encoding='utf-8')
        pi.write_text(pi.read_text(encoding='utf-8').replace(
            '| output.accepted | send | boolean | required |',
            '| input.member | receive | ' + element_domain + ' | ' + presence + ' |\n'
            '| output.accepted | send | boolean | required |'), encoding='utf-8')
        tce.write_text(tce.read_text(encoding='utf-8').replace(
            'state.ready = true',
            'state.members = set_remove(' + source + ', ' + item + ')'),
            encoding='utf-8')
        if source == 'input.source':
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.member | receive |',
                '| input.source | receive | set<string> | required |\\n'
                '| input.member | receive |', 1), encoding='utf-8')
        return process, pi, tce

    def effect(self, model):
        checks = {key: value for key, value in model['effect_checks'].items()
                  if key.endswith(':state.members')}
        self.assertEqual(len(checks), 1, checks)
        return next(iter(checks.values()))

    def test_nonfinite_string_set_removal_proves_domain_membership(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            process, pi, tce = self.fixture(root)
            model = load(process, pi, tce, allow_draft=True, allow_partial=True)
            self.assertEqual(self.effect(model), {
                'result': 'proved', 'proof_method': 'typed-domain-closure/v1'})
            path = root / 'Model.json'
            path.write_text(json.dumps(model), encoding='utf-8')
            self.assertEqual(
                validate(process, pi, tce, path, allow_draft=True)['status'], 'passed')
            forged = json.loads(path.read_text(encoding='utf-8'))
            forged['effect_checks'] = {key: {'result': 'unproven', 'reason': 'forged'}
                                       for key in model['effect_checks']}
            path.write_text(json.dumps(forged), encoding='utf-8')
            result = validate(process, pi, tce, path, allow_draft=True)
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('effect_checks', result['mismatches'])

    def test_nonfinite_integer_set_removal_preserves_typed_membership(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*self.fixture(Path(td), element_domain='integer',
                                       state_domain='set<integer>'),
                         allow_draft=True, allow_partial=True)
            self.assertEqual(self.effect(model)['result'], 'proved')

    def test_nonfinite_removal_rejects_wrong_element_type(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*self.fixture(Path(td), element_domain='integer'),
                         allow_draft=True, allow_partial=True)
            self.assertEqual(self.effect(model)['result'], 'unproven')

    def test_nonfinite_removal_rejects_wrong_target_domain(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*self.fixture(Path(td), state_domain='set<integer>',
                                       source='input.source'),
                         allow_draft=True, allow_partial=True)
            self.assertEqual(self.effect(model)['result'], 'unproven')

    def test_nonfinite_removal_with_missing_optional_item_is_unproven(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*self.fixture(Path(td), presence='optional'),
                         allow_draft=True, allow_partial=True)
            self.assertEqual(self.effect(model)['result'], 'unproven')
            self.assertIn('Presence', self.effect(model)['reason'])

    def test_nonfinite_removal_from_unavailable_source_never_proves(self):
        with tempfile.TemporaryDirectory() as td:
            # Output cannot be an input to an Effect expression.
            with self.assertRaises(ValueError):
                load(*self.fixture(Path(td), source='output.accepted'),
                     allow_draft=True, allow_partial=True)


if __name__ == '__main__':
    unittest.main()
