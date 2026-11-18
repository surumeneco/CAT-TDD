"""CAT33 isolated: irrelevant optional input must not force enumerating all strings."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.cat-system' / 'scripts'), str(ROOT / 'tests')]
from cat_compile_v2 import load, selection_vectors
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture


def fixture(root):
    process, pi, tce = write_v2(root, False)
    pi.write_text(pi.read_text('utf-8').replace(
        '| input.enabled | receive | boolean | required |',
        '| input.enabled | receive | boolean | required |\n'
        '| input.unused | receive | string | optional |'), encoding='utf-8')
    for path in (process, pi, tce):
        approve_fixture(path)
    return process, pi, tce


class UnusedOptionalNonfiniteTests(unittest.TestCase):
    def test_unused_optional_string_is_independent_of_guards_and_source_validated(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            process, pi, tce = fixture(root)
            model = load(process, pi, tce)
            self.assertEqual(model['status'], 'confirmed')
            self.assertEqual(model['coverage_checks']['submit']['result'], 'proved')
            self.assertEqual(model['coverage_checks']['submit']['guard_refs'], ['input.enabled'])
            self.assertEqual(model['presence_unproven'], [])
            model_path = root / 'Model.json'
            model_path.write_text(json.dumps(model), encoding='utf-8')
            self.assertEqual(validate(process, pi, tce, model_path)['status'], 'passed')
            vectors = selection_vectors(model)
            self.assertEqual(len(vectors['cases']), 2)
            self.assertTrue(all('input.unused' not in c['input'] for c in vectors['cases']))

    def test_used_optional_string_is_not_proved_without_full_coverage_reasoning(self):
        with tempfile.TemporaryDirectory() as d:
            process, pi, tce = fixture(Path(d))
            old = tce.read_text('utf-8')
            tce.write_text(old.replace('`input.enabled`',
                 '`input.enabled and is_present(input.unused)`').replace(
                 '`not input.enabled`', '`not(input.enabled and is_present(input.unused))`'),
                 encoding='utf-8')
            model = load(process, pi, tce, allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'unproven')
            self.assertIn('input.unused', model['presence_unproven'])


if __name__ == '__main__': unittest.main()
