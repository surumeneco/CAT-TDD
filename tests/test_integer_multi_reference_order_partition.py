"""Exact local truth partitions for three to five integer references.

An order-preserving re-ranking of a finite tuple preserves every direct
==/!=/</<=/>/>= comparison. This is not an initial-state reachability proof.
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
from cat_compile_v2 import load, selection_vectors, expand_cases
from cat_model_conformance import validate
from test_integer_reference_equality_partition import fixture
from test_intrinsic_rule_proofs import approve_fixture
from test_conformance_runtime import base_work

EXTRA = ('state.middle', 'state.extra', 'state.fifth')


def multi(root, *, count=3, domain='integer[1..1000000]',
          positive=None, negative=None, presence='required'):
    if positive is None:
        ids = ['input.version', 'state.version', *EXTRA[:count-2]]
        parts = [f'{ids[i]} < {ids[i+1]}' for i in range(count-1)]
        positive = ' and '.join(parts)
    if negative is None:
        negative = 'not (' + positive + ')'
    paths = fixture(root, domain=domain, positive=positive,
                    negative=negative, presence=presence)
    process, pi, tce = paths
    source = process.read_text(encoding='utf-8')
    anchor = '| state.version | ' + domain + ' |'
    assert source.count(anchor) == 1
    added = ''.join('\n| ' + name + ' | ' + domain + ' |'
                    for name in EXTRA[:count-2])
    process.write_text(source.replace(anchor, anchor + added), encoding='utf-8')
    return paths


def prove(root, paths):
    for source in paths:
        approve_fixture(source)
    model = load(*paths)
    target = root / 'Model.json'
    target.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
    assert validate(*paths, target)['status'] == 'passed'
    return model


class ExactMultiReferenceIntegerPartitionTests(unittest.TestCase):
    def test_three_four_five_reference_full_order_partition(self):
        for count, expected in ((3, 27), (4, 256), (5, 3125)):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                paths = multi(root, count=count)
                model = prove(root, paths)
                proof = model['coverage_checks']['submit']
                self.assertEqual(model['status'], 'confirmed')
                self.assertEqual(proof['result'], 'proved')
                self.assertEqual(proof['proof_method'], 'integer-reference-order-partition/v2')
                self.assertEqual(proof['abstract_state_count'], expected)
                self.assertEqual(len(proof['partition_fields']), count)
                self.assertIn('no-general-reachability-proof', model['limits'])
                cases = expand_cases(model, selection_vectors(model))
                self.assertEqual({c['source_tce'] for c in cases},
                                 {'demo.accept', 'demo.reject'})

    def test_three_reference_equality_only_partition(self):
        positive = 'input.version == state.version and state.version != state.middle'
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model = prove(root, multi(root, positive=positive))
            proof = model['coverage_checks']['submit']
            self.assertEqual(proof['proof_method'], 'integer-reference-equality-partition/v2')
            self.assertEqual(proof['abstract_state_count'], 27)
            self.assertEqual(proof['result'], 'proved')

    def test_upper_bounded_negative_domain_uses_only_admissible_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model = prove(root, multi(root, domain='integer[..-100]'))
            proof = model['coverage_checks']['submit']
            self.assertEqual(proof['abstract_state_count'], 27)
            cases = expand_cases(model, selection_vectors(model))
            for case in cases:
                self.assertTrue(all(x <= -100
                    for key, x in {**case['input'], **case['initial_state']}.items()
                    if key in ('input.version', 'state.middle', 'state.version')))

    def test_comparison_truth_classes_equal_full_finite_domain(self):
        # Exhaustive independent check: only pairwise order types matter.
        def signature(values):
            return tuple((values[i] > values[j]) - (values[i] < values[j])
                         for i in range(len(values)) for j in range(i+1, len(values)))
        for count in (3, 4, 5):
            with self.subTest(count=count):
                actual = {signature(x) for x in itertools.product(range(count+1), repeat=count)}
                abstract = {signature(x) for x in itertools.product(range(count), repeat=count)}
                self.assertEqual(abstract, actual)

    def test_bounded_two_value_domain_never_invents_three_distinct_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = multi(root, domain='integer[4..5]')
            model = load(*paths, allow_draft=True, allow_partial=True)
            proof = model['coverage_checks']['submit']
            # The remaining rule covers every feasible state, but the
            # strict triple ordering is unreachable in a two-value Domain.
            # Guard coverage and Rule reachability are separate claims.
            self.assertEqual(proof['result'], 'proved')
            self.assertIn('demo.accept', proof['unreachable_rules'])
            self.assertNotEqual(proof.get('proof_method'), 'integer-reference-order-partition/v2')

    def test_overlap_and_uncovered_remain_nonproved(self):
        cases = (
            ('input.version < state.middle', 'state.middle < state.version', 'conflict'),
            ('input.version < state.middle and state.middle < state.version',
             'input.version > state.middle and state.middle > state.version', 'uncovered'),
        )
        for yes, no, verdict in cases:
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as td:
                model = load(*multi(Path(td), positive=yes, negative=no),
                             allow_draft=True, allow_partial=True)
                receipt = model['coverage_checks']['submit']
                self.assertEqual(receipt['result'], verdict)
                self.assertEqual(receipt['proof_method'], 'integer-reference-order-partition/v2')

    def test_arithmetic_optional_and_mixed_domains_remain_unproven(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            positive = 'input.version + 1 < state.middle and state.middle < state.version'
            model = load(*multi(root, positive=positive),
                         allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'unproven')
        with tempfile.TemporaryDirectory() as td:
            model = load(*multi(Path(td), presence='optional'),
                         allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'unproven')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, pi, tce = multi(root)
            old = pi.read_text(encoding='utf-8')
            pi.write_text(old.replace('integer[1..1000000] | required',
                                      'integer[2..1000000] | required'),
                          encoding='utf-8')
            model = load(p, pi, tce, allow_draft=True, allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'], 'proved')
            self.assertEqual(model['coverage_checks']['submit']['proof_method'],
                             'integer-reference-range-order-partition/v1')

    def test_independent_source_verifier_rejects_forged_partition_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = multi(root, count=4)
            model = prove(root, paths)
            model['coverage_checks']['submit']['proof_method'] = 'integer-reference-order-partition/v1'
            path = root / 'Model.json'
            path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            verdict = validate(*paths, path)
            self.assertEqual(verdict['status'], 'blocked')
            self.assertIn('source_guard_coverage', verdict['mismatches'])

    def test_canonical_formal_gate_passes_complete_and_keeps_gap_inconclusive(self):
        for label, negative, expected in (
            ('complete', None, 'passed'),
            ('gap', 'input.version > state.middle and state.middle > state.version', 'inconclusive'),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                paths = multi(root, negative=negative)
                for path in paths:
                    approve_fixture(path)
                work = base_work()
                work['id'] = 'synthetic-integer-multi-' + label
                work['compilation'] = {
                    'schema': 'cat-compile/v2', 'process': 'Process.md',
                    'pi': 'PI.md', 'tce': 'TCE.md', 'model': 'Model.json',
                    'allow_draft': False, 'allow_partial': True,
                }
                path = root / 'Work.json'
                path.write_text(json.dumps(work), encoding='utf-8')
                cmd = [sys.executable,
                       str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts' / 'cat_flow.py'),
                       'conformance', '--work', str(path), '--kind', 'process-closure']
                run = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=40)
                self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
                self.assertEqual(json.loads(run.stdout)['status'], expected)


if __name__ == '__main__':
    unittest.main()
