"""Exact local Guard partition for two same-domain integer references."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from cat_compile_v2 import load, selection_vectors, expand_cases
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture
from test_conformance_runtime import base_work


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
    def test_canonical_process_closure_gate_positive_and_fail_closed_counterexamples(self):
        # This is a synthetic Confirmed test fixture, never an approval or
        # proof of a product's Rule/Provider/reachability semantics.
        scenarios = [
            ('complete', {}, 'passed', 0, 'confirmed', 'proved'),
            ('bounded-complete', {'domain':'integer[1..1000000]'}, 'passed', 0, 'confirmed', 'proved'),
            ('overlap', {'negative':'input.version == state.version'}, 'blocked', 2, None, None),
            ('uncovered', {'negative':'false'}, 'blocked', 2, None, None),
            ('unsupported', {'negative':'input.version > state.version'}, 'inconclusive', 0, 'draft', 'unproven'),
        ]
        for label, arguments, verdict, code, model_status, coverage in scenarios:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                source=fixture(root, **arguments)
                for artifact in source: approve_fixture(artifact)
                work=base_work()
                work['id']='synthetic-int-ref-equality-'+label
                work['compilation']={
                    'schema':'cat-compile/v2', 'process':'Process.md',
                    'pi':'PI.md', 'tce':'TCE.md', 'model':'Model.json',
                    'allow_draft':False, 'allow_partial':True,
                }
                work_file=root/'Work.json'
                work_file.write_text(json.dumps(work,ensure_ascii=False),encoding='utf-8')
                command=[sys.executable,
                         str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'/'cat_flow.py'),
                         'conformance','--work',str(work_file),'--kind','process-closure']
                run=subprocess.run(command,capture_output=True,text=True,check=False,timeout=35)
                self.assertEqual(run.returncode,code,run.stderr+run.stdout)
                gate=json.loads(run.stdout)
                self.assertEqual(gate['status'],verdict,gate)
                receipt=json.loads((root/'.cat-flow'/'conformance'/'process-closure.json').read_text(encoding='utf-8'))
                self.assertEqual(receipt['verdict'],verdict)
                self.assertEqual(receipt['reason'],gate['reason'])
                if model_status is None:
                    self.assertIsNone(gate['supporting_evidence'])
                    continue
                model=json.loads((root/'.cat-flow'/'cache'/'process-closure.model.json').read_text(encoding='utf-8'))
                self.assertEqual(model['status'],model_status)
                self.assertEqual(model['coverage_checks']['submit']['result'],coverage)
                self.assertIn('no-general-reachability-proof',model['limits'])
                if verdict=='passed':
                    self.assertEqual(model['coverage_checks']['submit']['proof_method'],
                                     'integer-reference-equality-partition/v1')
                else:
                    self.assertNotEqual(verdict,'passed')

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

    def test_arithmetic_or_optional_input_is_not_proved(self):
        variants=[{'positive':'input.version + 1 == state.version',
                   'negative':'input.version + 1 != state.version'},
                  {'presence':'optional'}]
        for spec in variants:
            with self.subTest(spec=spec),tempfile.TemporaryDirectory() as td:
                model=load(*fixture(Path(td),**spec),allow_draft=True,allow_partial=True)
                self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')

    def test_large_bounded_integer_equality_is_exact_without_enumeration(self):
        with tempfile.TemporaryDirectory() as td:
            source=fixture(Path(td),domain='integer[1..1000000]')
            for artifact in source: approve_fixture(artifact)
            model=load(*source)
            self.assertEqual(model['status'],'confirmed')
            receipt=model['coverage_checks']['submit']
            self.assertEqual(receipt['result'],'proved')
            self.assertEqual(receipt['proof_method'],'integer-reference-equality-partition/v1')
            self.assertEqual(receipt['abstract_state_count'],4)
            path=Path(td)/'Model.json'
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(validate(*source,path)['status'],'passed')
            selected=selection_vectors(model)
            self.assertEqual(len(selected['cases']),2)
            cases=expand_cases(model,selected)
            self.assertEqual({case['input']['input.version']==case['initial_state']['state.version']
                              for case in cases},{True,False})

    def test_upper_only_negative_bound_stays_inside_domain(self):
        with tempfile.TemporaryDirectory() as td:
            source=fixture(Path(td),domain='integer[..-100]')
            for artifact in source: approve_fixture(artifact)
            model=load(*source)
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            self.assertEqual(model['coverage_checks']['submit']['proof_method'],
                             'integer-reference-equality-partition/v1')
            cases=expand_cases(model,selection_vectors(model))
            self.assertEqual(len(cases),2)
            self.assertTrue(all(x<=-100 for case in cases
                                for x in (case['input']['input.version'],case['initial_state']['state.version'])))

    def test_singleton_bounded_domain_does_not_invent_distinct_pair(self):
        with tempfile.TemporaryDirectory() as td:
            source=fixture(Path(td),domain='integer[4..4]')
            model=load(*source,allow_draft=True,allow_partial=True)
            receipt=model['coverage_checks']['submit']
            self.assertIn('demo.reject',receipt['unreachable_rules'])
            self.assertNotEqual(receipt.get('proof_method'),
                                'integer-reference-equality-partition/v1')
            for artifact in source: approve_fixture(artifact)
            work=base_work()
            work['id']='synthetic-bounded-singleton'
            work['compilation']={
                'schema':'cat-compile/v2','process':'Process.md',
                'pi':'PI.md','tce':'TCE.md','model':'Model.json','allow_draft':False,'allow_partial':True,
            }
            work_file=Path(td)/'Work.json'
            work_file.write_text(json.dumps(work),encoding='utf-8')
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'/'cat_flow.py'),
                                   'conformance','--work',str(work_file),'--kind','process-closure'],
                                  capture_output=True,text=True,check=False,timeout=35)
            self.assertEqual(result.returncode,2,result.stderr+result.stdout)
            self.assertEqual(json.loads(result.stdout)['status'],'blocked')

    def test_differing_bounded_domains_and_ordering_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=fixture(Path(td),domain='integer[1..1000000]')
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.version | receive | integer[1..1000000] | required |',
                '| input.version | receive | integer[2..1000000] | required |'),encoding='utf-8')
            model=load(p,pi,tce,allow_draft=True,allow_partial=True)
            self.assertEqual(model['coverage_checks']['submit']['result'],'unproven')
        with tempfile.TemporaryDirectory() as td:
            model=load(*fixture(Path(td),domain='integer[1..1000000]',
                                negative='input.version > state.version'),
                       allow_draft=True,allow_partial=True)
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
