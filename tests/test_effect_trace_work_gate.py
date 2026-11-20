"""The official Work implementation Gate can inventory and reject Effect traces.

Packet content is not evidence of a real external effect and must not pass a
normative implementation Gate even with all other obligations marked passed.
"""
from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
import cat_flow as flow
from catlib import work as worklib
from test_effect_trace_correlation import data,DRIVER,BINDING


def setup(root):
    raw,trace,packet=data(root)
    (root/'Model.json').write_bytes(raw)
    (root/'Trace.json').write_text(json.dumps(trace),encoding='utf-8')
    (root/'Packet.json').write_text(json.dumps(packet),encoding='utf-8')
    (root/'runner.py').write_bytes(DRIVER)
    for name in ('process.md','pi.md','tce.md'):
        (root/name).write_text('fixture')
    (root/'obligations.json').write_text(json.dumps({'schema':'cat-implementation-obligations/v1','items':[]}),encoding='utf-8')
    workpath=root/'work.json'
    conf={'schema':'cat-compile/v2','process':'process.md','pi':'pi.md','tce':'tce.md',
          'model':'Model.json','obligations':'obligations.json',
          'effect_trace':'Trace.json','effect_packet':'Packet.json',
          'effect_driver':'runner.py','allow_draft':False}
    w={'id':'demo.effect.work','flow':'spec-implementation','entry':'confirmed-spec',
       'specification':{'status':'confirmed','decision_ref':'spec','artifact_refs':['demo.tce']},
       'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},
       'repositories':[],'technologies':[], 'checks':[], 'compilation':conf}
    workpath.write_text(json.dumps(w),encoding='utf-8')
    return w,workpath


