"""Finite closure solver budgets are inconclusive, not semantic violations."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from cat_compile_v2 import Blocked,load
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture


class FiniteBudgetTests(unittest.TestCase):
    def test_larger_than_budget_is_draft_in_shadow_but_blocked_in_normative_mode(self):
        self.check_domain(21, "unproven")

    def test_factorized_domain_detects_real_gap(self):
        self.check_domain(17, "uncovered")

    def check_domain(self, count, expected):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t=write_v2(root,False)
            observations=''.join(
                '| observation.cap'+str(i)+' | synthetic | boolean |\n'
                for i in range(count))
            p.write_text(p.read_text(encoding='utf-8').replace(
                '## Actions',observations+'## Actions'),encoding='utf-8')
            condition='input.enabled and ('+' or '.join(
                'observation.cap'+str(i) for i in range(count))+')'
            t.write_text(t.read_text(encoding='utf-8').replace(
                'submit | `input.enabled` |','submit | `'+condition+'` |'),
                encoding='utf-8')
            for src in (p,pi,t):approve_fixture(src)
            shadow=load(p,pi,t,allow_draft=True,allow_partial=True)
            self.assertEqual(shadow['status'],'draft')
            self.assertEqual(shadow['coverage_requirement'],'partial')
            check=shadow['coverage_checks']['submit']
            self.assertEqual(check['result'],expected)
            if expected=='unproven':
                self.assertEqual(check['combination_count'],2**(count+1))
                self.assertIn('factorized proof budget',check['reason'])
            else:
                # Exactly one admissible state (enabled, all observations false)
                # is not covered. Greater proof capacity must not turn it green.
                self.assertEqual(check['uncovered_count'],1)
                self.assertEqual(check['overlap_count'],0)
                self.assertEqual(check['uncovered'],[{'input.enabled':True,**{
                    'observation.cap'+str(i):False for i in range(count)}}])
            self.assertEqual(len(check['guard_refs']),count+1)
            with self.assertRaisesRegex(
                    Blocked,'assembled Process closed-world coverage requirement not proved'):
                load(p,pi,t,allow_draft=False,allow_partial=False)


if __name__=='__main__':
    unittest.main()
