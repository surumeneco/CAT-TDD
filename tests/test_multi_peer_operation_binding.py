"""Operation-to-peer provenance must survive PI parsing and cross-Process binding."""
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
from cat_compile_v2 import Blocked, load
from test_cat_compile_readable import write_v2
from test_process_composition import model, binding


def multi_peer_models():
    source = model('p.one', 'p.two', 'send')
    source['pi_boundaries'][0]['peers'] = ['p.two', 'p.three']
    source['pi_operations'][0]['peer'] = 'p.two'
    secondary = dict(source['pi_operations'][0], id='p.one.secondary', peer='p.three')
    source['pi_operations'].append(secondary)
    two = model('p.two', 'p.one', 'receive')
    three = model('p.three', 'p.one', 'receive')
    return source, two, three


def write_models(root, source, two, three, links):
    paths = []
    for name, value in (('one', source), ('two', two), ('three', three)):
        path = root / (name + '.json')
        path.write_text(json.dumps(value), encoding='utf-8')
        paths.append(path)
    bind = root / 'binding.json'
    bind.write_text(json.dumps({'schema': 'cat-process-bindings/v1', 'links': links}), encoding='utf-8')
    return paths, bind


def link_to(target, outgoing):
    result = json.loads(json.dumps(binding()['links'][0]))
    result['target_process'] = target
    result['target_pi'] = target + '.pi'
    result['target_operation'] = target + '.op'
    result['source_operation'] = outgoing
    return result


def peer_pi(root, explicitly=True):
    process, pi, tce = write_v2(root, False)
    original = pi.read_text(encoding='utf-8')
    original = original.replace('| demo.user | bidirectional |',
                                '| demo.user | bidirectional |\n| demo.other | bidirectional |')
    if explicitly:
        original = original.replace('| ID | Direction | Trigger |\n| --- | --- | --- |\n| submit_op | accept | submit |',
                                    '| ID | Direction | Trigger | Peer process |\n| --- | --- | --- | --- |\n| submit_op | accept | submit | demo.user |')
    pi.write_text(original, encoding='utf-8')
    return process, pi, tce


class MultiPeerBindingTests(unittest.TestCase):
    def test_distinct_peers_can_have_distinct_explicit_operations(self):
        with tempfile.TemporaryDirectory() as temp:
            source, two, three = multi_peer_models()
            paths, binds = write_models(Path(temp), source, two, three, [
                link_to('p.two', 'p.one.op'),
                link_to('p.three', 'p.one.secondary'),
            ])
            result = composition.compose(paths, binds)
            self.assertEqual(len(result['bindings']), 2)
            self.assertEqual(result['unresolved_connections'], [])
            self.assertEqual(result['status'], 'inconclusive')  # No external effect proof

    def test_source_operation_may_not_be_bound_to_different_declared_peer(self):
        with tempfile.TemporaryDirectory() as temp:
            source, two, three = multi_peer_models()
            paths, binds = write_models(Path(temp), source, two, three, [
                link_to('p.three', 'p.one.op')
            ])
            with self.assertRaisesRegex(composition.CompositionError, 'operation.*peer'):
                composition.compose(paths, binds)

    def test_multi_peer_operation_without_peer_provenance_is_not_proved(self):
        with tempfile.TemporaryDirectory() as temp:
            source, two, three = multi_peer_models()
            del source['pi_operations'][0]['peer']
            paths, binds = write_models(Path(temp), source, two, three, [
                link_to('p.two', 'p.one.op')
            ])
            with self.assertRaisesRegex(composition.CompositionError, 'operation.*peer'):
                composition.compose(paths, binds)

    def test_unknown_declared_peer_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            source, two, three = multi_peer_models()
            source['pi_operations'][0]['peer'] = 'p.unknown'
            paths, binds = write_models(Path(temp), source, two, three, [
                link_to('p.two', 'p.one.op')
            ])
            with self.assertRaisesRegex(composition.CompositionError, 'operation.*peer'):
                composition.compose(paths, binds)

    def test_legacy_single_peer_operation_remains_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            s = model('p.one', 'p.two', 'send')
            t = model('p.two', 'p.one', 'receive')
            a = Path(temp) / 'a.json'
            b = Path(temp) / 'b.json'
            l = Path(temp) / 'links.json'
            a.write_text(json.dumps(s))
            b.write_text(json.dumps(t))
            l.write_text(json.dumps(binding()))
            self.assertEqual(composition.compose([a, b], l)['bindings'][0]['status'],
                             'structurally-matched')

    def test_parser_preserves_explicit_peer_in_machine_model(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = peer_pi(Path(temp))
            compiled = load(*paths, allow_draft=True, allow_partial=True)
            self.assertEqual(compiled['pi_operations'][0]['peer'], 'demo.user')
            self.assertEqual(compiled['pi_boundaries'][0]['peers'], ['demo.user', 'demo.other'])

    def test_multi_peer_pi_without_operation_mapping_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = peer_pi(Path(temp), explicitly=False)
            with self.assertRaisesRegex(Blocked, 'operation.*peer'):
                load(*paths, allow_draft=True, allow_partial=True)

    def test_source_conformance_rejects_peer_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = peer_pi(root)
            compiled = load(*paths, allow_draft=True, allow_partial=True)
            model_file = root / 'Model.json'
            model_file.write_text(json.dumps(compiled), encoding='utf-8')
            self.assertEqual(conformance.validate(paths[0], paths[1], [paths[2]],
                                                  model_file, allow_draft=True)['status'], 'passed')
            compiled['pi_operations'][0]['peer'] = 'demo.other'
            model_file.write_text(json.dumps(compiled), encoding='utf-8')
            result = conformance.validate(paths[0], paths[1], [paths[2]],
                                          model_file, allow_draft=True)
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('operations', result['mismatches'])


if __name__ == '__main__':
    unittest.main()