class EffectGateIntegration(unittest.TestCase):
    def test_structurally_consistent_receipt_cannot_pass_official_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            passed_items=[{'category':c,'status':'passed','source_ref':'src',
                           'method':'observed','limitation':'bounded','evidence':'fixture'}
                          for c in ('interface','capability','behavior','invariant',
                                    'cross-process','domain','implementation-constraint')]
            with patch.object(flow,'technology_conformance',return_value={'status':'passed','results':[]}),\
                 patch.object(flow,'obligations_work',return_value={'status':'passed'}),\
                 patch.object(flow.obligation_runtime,'aggregate',return_value={'items':passed_items}),\
                 patch.object(flow,'conformance_evidence_status',return_value={'status':'passed'}):
                result=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(result['status'],'inconclusive')
            self.assertIn('Effect/trace receipt identities',result['reason'])
            path=Path(result['effect_correlation_evidence'])
            self.assertEqual(json.loads(path.read_bytes())['normative_status'],'inconclusive')

    def test_fake_cross_run_effect_blocks_official_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            packet=json.loads((root/'Packet.json').read_text())
            packet['observations'][0]['effect_event_id']='result'
            (root/'Packet.json').write_text(json.dumps(packet))
            result=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(result['status'],'blocked')
            self.assertIn('Effect/trace evidence invalid',result['reason'])

    def test_mixed_transaction_in_single_execution_blocks_formal_implementation_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            trace=json.loads((root/'Trace.json').read_text(encoding='utf-8'))
            packet=json.loads((root/'Packet.json').read_text(encoding='utf-8'))
            trace['runs'][0]['correlation']=dict(BINDING)
            trace['events'][4]['correlation']=dict(BINDING)
            trace['events'][5]['correlation']=dict(BINDING)
            packet['observations'][0]['correlation']=dict(BINDING)
            packet['observations'][0]['correlation']['transaction_id']='unrelated-tx'
            (root/'Trace.json').write_text(json.dumps(trace),encoding='utf-8')
            (root/'Packet.json').write_text(json.dumps(packet),encoding='utf-8')
            verdict=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(verdict['status'],'blocked',verdict)
            self.assertIn('correlation',verdict['reason'])

    def test_consistent_transaction_identity_remains_non_normative_in_formal_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            trace=json.loads((root/'Trace.json').read_text(encoding='utf-8'))
            packet=json.loads((root/'Packet.json').read_text(encoding='utf-8'))
            trace['runs'][0]['correlation']=dict(BINDING)
            trace['events'][4]['correlation']=dict(BINDING)
            trace['events'][5]['correlation']=dict(BINDING)
            packet['observations'][0]['correlation']=dict(BINDING)
            (root/'Trace.json').write_text(json.dumps(trace),encoding='utf-8')
            (root/'Packet.json').write_text(json.dumps(packet),encoding='utf-8')
            passed_items=[{'category':c,'status':'passed','source_ref':'src',
                           'method':'observed','limitation':'bounded','evidence':'fixture'}
                          for c in ('interface','capability','behavior','invariant',
                                    'cross-process','domain','implementation-constraint')]
            with patch.object(flow,'technology_conformance',return_value={'status':'passed','results':[]}),\
                 patch.object(flow,'obligations_work',return_value={'status':'passed'}),\
                 patch.object(flow.obligation_runtime,'aggregate',return_value={'items':passed_items}),\
                 patch.object(flow,'conformance_evidence_status',return_value={'status':'passed'}):
                verdict=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(verdict['status'],'inconclusive',verdict)
            self.assertIn('Effect/trace receipt identities',verdict['reason'])

    def test_receipt_observation_mutation_invalidates_exact_gate_input_inventory(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            a=flow.conformance_input_hashes(wp,w,'implementation-conformance')
            self.assertIn('effect_packet',a)
            self.assertIn('effect_trace',a)
            self.assertIn('effect_driver',a)
            self.assertIn('effect_observation:1',a)
            flow.record_conformance_evidence(wp,w,'implementation-conformance',
                {'status':'inconclusive','reason':'identity-only'})
            self.assertEqual(flow.conformance_evidence_status(wp,w,'implementation-conformance')['status'],'inconclusive')
            (root/'observation.json').write_text('changed observation')
            self.assertEqual(flow.conformance_evidence_status(wp,w,'implementation-conformance')['status'],'stale')

    def test_observation_file_cannot_claim_other_transaction_under_matching_sha(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            trace=json.loads((root/'Trace.json').read_text(encoding='utf-8'))
            packet=json.loads((root/'Packet.json').read_text(encoding='utf-8'))
            trace['runs'][0]['correlation']=dict(BINDING)
            trace['events'][4]['correlation']=dict(BINDING)
            trace['events'][5]['correlation']=dict(BINDING)
            packet['observations'][0]['correlation']=dict(BINDING)
            observed=json.loads((root/'observation.json').read_bytes())
            observed['correlation']={**BINDING,'transaction_id':'another-tx'}
            content=json.dumps(observed,sort_keys=True).encode()
            (root/'observation.json').write_bytes(content)
            packet['observations'][0]['observation_sha256']=hashlib.sha256(content).hexdigest()
            (root/'Trace.json').write_text(json.dumps(trace),encoding='utf-8')
            (root/'Packet.json').write_text(json.dumps(packet),encoding='utf-8')
            result=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(result['status'],'blocked',result)
            self.assertIn('observation correlation',result['reason'])

    def test_unobserved_effect_with_other_terminal_outcome_blocks_formal_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            trace=json.loads((root/'Trace.json').read_text(encoding='utf-8'))
            packet=json.loads((root/'Packet.json').read_text(encoding='utf-8'))
            record=packet['observations'][0]
            record.update(reported_status='not-observed',observation_file=None,
                          observation_sha256=None,effect_event_id=None)
            trace['events'][5]['outcome_index']=2
            (root/'Trace.json').write_text(json.dumps(trace),encoding='utf-8')
            (root/'Packet.json').write_text(json.dumps(packet),encoding='utf-8')
            verdict=flow.conformance_work(wp,w,'implementation-conformance')
            self.assertEqual(verdict['status'],'blocked',verdict)
            self.assertIn('terminal allowed Outcome',verdict['reason'])

    def test_unobserved_effect_with_conflicting_terminal_transaction_blocks_official_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work,wp=setup(root)
            trace=json.loads((root/'Trace.json').read_text(encoding='utf-8'))
            packet=json.loads((root/'Packet.json').read_text(encoding='utf-8'))
            trace['runs'][0]['correlation']=dict(BINDING)
            trace['events'][5]['correlation']={**BINDING,'transaction_id':'other-tx'}
            record=packet['observations'][0]
            record['correlation']=dict(BINDING)
            record.update(reported_status='not-observed',observation_file=None,
                          observation_sha256=None,effect_event_id=None)
            (root/'Trace.json').write_text(json.dumps(trace),encoding='utf-8')
            (root/'Packet.json').write_text(json.dumps(packet),encoding='utf-8')
            verdict=flow.conformance_work(wp,work,'implementation-conformance')
            self.assertEqual(verdict['status'],'blocked',verdict)
            self.assertIn('correlation',verdict['reason'])

    def test_incomplete_evidence_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            del w['compilation']['effect_driver']
            self.assertIn('effect evidence requires trace, packet and driver together',worklib.validate(w))
            with self.assertRaisesRegex(flow.Blocked,'Effect evidence requires'):
                flow.implementation_effect_preflight(wp,w,w['compilation'])

    def test_optional_evidence_does_not_affect_existing_work(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            for key in ('effect_trace','effect_packet','effect_driver'):
                del w['compilation'][key]
            self.assertIsNone(flow.implementation_effect_preflight(wp,w,w['compilation']))
            inputs=flow.conformance_input_hashes(wp,w,'implementation-conformance')
            self.assertNotIn('effect_packet',inputs)

    def test_wrong_observation_path_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,wp=setup(root)
            packet=json.loads((root/'Packet.json').read_text())
            packet['observations'][0]['observation_file']='../outside.json'
            (root/'Packet.json').write_text(json.dumps(packet))
            with self.assertRaisesRegex(flow.Blocked,'Effect observation input invalid'):
                flow.conformance_input_hashes(wp,w,'implementation-conformance')
            packet['observations'][0]['observation_file']='linked.json'
            (root/'Packet.json').write_text(json.dumps(packet))
            (root/'linked.json').symlink_to(root/'observation.json')
            with self.assertRaisesRegex(flow.Blocked,'symlink'):
                flow.conformance_input_hashes(wp,w,'implementation-conformance')

if __name__=='__main__':unittest.main()
