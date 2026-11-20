"""UP20-03: trace identity and causality cannot be inferred from type equality."""
from __future__ import annotations
import hashlib,json,sys,tempfile,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_execution_trace_diagnostic as diagnostic

def payload():
    model={'schema':'cat-test-model/v2','process':'demo',
        'source_records':[{'id':'demo.pi','kind':'pi','sha256':'a'*64}],
        'pi_boundaries':[{'artifact':'demo.pi','peer':'launcher',
                          'peers':['launcher','command'],'direction':'bidirectional'}],
        'pi_operations':[
            {'id':'startup','direction':'accept','source_pi':'demo.pi','peer':'launcher'},
            {'id':'manual','direction':'accept','source_pi':'demo.pi','peer':'command'},
            {'id':'startup_result','direction':'provide','source_pi':'demo.pi','peer':'launcher'},
            {'id':'manual_result','direction':'provide','source_pi':'demo.pi','peer':'command'}]}
    source={'demo.pi':'a'*64}
    events=[
        {'event_id':'start','execution_id':'run-1','kind':'trigger','operation':'startup','peer':'launcher'},
        {'event_id':'request','execution_id':'run-1','kind':'request','parent_event_id':'start'},
        {'event_id':'remote','execution_id':'run-1','kind':'response','parent_event_id':'request'},
        {'event_id':'validated','execution_id':'run-1','kind':'projection','parent_event_id':'remote','source_kind':'response'},
        {'event_id':'replace','execution_id':'run-1','kind':'replace','parent_event_id':'validated'},
        {'event_id':'result','execution_id':'run-1','kind':'result','parent_event_id':'replace','operation':'startup_result','peer':'launcher','outcome':'success'},
        {'event_id':'reload','execution_id':'run-1','kind':'followup','parent_event_id':'result'}]
    trace={'schema':'cat-execution-trace/v1','source_sha256':source,
           'runs':[{'execution_id':'run-1','entry_operation':'startup','peer':'launcher'}],
           'events':events}
    return model,trace

def diagnose(model,trace):
    raw=json.dumps(model,ensure_ascii=False,sort_keys=True).encode()
    trace['model_sha256']=hashlib.sha256(raw).hexdigest()
    return diagnostic.evaluate(model,raw,trace)

class ExecutionTraceTests(unittest.TestCase):
    def test_one_run_structurally_consistent_is_not_external_effect_proof(self):
        model,trace=payload();result=diagnose(model,trace)
        self.assertEqual(result['trace_integrity'],'consistent')
        self.assertEqual(result['normative_status'],'inconclusive')
        self.assertEqual(result['external_effect_proof'],'not-run')
    def test_declared_outcome_index_is_exact_positive_integer(self):
        # Standalone trace checks must reject malformed identifiers before
        # any Effect receipt correlation is attempted.
        for index in (1,5):
            for invalid in (True,False,1.0,0.0):
                with self.subTest(event=index,value=invalid):
                    model,trace=payload()
                    trace['events'][index]['outcome_index']=invalid
                    with self.assertRaisesRegex(diagnostic.TraceError,'outcome index'):
                        diagnose(model,trace)
        model,trace=payload()
        trace['events'][1]['outcome_index']=1
        trace['events'][5]['outcome_index']=1
        self.assertEqual(diagnose(model,trace)['trace_integrity'],'consistent')

    def test_cross_run_response_is_not_one_execution(self):
        m,t=payload()
        t['runs'].append({'execution_id':'run-2','entry_operation':'manual','peer':'command'})
        t['events'].insert(1,{'event_id':'start2','execution_id':'run-2','kind':'trigger','operation':'manual','peer':'command'})
        t['events'][3]['execution_id']='run-2'  # the response now belongs to run-2
        with self.assertRaisesRegex(diagnostic.TraceError,'different execution'):
            diagnose(m,t)
    def test_wrong_operation_peer_is_not_accepted(self):
        m,t=payload();t['events'][0]['peer']='command'
        with self.assertRaisesRegex(diagnostic.TraceError,'peer'):
            diagnose(m,t)
    def test_reused_result_from_other_operation_is_rejected(self):
        m,t=payload();t['events'][5]['operation']='manual_result'
        with self.assertRaisesRegex(diagnostic.TraceError,'peer'):
            diagnose(m,t)
    def test_duplicate_terminal_result_is_rejected(self):
        m,t=payload();t['events'].append({'event_id':'extra','execution_id':'run-1','kind':'result',
            'parent_event_id':'result','operation':'startup_result','peer':'launcher','outcome':'failure'})
        with self.assertRaisesRegex(diagnostic.TraceError,'multiple terminal'):
            diagnose(m,t)
    def test_unknown_result_is_not_treated_as_success(self):
        m,t=payload();t['events'][5]['outcome']='unknown'
        result=diagnose(m,t)
        self.assertEqual(result['trace_integrity'],'inconclusive')
        self.assertEqual(result['normative_status'],'inconclusive')
    def test_missing_result_stays_inconclusive(self):
        m,t=payload();t['events']=t['events'][:5]
        result=diagnose(m,t)
        self.assertEqual(result['trace_integrity'],'inconclusive')
    def test_projection_without_response_ancestor_fails(self):
        m,t=payload();t['events'][3]['parent_event_id']='request'
        with self.assertRaisesRegex(diagnostic.TraceError,'response ancestor'):
            diagnose(m,t)
    def test_hash_rebinding_cannot_erase_source_difference(self):
        m,t=payload();t['source_sha256']['demo.pi']='b'*64
        with self.assertRaisesRegex(diagnostic.TraceError,'source identity'):
            diagnose(m,t)
    def test_existing_multi_peer_without_operation_peer_is_ambiguous(self):
        m,t=payload();del m['pi_operations'][0]['peer']
        with self.assertRaisesRegex(diagnostic.TraceError,'ambiguous'):
            diagnose(m,t)

if __name__=='__main__':unittest.main()
