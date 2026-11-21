"""Typed Set connections must preserve element-distinctness, not only element types.

The CAT Set domain has a domain-aware element equality contract. It cannot be
widened to another Set whose equality merges two values validly distinct in
the producer. JSON treats the numeric values 1 and 1.0 as equal; a plain
real Domain currently treats their different scalar representations as
distinct. Source-to-Model/Provider truth is not established by these tests.
"""
from __future__ import annotations

import unittest

from catlib import semantic_types, semantic_subtyping
import cat_process_composition as composition
from test_process_composition import model, binding


JSON = {'type': 'json', 'root': 'value'}
REAL = {'type': 'real'}
INTEGER = {'type': 'integer'}
STRING = {'type': 'string'}


def set_of(element):
    return {'type': 'set', 'element': element}


def sequence_of(element):
    return {'type': 'sequence', 'element': element}


def record_of(element):
    return {'type': 'record', 'resolved': True, 'fields': [
        {'id': 'number', 'domain': element, 'presence': 'required'}]}


def actual_binding(source, target):
    sender = model('p.one', 'p.two', 'send')
    receiver = model('p.two', 'p.one', 'receive')
    sender['fields'][0]['domain'] = source
    receiver['fields'][0]['domain'] = target
    return composition._link(binding()['links'][0],
                             {'p.one': sender, 'p.two': receiver})


class SetSemanticEqualityInclusionTests(unittest.TestCase):
    def assert_unsound_witness_rejected(self, source_element, target_element, witness):
        source = set_of(source_element)
        target = set_of(target_element)
        self.assertTrue(semantic_types.contains(source, witness))
        self.assertFalse(semantic_types.contains(target, witness))
        # A type-only widening is insufficient for a Set: same Target
        # equality may merge elements Source correctly distinguishes.
        self.assertIsNone(semantic_subtyping.subset(source, target))

    def test_real_elements_collapse_under_json_numeric_equality(self):
        self.assert_unsound_witness_rejected(REAL, JSON, [1, 1.0])

    def test_record_elements_with_real_field_collapse_under_json_field(self):
        self.assert_unsound_witness_rejected(
            record_of(REAL), record_of(JSON),
            [{'number': 1}, {'number': 1.0}])

    def test_record_elements_collapse_when_widened_to_json_object(self):
        self.assert_unsound_witness_rejected(
            record_of(REAL), JSON,
            [{'number': 1}, {'number': 1.0}])

    def test_sequence_elements_with_real_field_collapse(self):
        self.assert_unsound_witness_rejected(
            sequence_of(REAL), sequence_of(JSON), [[1], [1.0]])

    def test_nullable_json_equality_still_merges_real_numeric_representations(self):
        self.assert_unsound_witness_rejected(
            REAL, {'type': 'nullable', 'of': JSON}, [1, 1.0])

    def test_false_structural_pi_connection_must_remain_inconclusive(self):
        linked = actual_binding(set_of(REAL), set_of(JSON))
        self.assertEqual(linked['status'], 'inconclusive')
        self.assertEqual(linked['field_links'][0]['status'], 'inconclusive')
        self.assertEqual(linked['field_links'][0]['value_domain_proof'],
                         'inconclusive')
        self.assertFalse(linked['external_effects_verified'])

    def test_safe_integer_elements_to_json_keep_valid_inclusion(self):
        source = set_of({'type': 'integer', 'min': -2, 'max': 3})
        target = set_of(JSON)
        self.assertTrue(semantic_subtyping.subset(source, target))
        self.assertTrue(semantic_types.contains(target, [1, 2]))
        linked = actual_binding(source, target)
        self.assertEqual(linked['status'], 'structurally-matched')
        self.assertEqual(linked['field_links'][0]['value_domain_proof'], 'proved')
        self.assertFalse(linked['external_effects_verified'])

    def test_safe_enum_of_int_and_bool_to_json_remains_proved(self):
        source = set_of({'type': 'enum', 'values': [True, 1, 'one']})
        target = set_of(JSON)
        self.assertTrue(semantic_subtyping.subset(source, target))
        self.assertTrue(semantic_types.contains(source, [True, 1, 'one']))
        self.assertTrue(semantic_types.contains(target, [True, 1, 'one']))

    def test_safe_nested_record_integer_to_json_remains_proved(self):
        source = set_of(record_of(INTEGER))
        for target in (set_of(record_of(JSON)), set_of(JSON)):
            self.assertTrue(semantic_subtyping.subset(source, target))
            self.assertTrue(semantic_types.contains(target,
                            [{'number': 1}, {'number': 2}]))

    def test_equivalent_real_set_is_proved(self):
        source = set_of(REAL)
        self.assertTrue(semantic_subtyping.subset(source, set_of(REAL)))
        self.assertTrue(semantic_types.contains(source, [1, 1.0]))

    def test_real_set_can_transfer_to_json_sequence_without_set_uniqueness(self):
        source = set_of(REAL)
        for target in (sequence_of(JSON), JSON):
            self.assertTrue(semantic_subtyping.subset(source, target))
            self.assertTrue(semantic_types.contains(target, [1, 1.0]))

    def test_safe_strict_element_domain_widening_is_preserved(self):
        source = set_of({'type': 'enum', 'values': ['red', 'blue']})
        target = set_of(STRING)
        self.assertTrue(semantic_subtyping.subset(source, target))
        self.assertEqual(actual_binding(source, target)['status'],
                         'structurally-matched')


if __name__ == '__main__':
    unittest.main()
