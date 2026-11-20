"""Exact local Guard partition for two same-domain, half-infinite integer references."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from cat_compile_v2 import load, selection_vectors, expand_cases
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture


def fixture(root, *, domain='integer[1..]', positive='input.version == state.version',
            negative='input.version != state.version', presence='required'):
    p,pi,tce=write_v2(root,False)
    old=p.read_text(encoding='utf-8')
    assert '| state.ready | boolean |' in old
    p.write_text(old.replace('| state.ready | boolean |',
                             '| state.ready | boolean |\n| state.version | '+domain+' |'), encoding='utf-8')
    old=pi.read_text(encoding='utf-8')
    assert '| input.enabled | receive | boolean | required |' in old
    pi.write_text(old.replace('| input.enabled | receive | boolean | required |',
                              '| input.version | receive | '+domain+' | '+presence+' |'),encoding='utf-8')
    old=tce.read_text(encoding='utf-8')
    assert '`input.enabled`' in old and '`not input.enabled`' in old
    tce.write_text(old.replace('`input.enabled`', '`'+positive+'`').replace('`not input.enabled`',
                              '`'+negative+'`'),encoding='utf-8')
    return p,pi,tce


class IntegerReferenceEqualityPartitionTests(unittest.TestCase):
    def test_half_infinite_version_equality_is_a_complete_boolean_partition(self):
        with tempfile.TemporaryDirectory() as td:
            source=fixture(Path(td))
            for artifact in source: approve_fixture(artifact)
            model=load(*source)
            self.assertEqual(model['status'],'confirmed')
            receipt=model['coverage_checks']['submit']
            self.assertEqual(receipt['result'],'proved')
            self.assertEqual(receipt['proof_method'],'integer-reference-equality-partition/v1')
            self.assertEqual(receipt['partition_fields'],['input.version','state.version'])
            self.assertEqual(receipt['abstract_state_count'],4)
            path=Path(td)/'Model.json'; path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(validate(*source,path)['status'],'passed')
            vectors=selection_vectors(model)
            self.assertEqual(len(vectors['cases']),2)
            cases=expand_cases(model,vectors)
            self.assertEqual({x['source_tce'] for x in cases},{'demo.accept','demo.reject'})
            self.assertEqual({c['input']['input.version']==c['initial_state']['state.version']
                              for c in cases},{True,False})

    def test_missing_or_overlapping_equality_branch_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            model=load(*fixture(Path(td),negative='input.version == state.version'),
                       allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'conflict')
        with tempfile.TemporaryDirectory() as td:
            model=load(*fixture(Path(td),negative='input.version > state.version'),
                       allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')
        with tempfile.TemporaryDirectory() as td:
            model=load(*fixture(Path(td),negative='false'),
                       allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'uncovered')

    def test_arithmetic_optional_input_or_nonmatching_domain_is_not_proved(self):
        variants=[{'positive':'input.version + 1 == state.version',
                   'negative':'input.version + 1 != state.version'},
                  {'presence':'optional'},
                  {'domain':'integer[1..1000000]'}]
        # A large finite interval equality is deliberately not accepted by the
        # special half-infinite proof, even though a stronger solver might exist.
        for spec in variants:
            with self.subTest(spec=spec),tempfile.TemporaryDirectory() as td:
                model=load(*fixture(Path(td),**spec),allow_draft=True,allow_partial=True)
                self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')

    def test_different_half_infinite_bounds_and_literal_mixture_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,t=fixture(Path(td))
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.version | receive | integer[1..] | required |',
                '| input.version | receive | integer[2..] | required |'),encoding='utf-8')
            m=load(p,pi,t,allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'unproven')
        with tempfile.TemporaryDirectory() as td:
            m=load(*fixture(Path(td),positive='input.version == state.version and state.version > 1'),
                   allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'unproven')

    def test_tampered_receipt_does_not_pass_independent_conformance(self):
        with tempfile.TemporaryDirectory() as td:
            source=fixture(Path(td))
            for artifact in source: approve_fixture(artifact)
            model=load(*source)
            model['coverage_checks']['submit']['partition_fields']=[]
            path=Path(td)/'Model.json';path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(validate(*source,path)['status'],'blocked')

if __name__=='__main__':unittest.main()
