"""GEN-02: execution-origin is a runtime Process peer, not a fixed component."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'),
    str(Path(__file__).resolve().parent),
]
import cat_process_composition as composition
import cat_model_conformance as conformance
import cat_execution_trace_diagnostic as trace_diagnostic
from cat_compile_v2 import load, render_model_markdown
from test_multi_peer_operation_binding import peer_pi, multi_peer_models, link_to, write_models
from test_process_composition import model, binding
from test_execution_trace_diagnostic import payload, diagnose

ORIGIN = '@execution-origin'


def replace_operation_peer(pi, value):
    text = pi.read_text(encoding='utf-8')
    text = text.replace('| submit_op | accept | submit | demo.user |',
                        '| submit_op | accept | submit | ' + value + ' |')
    pi.write_text(text, encoding='utf-8')


class ExecutionOriginPeerTests(unittest.TestCase):
    def test_dynamic_origin_operation_accepts_japanese_and_canonical_notation(self):
        for value in ('実行元Process', ORIGIN):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                paths = peer_pi(Path(tmp))
                replace_operation_peer(paths[1], value)
                result = load(*paths, allow_draft=True, allow_partial=True)
                self.assertEqual(result['pi_operations'][0]['peer'], ORIGIN)
                self.assertEqual(result['pi_boundaries'][0]['peers'],
                                 ['demo.user', 'demo.other'])
                report = render_model_markdown(result)
                model_path = Path(tmp) / 'Model.md'
                model_path.write_text(report, encoding='utf-8')
                self.assertEqual(conformance.validate(
                    paths[0], paths[1], [paths[2]], model_path, allow_draft=True
                )['status'], 'passed')

    def test_dynamic_origin_can_be_the_only_boundary_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = peer_pi(Path(tmp), explicitly=True)
            text = paths[1].read_text(encoding='utf-8')
            text = text.replace('| demo.user | bidirectional |', '| 実行元Process | bidirectional |')
            text = text.replace('| demo.other | bidirectional |\n', '')
            paths[1].write_text(text, encoding='utf-8')
            replace_operation_peer(paths[1], ORIGIN)
            result = load(*paths, allow_draft=True, allow_partial=True)
            self.assertEqual(result['pi_boundaries'][0]['peer'], ORIGIN)
            self.assertEqual(result['pi_operations'][0]['peer'], ORIGIN)
            report = render_model_markdown(result)
            self.assertIn('Peer process', report)
            path = Path(tmp) / 'Model.md'
            path.write_text(report, encoding='utf-8')
            self.assertEqual(conformance.validate(
                paths[0], paths[1], [paths[2]], path, allow_draft=True
            )['status'], 'passed')

    def test_dynamic_origin_model_peer_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = peer_pi(Path(tmp))
            replace_operation_peer(paths[1], ORIGIN)
            result = load(*paths, allow_draft=True, allow_partial=True)
            result['pi_operations'][0]['peer'] = 'demo.user'
            path = Path(tmp) / 'Model.json'
            path.write_text(json.dumps(result), encoding='utf-8')
            checked = conformance.validate(
                paths[0], paths[1], [paths[2]], path, allow_draft=True
            )
            self.assertEqual(checked['status'], 'blocked')
            self.assertIn('operations', checked['mismatches'])

    def test_dynamic_provide_can_bind_two_static_peers_without_proving_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, two, three = multi_peer_models()
            source['pi_operations'] = [source['pi_operations'][0]]
            source['pi_operations'][0]['peer'] = ORIGIN
            paths, links = write_models(Path(tmp), source, two, three, [
                link_to('p.two', 'p.one.op'),
                link_to('p.three', 'p.one.op'),
            ])
            result = composition.compose(paths, links)
            self.assertEqual(len(result['bindings']), 2)
            self.assertTrue(all(x['status'] == 'inconclusive' for x in result['bindings']))
            self.assertEqual(result['status'], 'inconclusive')

    def test_symbolic_boundary_binds_unenumerated_process_without_static_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = model('p.one', ORIGIN, 'send')
            source['pi_operations'][0]['peer'] = ORIGIN
            target = model('p.two', 'p.one', 'receive')
            a = Path(tmp) / 'a.json'
            b = Path(tmp) / 'b.json'
            l = Path(tmp) / 'links.json'
            for path, value in ((a, source), (b, target), (l, binding())):
                path.write_text(json.dumps(value), encoding='utf-8')
            result = composition.compose([a, b], l)
            self.assertEqual(result['bindings'][0]['status'], 'inconclusive')
            self.assertEqual(result['status'], 'inconclusive')
            self.assertTrue(result['unresolved_connections'])

    def test_concrete_wrong_static_peer_remains_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, two, three = multi_peer_models()
            paths, links = write_models(Path(tmp), source, two, three, [
                link_to('p.three', 'p.one.op')
            ])
            with self.assertRaisesRegex(composition.CompositionError, 'operation.*peer'):
                composition.compose(paths, links)

    def test_two_concurrent_runs_share_operations_but_keep_distinct_origins(self):
        m, t = payload()
        m['pi_operations'][0]['peer'] = ORIGIN
        m['pi_operations'][2]['peer'] = ORIGIN
        t['runs'].append({'execution_id': 'run-2', 'entry_operation': 'startup',
                          'peer': 'command'})
        t['events'].extend([
            {'event_id': 'start-2', 'execution_id': 'run-2', 'kind': 'trigger',
             'operation': 'startup', 'peer': 'command'},
            {'event_id': 'result-2', 'execution_id': 'run-2', 'kind': 'result',
             'parent_event_id': 'start-2', 'operation': 'startup_result',
             'peer': 'command', 'outcome': 'success'},
        ])
        checked = diagnose(m, t)
        self.assertEqual(checked['trace_integrity'], 'consistent')
        self.assertEqual(checked['normative_status'], 'inconclusive')
        t['events'][-1]['peer'] = 'launcher'  # run-2 must return to command
        with self.assertRaisesRegex(trace_diagnostic.TraceError, 'peer'):
            diagnose(m, t)
        t['events'][-1]['peer'] = 'command'
        t['runs'].append(dict(t['runs'][0]))  # cannot reuse an execution identity
        with self.assertRaisesRegex(trace_diagnostic.TraceError, 'duplicate execution'):
            diagnose(m, t)

    def test_dynamic_boundary_matches_concrete_runtime_origin_not_symbolic_placeholder(self):
        m, t = payload()
        m['pi_boundaries'][0]['peer'] = ORIGIN
        m['pi_boundaries'][0]['peers'] = [ORIGIN]
        m['pi_operations'] = [m['pi_operations'][0], m['pi_operations'][2]]
        for op in m['pi_operations']:
            op['peer'] = ORIGIN
        t['runs'][0]['peer'] = 'component.alpha'
        t['events'][0]['peer'] = 'component.alpha'
        t['events'][5]['peer'] = 'component.alpha'
        self.assertEqual(diagnose(m, t)['trace_integrity'], 'consistent')
        t['events'][5]['peer'] = 'component.beta'
        with self.assertRaisesRegex(trace_diagnostic.TraceError, 'peer'):
            diagnose(m, t)
        t['events'][5]['peer'] = 'component.alpha'
        t['runs'][0]['peer'] = ORIGIN
        with self.assertRaisesRegex(trace_diagnostic.TraceError, 'peer|origin'):
            diagnose(m, t)

    def test_outside_declared_static_peers_is_not_a_valid_runtime_origin(self):
        m, t = payload()
        m['pi_operations'][0]['peer'] = ORIGIN
        t['runs'][0]['peer'] = 'outsider'
        t['events'][0]['peer'] = 'outsider'
        with self.assertRaisesRegex(trace_diagnostic.TraceError, 'peer'):
            diagnose(m, t)


if __name__ == '__main__':
    unittest.main()
