"""CAT36 W07: exact unbounded string equality/inequality Guard partition."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.cat-system' / 'scripts'), str(ROOT / 'tests')]
from cat_compile_v2 import load, selection_vectors, expand_cases
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture


def fixture(root, first='input.enabled == "known"',
            second='input.enabled != "known"', domain='string'):
    p, pi, tce = write_v2(root, False)
    pi.write_text(pi.read_text(encoding='utf-8').replace(
        '| input.enabled | receive | boolean | required |',
        f'| input.enabled | receive | {domain} | required |'), encoding='utf-8')
    contents = tce.read_text(encoding='utf-8')
    contents = contents.replace('submit | `input.enabled` |',
                                f'submit | `{first}` |').replace(
        'submit | `not input.enabled` |', f'submit | `{second}` |')
    tce.write_text(contents, encoding='utf-8')
    return p, pi, tce


class ExactStringLiteralPartitionTests(unittest.TestCase):
    def test_nonfinite_string_equality_complement_is_proved(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*fixture(Path(td)), allow_draft=True, allow_partial=True)
            check = model['coverage_checks']['submit']
            self.assertEqual(check['result'], 'proved')
            self.assertEqual(check['proof_method'], 'string-literal-equality-partition/v1')
            self.assertEqual(check['abstract_state_count'], 2)
            self.assertEqual(check['partition_fields'], ['input.enabled'])
            self.assertEqual(model['status'], 'draft')  # unapproved Source

    def test_multiple_literals_are_all_distinguished(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*fixture(Path(td),
                first='input.enabled == "a" or input.enabled == "b"',
                second='input.enabled != "a" and input.enabled != "b"'),
                allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'proved')
            self.assertEqual(model['coverage_checks']['submit']['abstract_state_count'], 3)

    def test_missing_string_class_is_uncovered_not_proved(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*fixture(Path(td),
                first='input.enabled == "a"', second='input.enabled == "b"'),
                allow_draft=True, allow_partial=True)
            check = model['coverage_checks']['submit']
            self.assertEqual(check['result'], 'uncovered')
            self.assertIsNone(check['uncovered_count'])
            self.assertEqual(len(check['uncovered']), 1)

    def test_overlapping_string_guards_are_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*fixture(Path(td),
                first='input.enabled == "a"', second='input.enabled != "b"'),
                allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'conflict')

    def test_dynamic_ref_comparison_is_not_falsely_proved(self):
        with tempfile.TemporaryDirectory() as td:
            p, pi, tce = fixture(Path(td),
                first='input.enabled == input.other',
                second='input.enabled != input.other')
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.enabled | receive | string | required |',
                '| input.enabled | receive | string | required |\n'
                '| input.other | receive | string | required |'), encoding='utf-8')
            model = load(p, pi, tce, allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'unproven')

    def test_transform_before_equality_cannot_claim_exact_partition(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*fixture(Path(td),
                first='concat(input.enabled,"x") == "ax"',
                second='concat(input.enabled,"x") != "ax"'),
                allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'unproven')

    def test_formatted_string_domain_is_not_approximated(self):
        with tempfile.TemporaryDirectory() as td:
            model = load(*fixture(Path(td),
                first='input.enabled == "1"', second='input.enabled != "1"',
                domain='string<safe-signed-integer>'),
                allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'unproven')

    def test_independent_source_to_model_conformance_and_witnesses(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources = fixture(root)
            for path in sources: approve_fixture(path)
            model = load(*sources)
            self.assertEqual(model['status'], 'confirmed')
            path = root / 'Model.json'
            path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            conformance = validate(*sources, path)
            self.assertEqual(conformance['status'], 'passed', conformance['mismatches'])
            vectors = selection_vectors(model)
            values = [case['input']['input.enabled'] for case in vectors['cases']]
            self.assertEqual(len(values), 2)
            self.assertEqual({v == 'known' for v in values}, {False, True})
            self.assertTrue(all(type(v) is str for v in values))
            concrete = expand_cases(model, vectors)
            self.assertEqual(len(concrete), 2)

    def test_forged_receipt_is_rejected_by_independent_conformance(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            sources=fixture(root)
            for path in sources:approve_fixture(path)
            model=load(*sources)
            model['coverage_checks']['submit']['abstract_state_count']=1
            path=root/'forged.json'
            path.write_text(json.dumps(model), encoding='utf-8')
            result=validate(*sources,path)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('source_guard_coverage',result['mismatches'])

    def test_literal_is_arbitrary_unicode_text_not_protocol_marker(self):
        with tempfile.TemporaryDirectory() as td:
            model=load(*fixture(Path(td),
                first='input.enabled == "💠"', second='input.enabled != "💠"'),
                allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')


if __name__ == '__main__': unittest.main()
