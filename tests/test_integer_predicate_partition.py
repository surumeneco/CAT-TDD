"""Exact integer-literal partition for guard closure, never a general solver."""
from __future__ import annotations
import sys, tempfile, unittest, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from cat_compile_v2 import load, selection_vectors
import cat_model_conformance as conformance
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture


def fixture(root, domain='integer', first='input.enabled < 0', second='input.enabled >= 0'):
    p,pi,tce=write_v2(root,False)
    pi.write_text(pi.read_text(encoding='utf-8').replace(
        '| input.enabled | receive | boolean | required |',
        f'| input.enabled | receive | {domain} | required |'),encoding='utf-8')
    tce.write_text(tce.read_text(encoding='utf-8').replace(
        'submit | `input.enabled` |',f'submit | `{first}` |').replace(
        'submit | `not input.enabled` |',f'submit | `{second}` |'),encoding='utf-8')
    return p,pi,tce

class ExactPartitionTests(unittest.TestCase):
    def test_unbounded_integer_split_is_exhaustive_for_literal_comparisons(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load(*fixture(Path(tmp)),allow_draft=True,allow_partial=True)
            c=m['coverage_checks']['submit']
            self.assertEqual(c['result'],'proved')
            self.assertEqual(c.get('proof_method'),'integer-literal-partition/v1')
            self.assertEqual(c['abstract_state_count'],3)
            self.assertEqual(m['status'],'draft')

    def test_large_bounded_integer_does_not_need_one_million_enumerations(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load(*fixture(Path(tmp),'integer[0..1000000]',
                'input.enabled < 400000','input.enabled >= 400000'),
                allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'proved')
            self.assertEqual(m['coverage_checks']['submit']['proof_method'],
                'integer-literal-partition/v1')

    def test_uncovered_single_integer_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load(*fixture(Path(tmp),first='input.enabled < 0',
                second='input.enabled > 0'),allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'uncovered')
            self.assertEqual(m['coverage_checks']['submit']['uncovered'][0]['input.enabled'],0)
            self.assertIsNone(m['coverage_checks']['submit']['uncovered_count'])

    def test_overlap_at_partition_boundary_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load(*fixture(Path(tmp),first='input.enabled <= 0',
                second='input.enabled >= 0'),allow_draft=True,allow_partial=True)
            c=m['coverage_checks']['submit']
            self.assertEqual(c['result'],'conflict')
            self.assertEqual(c['overlaps'][0]['state']['input.enabled'],0)

    def test_arithmetic_guard_remains_unproven(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load(*fixture(Path(tmp),first='input.enabled + 1 < 0',
                second='input.enabled + 1 >= 0'),allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'unproven')

    def test_same_integer_domain_observation_pair_has_exact_order_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t=fixture(root,first='input.enabled < observation.other',
                second='input.enabled >= observation.other')
            p.write_text(p.read_text().replace('## Actions',
                '| observation.other | input | integer |\n## Actions'))
            m=load(p,pi,t,allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'proved')
            self.assertEqual(m['coverage_checks']['submit']['proof_method'],
                             'integer-reference-order-partition/v1')
            self.assertIn('no-general-reachability-proof',m['limits'])

    def test_dynamic_eq_is_not_mistaken_for_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,pi,t=fixture(root,first='input.enabled == input.enabled',
                second='input.enabled != input.enabled')
            m=load(p,pi,t,allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'unproven')

    def test_finite_boolean_baseline_remains_finite(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load(*write_v2(Path(tmp),False),allow_draft=True,allow_partial=True)
            self.assertEqual(m['coverage_checks']['submit']['result'],'proved')
            self.assertNotIn('proof_method',m['coverage_checks']['submit'])

    def test_independent_source_to_model_agrees_on_exact_interval_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sources=fixture(root)
            for src in sources:approve_fixture(src)
            model=load(*sources,allow_draft=False,allow_partial=False)
            model_path=root/'Model.json'
            model_path.write_text(json.dumps(model,sort_keys=True),encoding='utf-8')
            verdict=conformance.validate(*sources,model_path)
            self.assertEqual(verdict['status'],'passed',verdict['mismatches'])

    def test_forged_symbolic_proof_metadata_fails_independent_conformance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sources=fixture(root)
            for src in sources:approve_fixture(src)
            model=load(*sources,allow_draft=False,allow_partial=False)
            model['coverage_checks']['submit']['partition_fields']=[]
            model_path=root/'Model.json'
            model_path.write_text(json.dumps(model,sort_keys=True),encoding='utf-8')
            verdict=conformance.validate(*sources,model_path)
            self.assertEqual(verdict['status'],'blocked')
            self.assertIn('source_guard_coverage',verdict['mismatches'])

    def test_confirmed_integer_partition_can_emit_concrete_rule_witnesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            files=fixture(Path(tmp))
            for src in files: approve_fixture(src)
            m=load(*files,allow_draft=False,allow_partial=False)
            self.assertEqual(m['status'],'confirmed')
            v=selection_vectors(m)
            self.assertEqual({c['id'] for c in v['cases']}, {'case.demo.accept','case.demo.reject'})
            self.assertTrue(all(type(c['input']['input.enabled']) is int for c in v['cases']))

if __name__=='__main__': unittest.main()
