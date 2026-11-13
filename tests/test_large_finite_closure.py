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
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t=write_v2(root,False)
            observations=''.join(
                '| observation.cap'+str(i)+' | synthetic | boolean |\n'
                for i in range(17))
            p.write_text(p.read_text(encoding='utf-8').replace(
                '## Actions',observations+'## Actions'),encoding='utf-8')
            condition='input.enabled and ('+' or '.join(
                'observation.cap'+str(i) for i in range(17))+')'
            t.write_text(t.read_text(encoding='utf-8').replace(
                'submit | `input.enabled` |','submit | `'+condition+'` |'),
                encoding='utf-8')
            for src in (p,pi,t):approve_fixture(src)
            shadow=load(p,pi,t,allow_draft=True,allow_partial=True)
            self.assertEqual(shadow['status'],'draft')
            self.assertEqual(shadow['coverage_requirement'],'partial')
            check=shadow['coverage_checks']['submit']
            self.assertEqual(check['result'],'unproven')
            self.assertEqual(check['combination_count'],262144)
            self.assertIn('65536',check['reason'])
            self.assertEqual(len(check['guard_refs']),18)
            with self.assertRaisesRegex(
                    Blocked,'assembled Process closed-world coverage requirement not proved'):
                load(p,pi,t,allow_draft=False,allow_partial=False)


if __name__=='__main__':
    unittest.main()
