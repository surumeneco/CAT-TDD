"""Sound direct integer-reference ordering with unequal intervals and literals.

Atomic direct comparisons use only the order of integer references relative
to one another and to declared literal/domain boundaries. The finite proof is
local Guard truth-class coverage, never initial-state reachable closure.
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
from test_integer_multi_reference_order_partition import multi
from test_intrinsic_rule_proofs import approve_fixture
from test_conformance_runtime import base_work

PROOF = 'integer-reference-range-order-partition/v1'


def mixed(root, *, input_domain='integer[2..]', state_domain='integer[1..1000000]',
          positive='input.version < state.version',
          negative='input.version >= state.version',
          presence='required'):
    p, pi, tce = fixture(root, domain=state_domain,
                         positive=positive, negative=negative, presence=presence)
    original=pi.read_text(encoding='utf-8')
    source='| input.version | receive | ' + state_domain + ' | ' + presence + ' |'
    assert original.count(source)==1
    pi.write_text(original.replace(source,
                 '| input.version | receive | ' + input_domain + ' | ' + presence + ' |'),
                 encoding='utf-8')
    return p,pi,tce


def prove(root, paths):
    for source in paths:
        approve_fixture(source)
    model=load(*paths)
    target=root/'Model.json'
    target.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
    assert validate(*paths, target)['status']=='passed'
    return model


class IntegerReferenceRangePartitionTests(unittest.TestCase):
    def test_different_bounded_and_half_infinite_domains_are_exact(self):
        for left,right in (
            ('integer[2..]', 'integer[1..1000000]'),
            ('integer[..-100]', 'integer[..-101]'),
            ('integer[5..1000000]', 'integer[1..1000000]'),
            ('integer', 'integer[2..]'),
        ):
            with self.subTest(left=left,right=right), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                model=prove(root,mixed(root,input_domain=left,state_domain=right))
                check=model['coverage_checks']['submit']
                self.assertEqual(model['status'],'confirmed')
                self.assertEqual(check['result'],'proved')
                self.assertEqual(check['proof_method'],PROOF)
                self.assertTrue(check['abstract_state_count']>0)
                self.assertEqual(check['partition_fields'],['input.version','state.version'])
                self.assertIn('no-general-reachability-proof',model['limits'])
                cases=expand_cases(model,selection_vectors(model))
                self.assertEqual({case['source_tce'] for case in cases},
                                 {'demo.accept','demo.reject'})

    def test_same_domain_with_a_literal_cut_is_exact(self):
        for yes in (
            'input.version < state.version and input.version < 10',
            '10 < input.version and state.version >= input.version',
            '(input.version == state.version and state.version >= 10) or input.version < 5',
        ):
            with self.subTest(yes=yes), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                model=prove(root,fixture(root,domain='integer[1..1000000]',
                                  positive=yes,negative='not ('+yes+')'))
                check=model['coverage_checks']['submit']
                self.assertEqual(check['result'],'proved')
                self.assertEqual(check['proof_method'],PROOF)
                self.assertEqual(len(expand_cases(model,selection_vectors(model))),2)

    def test_three_reference_mixed_domains_and_literal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            yes='input.version < state.version and state.version <= state.middle and state.middle > 10'
            p,pi,tce=multi(root,domain='integer[1..1000000]',
                         positive=yes,negative='not ('+yes+')')
            original=pi.read_text(encoding='utf-8')
            pi.write_text(original.replace('integer[1..1000000] | required',
                                           'integer[2..1000000] | required'),encoding='utf-8')
            model=prove(root,(p,pi,tce))
            check=model['coverage_checks']['submit']
            self.assertEqual(check['result'],'proved')
            self.assertEqual(check['proof_method'],PROOF)
            self.assertEqual(len(check['partition_fields']),3)
            self.assertEqual(len(expand_cases(model,selection_vectors(model))),2)

    def test_gap_and_conflict_are_reported_without_false_closure(self):
        cases=(
            ('input.version < state.version','input.version > state.version','uncovered'),
            ('input.version <= state.version','input.version >= state.version','conflict'),
        )
        for yes,no,status in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as td:
                model=load(*mixed(Path(td),positive=yes,negative=no),
                           allow_draft=True,allow_partial=True)
                check=model['coverage_checks']['submit']
                self.assertEqual(check['result'],status)
                self.assertEqual(check['proof_method'],PROOF)

    def test_invalid_arithmetic_and_nonrequired_inputs_never_prove(self):
        with tempfile.TemporaryDirectory() as td:
            model=load(*mixed(Path(td),positive='input.version + 1 < state.version',
                            negative='input.version + 1 >= state.version'),
                       allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')
        with tempfile.TemporaryDirectory() as td:
            model=load(*mixed(Path(td),presence='optional'),
                       allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')

    def test_narrow_bounded_domains_do_not_invent_unreachable_combinations(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            model=load(*mixed(root,input_domain='integer[4..4]',
                                   state_domain='integer[5..5]'),
                       allow_draft=True,allow_partial=True)
            check=model['coverage_checks']['submit']
            self.assertEqual(check['result'],'proved')
            self.assertIn('demo.reject',check['unreachable_rules'])

    def test_source_independent_conformance_rejects_forged_range_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            paths=mixed(root)
            model=prove(root,paths)
            model['coverage_checks']['submit']['proof_method']='integer-reference-order-partition/v2'
            target=root/'Model.json'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            verdict=validate(*paths,target)
            self.assertEqual(verdict['status'],'blocked')
            self.assertIn('source_guard_coverage',verdict['mismatches'])

    def test_formal_gate_accepts_true_coverage_and_preserves_gap(self):
        cases=(
            ('complete','input.version >= state.version','passed'),
            ('gap','state.version < input.version and input.version < 10','inconclusive'),
        )
        for label,no,status in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                paths=mixed(root,negative=no)
                for path in paths:
                    approve_fixture(path)
                work=base_work()
                work['id']='synthetic-integer-range-'+label
                work['compilation']={
                    'schema':'cat-compile/v2','process':'Process.md',
                    'pi':'PI.md','tce':'TCE.md','model':'Model.json',
                    'allow_draft':False,'allow_partial':True}
                workpath=root/'Work.json'
                workpath.write_text(json.dumps(work),encoding='utf-8')
                p=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/
                                   '.cat-system'/'scripts'/'cat_flow.py'),
                                  'conformance','--work',str(workpath),
                                  '--kind','process-closure'],
                                 capture_output=True,text=True,check=False,timeout=40)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                self.assertEqual(json.loads(p.stdout)['status'],status)


if __name__=='__main__':
    unittest.main()
