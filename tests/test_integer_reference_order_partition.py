"""Exact local Guard truth partition for ordered pairs of same-domain integers.

The proof is strictly a local truth-class partition, not reachability,
Source Rule meaning, Effect totality, or real Provider conformance.
"""
from __future__ import annotations
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


class IntegerReferenceOrderPartitionTests(unittest.TestCase):
    def test_full_order_partition_compiler_independent_verifier_and_vectors(self):
        # Exact <, =, > truth classes exist for any common interval with >=2
        # integers. All four cross-products of two adjacent values represent
        # the three truth classes without sampling an unbounded Domain.
        scenarios = (
            ('integer[1..1000000]', '<=', '>'),
            ('integer[1..]', '<', '>='),
            ('integer[..-100]', '>', '<='),
            ('integer', '>=', '<'),
        )
        for domain, positive, negative in scenarios:
            with self.subTest(domain=domain, positive=positive), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                sources = fixture(
                    root, domain=domain,
                    positive=f'input.version {positive} state.version',
                    negative=f'input.version {negative} state.version')
                for item in sources:
                    approve_fixture(item)
                model = load(*sources)
                receipt = model['coverage_checks']['submit']
                self.assertEqual(model['status'], 'confirmed')
                self.assertEqual(receipt['result'], 'proved')
                self.assertEqual(receipt['proof_method'], 'integer-reference-order-partition/v1')
                self.assertEqual(receipt['abstract_state_count'], 4)
                self.assertEqual(receipt['partition_fields'], ['input.version', 'state.version'])
                self.assertIn('no-general-reachability-proof', model['limits'])
                model_path = root / 'Model.json'
                model_path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
                self.assertEqual(validate(*sources, model_path)['status'], 'passed')
                vectors = selection_vectors(model)
                cases = expand_cases(model, vectors)
                self.assertEqual({c['source_tce'] for c in cases},
                                 {'demo.accept', 'demo.reject'})
                self.assertEqual(len(cases), 2)

    def test_mixed_equality_and_ordering_is_a_complete_truth_partition(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources = fixture(root, domain='integer[0..1000000]',
                              positive='input.version == state.version or input.version < state.version',
                              negative='input.version > state.version')
            for item in sources:
                approve_fixture(item)
            model = load(*sources)
            receipt = model['coverage_checks']['submit']
            self.assertEqual(receipt['result'], 'proved')
            self.assertEqual(receipt['proof_method'], 'integer-reference-order-partition/v1')
            target = root / 'Model.json'
            target.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(validate(*sources, target)['status'], 'passed')

    def test_order_overlap_and_gap_are_not_proved(self):
        for positive, negative, expected in (
            ('input.version <= state.version', 'input.version >= state.version', 'conflict'),
            ('input.version < state.version', 'input.version > state.version', 'uncovered'),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as td:
                model = load(*fixture(Path(td), domain='integer[1..1000000]',
                                      positive=positive, negative=negative),
                             allow_draft=True, allow_partial=True)
                self.assertEqual(model['coverage_checks']['submit']['result'], expected)
                self.assertEqual(model['coverage_checks']['submit']['proof_method'],
                                 'integer-reference-order-partition/v1')
                self.assertEqual(model['status'], 'draft')

    def test_arithmetic_optional_and_different_domains_remain_unproved(self):
        with tempfile.TemporaryDirectory() as td:
            m = load(*fixture(Path(td), domain='integer[1..1000000]',
                              positive='input.version + 1 <= state.version',
                              negative='input.version + 1 > state.version'),
                     allow_draft=True, allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'], 'unproven')
        with tempfile.TemporaryDirectory() as td:
            m = load(*fixture(Path(td), presence='optional',
                              positive='input.version <= state.version',
                              negative='input.version > state.version'),
                     allow_draft=True, allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'], 'unproven')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p, pi, t = fixture(root, domain='integer[1..1000000]',
                               positive='input.version <= state.version',
                               negative='input.version > state.version')
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.version | receive | integer[1..1000000] | required |',
                '| input.version | receive | integer[2..1000000] | required |'),
                encoding='utf-8')
            m = load(p, pi, t, allow_draft=True, allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'], 'proved')
            self.assertEqual(m['coverage_checks']['submit']['proof_method'],
                             'integer-reference-range-order-partition/v1')

    def test_independent_verifier_rejects_forged_proof_scope(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources = fixture(root, domain='integer[1..1000000]',
                              positive='input.version <= state.version',
                              negative='input.version > state.version')
            for item in sources:
                approve_fixture(item)
            model = load(*sources)
            model['coverage_checks']['submit']['proof_method'] = (
                'integer-reference-equality-partition/v1')
            target = root / 'Model.json'
            target.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
            result = validate(*sources, target)
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('source_guard_coverage', result['mismatches'])

    def test_canonical_process_closure_accepts_complete_order_and_rejects_gap(self):
        for label, positive, negative, code, status in (
            ('complete', 'input.version <= state.version',
             'input.version > state.version', 0, 'passed'),
            ('gap', 'input.version < state.version',
             'input.version > state.version', 0, 'inconclusive'),
        ):
            with self.subTest(case=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                sources = fixture(root, domain='integer[1..1000000]',
                                  positive=positive, negative=negative)
                for item in sources:
                    approve_fixture(item)
                work = base_work()
                work['id'] = 'synthetic-ordered-pair-' + label
                work['compilation'] = {
                    'schema': 'cat-compile/v2', 'process': 'Process.md',
                    'pi': 'PI.md', 'tce': 'TCE.md', 'model': 'Model.json',
                    'allow_draft': False, 'allow_partial': True}
                workpath = root / 'Work.json'
                workpath.write_text(json.dumps(work), encoding='utf-8')
                run = subprocess.run(
                    [sys.executable,
                     str(Path(__file__).resolve().parents[1] /
                         '.cat-system' / 'scripts' / 'cat_flow.py'),
                     'conformance', '--work', str(workpath),
                     '--kind', 'process-closure'],
                    capture_output=True, text=True, check=False, timeout=35)
                self.assertEqual(run.returncode, code, run.stderr + run.stdout)
                report = json.loads(run.stdout)
                self.assertEqual(report['status'], status, report)


if __name__ == '__main__':
    unittest.main()
