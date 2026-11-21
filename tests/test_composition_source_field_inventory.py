"""Every possibly emitted PI output needs an explicit composition binding.

The current binding schema has no authorized per-operation projection. A
source's unbound Output must not disappear merely because all receiver Inputs
were bound. These are structural checks, not cross-process effect proofs.
"""
import tempfile
import unittest
from pathlib import Path

import test_process_composition as fixtures

import cat_process_composition as composer


def with_extra_source(presence='required', *, different_pi=False, operation_override=None):
    producer=fixtures.model('p.one','p.two','send')
    producer['fields'].append({
        'id':'output.extra', 'role':'output', 'presence':presence,
        'source_pi':'p.one.other' if different_pi else 'p.one.pi',
        'domain':{'type':'integer'},
    })
    if operation_override is not None:
        producer['operation_presence']=[{'source_pi':'p.one.pi',
                                         'operation':'p.one.op',
                                         'field':'output.extra',
                                         'presence':operation_override}]
    return producer


class SourceFieldInventoryTests(unittest.TestCase):
    def compose(self, producer):
        with tempfile.TemporaryDirectory() as td:
            a,b,links=fixtures.CompositionTests().write(Path(td),first=producer)
            return composer.compose([a,b],links)

    def test_unmapped_required_source_output_is_not_structurally_matched(self):
        result=self.compose(with_extra_source('required'))
        self.assertEqual(result['bindings'][0]['status'],'inconclusive')
        self.assertEqual(result['bindings'][0]['unmapped_source_fields'],['output.extra'])
        self.assertIn('PI binding exists but structural proof is inconclusive',
                      {r['reason'] for r in result['unresolved_connections']})

    def test_unmapped_optional_source_output_may_be_emitted(self):
        result=self.compose(with_extra_source('optional'))
        self.assertEqual(result['bindings'][0]['status'],'inconclusive')
        self.assertEqual(result['bindings'][0]['unmapped_source_fields'],['output.extra'])

    def test_unmapped_undefined_source_output_is_not_assumed_absent(self):
        result=self.compose(with_extra_source('undefined'))
        self.assertEqual(result['bindings'][0]['status'],'inconclusive')
        self.assertEqual(result['bindings'][0]['unmapped_source_fields'],['output.extra'])

    def test_base_absent_source_output_does_not_need_value_binding(self):
        result=self.compose(with_extra_source('absent'))
        self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
        self.assertEqual(result['bindings'][0]['unmapped_source_fields'],[])

    def test_linked_operation_override_absent_suppresses_extra_output(self):
        result=self.compose(with_extra_source('required',operation_override='absent'))
        self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
        self.assertEqual(result['bindings'][0]['unmapped_source_fields'],[])

    def test_extra_output_owned_by_other_pi_does_not_affect_connection(self):
        result=self.compose(with_extra_source('required',different_pi=True))
        self.assertEqual(result['bindings'][0]['status'],'structurally-matched')
        self.assertEqual(result['bindings'][0]['unmapped_source_fields'],[])


if __name__=='__main__':
    unittest.main()
