"""W06: preserve actual arbitrary-width integer Domains through both CAT model paths."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
from catlib import semantic_types
import cat_compile_v2 as compiler
import cat_model_conformance as conformance
from test_cat_compile_readable import write_v2


class ArbitraryIntegerModelTests(unittest.TestCase):
    def test_integer_and_enum_domain_roundtrip_and_range_membership(self):
        digits = '9' * 5000
        for literal in ('integer[' + digits + '..' + digits + ']',
                        'enum{' + digits + '}',
                        'nullable<integer[-' + digits + '..' + digits + ']>'):
            with self.subTest(domain=literal[:24]):
                domain = semantic_types.parse(literal)
                semantic_types.validate(domain)
                rendered = compiler.format_domain(domain)
                self.assertEqual(semantic_types.parse(rendered), domain)
                self.assertEqual(compiler.parse_domain_text(rendered), domain)
        enum = semantic_types.parse('enum{' + digits + '}')
        bounded = semantic_types.parse('integer[' + digits + '..' + digits + ']')
        self.assertTrue(semantic_types.contains(bounded, enum['values'][0]))
        self.assertEqual(semantic_types.finite_values(bounded), enum['values'])
        with self.assertRaises(semantic_types.DomainError):
            semantic_types.parse('enum{' + digits + ',' + digits + '}')

    def test_compiler_model_json_and_independent_conformance_preserve_big_int(self):
        digits = '9' * 5000
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            process, pi, tce = write_v2(root, False)
            original = '| state.ready | boolean |'
            self.assertIn(original, process.read_text(encoding='utf-8'))
            process.write_text(process.read_text(encoding='utf-8').replace(
                original, original + '\n| state.counter | integer[' + digits + '..' + digits + '] |'),
                encoding='utf-8')
            model = compiler.load(process, pi, tce, allow_draft=True, allow_partial=True)
            model_path = root / 'Model.json'
            model_path.write_text(compiler._model_content(model, model_path), encoding='utf-8')
            raw = model_path.read_text(encoding='utf-8')
            self.assertIn(digits, raw)
            self.assertEqual(conformance.validate(process, pi, [tce], model_path, allow_draft=True)['status'], 'passed')
            altered = '8' + digits[1:]
            model_path.write_text(raw.replace(digits, altered, 1), encoding='utf-8')
            result = conformance.validate(process, pi, [tce], model_path, allow_draft=True)
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue({'domains', 'fields'} & set(result['mismatches']), result)

    def test_vitest_renderer_blocks_js_precision_loss(self):
        digits = '9' * 5000
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            process, pi, tce = write_v2(root, False)
            old = '| state.ready | boolean |'
            process.write_text(process.read_text(encoding='utf-8').replace(
                old, old + '\n| state.counter | integer[' + digits + '..' + digits + '] |'),
                encoding='utf-8')
            model = compiler.load(process, pi, tce, allow_draft=True, allow_partial=True)
            huge = semantic_types.parse('enum{' + digits + '}')['values'][0]
            vectors = {'schema': compiler.V, 'process': model['process'], 'cases': [
                {'id': 'case.big', 'trigger': 'submit',
                 'input': {'input.enabled': True},
                 'state': {'state.ready': False, 'state.counter': huge}}
            ]}
            binding = root / 'Driver.json'
            binding.write_text(json.dumps({'schema':compiler.D, 'process':model['process'],
                                           'driver':'./driver.ts'}),encoding='utf-8')
            with self.assertRaisesRegex(compiler.Blocked, 'JS safe range'):
                compiler.emit_vitest(model, vectors, binding)

    def test_json_bridge_preserves_large_integer_and_schema(self):
        from catlib import decimal_integer
        n = decimal_integer.parse('9' * 5000)
        value = {'domain': {'type': 'integer', 'min': -n, 'max': n},
                 'enum': [True, n, n + 1], 'naive': '9' * 5000}
        wire = decimal_integer.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
        self.assertIs(type(decimal_integer.loads(wire)['enum'][1]), int)
        self.assertEqual(decimal_integer.loads(wire), value)
        # The byte-oriented canonical JSON path uses the same representation.
        from catlib.common import json_bytes, read_json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'model.json'
            path.write_bytes(json_bytes(value))
            self.assertEqual(read_json(path), value)
        for invalid in ('01', '{"x": 01}', 'NaN--', '1 ' + '2' * 5000):
            with self.subTest(invalid=invalid[:12]):
                with self.assertRaises(ValueError):
                    decimal_integer.loads(invalid)

    def test_default_json_no_regression(self):
        # New bridge must be byte-equivalent to normal JSON for existing small values.
        from catlib import decimal_integer
        value = {'yes': True, 'numbers': [1, 1.0, -17], 'text': '日本語'}
        self.assertEqual(decimal_integer.dumps(value, ensure_ascii=False, sort_keys=True, indent=2),
                         json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
        self.assertEqual(decimal_integer.loads(json.dumps(value)), value)
