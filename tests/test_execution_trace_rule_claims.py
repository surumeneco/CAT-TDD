"""A trace's optional Rule/Outcome declarations must match its fixed Model."""
from __future__ import annotations
import unittest
from test_execution_trace_diagnostic import payload, diagnose
import cat_execution_trace_diagnostic as diagnostic


def source_bound():
    model,trace=payload()
    model['source_records'].append({'id':'demo.tce','kind':'tce','sha256':'b'*64})
    model['rules']=[{'id':'sync_rule','source_artifact':'demo.tce',
                     'allowed':[{'write':[{'target':'action.replace','expr':{'literal':True}}]}]}]
    trace['source_sha256']['demo.tce']='b'*64
    return model,trace


class RuleClaimTests(unittest.TestCase):
    def test_unknown_effect_rule_id_must_not_be_consistent(self):
        m,t=source_bound()
        t['events'][4].update(rule_id='foreign_rule',outcome_index=1)
        with self.assertRaisesRegex(diagnostic.TraceError,'unknown (trace )?Rule'):
            diagnose(m,t)

    def test_out_of_range_terminal_allowed_outcome_must_not_be_consistent(self):
        m,t=source_bound()
        t['events'][5].update(rule_id='sync_rule',outcome_index=2)
        with self.assertRaisesRegex(diagnostic.TraceError,'(?:Allowed|allowed) Outcome'):
            diagnose(m,t)

    def test_out_of_range_effect_allowed_outcome_must_not_be_consistent(self):
        m,t=source_bound()
        t['events'][4].update(rule_id='sync_rule',outcome_index=3)
        with self.assertRaisesRegex(diagnostic.TraceError,'(?:Allowed|allowed) Outcome'):
            diagnose(m,t)

    def test_valid_model_bound_claims_remain_structurally_consistent_not_normative_proof(self):
        m,t=source_bound()
        t['events'][4].update(rule_id='sync_rule',outcome_index=1)
        t['events'][5].update(rule_id='sync_rule',outcome_index=1)
        result=diagnose(m,t)
        self.assertEqual(result['trace_integrity'],'consistent')
        self.assertEqual(result['normative_status'],'inconclusive')
        self.assertEqual(result['external_effect_proof'],'not-run')

    def test_same_execution_rule_cannot_claim_two_allowed_outcomes(self):
        m,t=source_bound()
        # Both outcome IDs are valid for the same pinned Rule; the
        # contradiction is selecting both in one logical execution.
        m['rules'][0]['allowed'].append({'write':[{'target':'action.replace',
                                                   'expr':{'literal':False}}]})
        t['events'][4].update(rule_id='sync_rule',outcome_index=1)
        t['events'][5].update(rule_id='sync_rule',outcome_index=2)
        with self.assertRaisesRegex(diagnostic.TraceError,'conflicting Allowed Outcome'):
            diagnose(m,t)

    def test_distinct_rules_may_report_different_allowed_outcomes_in_one_run(self):
        m,t=source_bound()
        m['rules'].append({'id':'another_rule','source_artifact':'demo.tce',
                           'allowed':[{'write':[]},{'write':[]}]})
        t['events'][4].update(rule_id='sync_rule',outcome_index=1)
        t['events'][5].update(rule_id='another_rule',outcome_index=2)
        self.assertEqual(diagnose(m,t)['trace_integrity'],'consistent')

    def test_same_rule_can_have_different_outcomes_across_separate_runs(self):
        m,t=source_bound()
        m['rules'][0]['allowed'].append({'write':[]})
        t['events'][4].update(rule_id='sync_rule',outcome_index=1)
        t['events'][5].update(rule_id='sync_rule',outcome_index=1)
        t['runs'].append({'execution_id':'run-2','entry_operation':'manual','peer':'command'})
        t['events'].extend([
            {'event_id':'other-start','execution_id':'run-2','kind':'trigger',
             'operation':'manual','peer':'command'},
            {'event_id':'other-result','execution_id':'run-2','kind':'result',
             'parent_event_id':'other-start','operation':'manual_result',
             'peer':'command','outcome':'failure','rule_id':'sync_rule',
             'outcome_index':2}])
        self.assertEqual(diagnose(m,t)['trace_integrity'],'consistent')

    def test_absent_optional_claim_remains_valid(self):
        m,t=source_bound()
        self.assertEqual(diagnose(m,t)['trace_integrity'],'consistent')

    def test_legacy_synthetic_model_without_rule_inventory_keeps_index_type_validation(self):
        m,t=payload()
        t['events'][5]['outcome_index']=1
        self.assertEqual(diagnose(m,t)['trace_integrity'],'consistent')


if __name__=='__main__':unittest.main()
