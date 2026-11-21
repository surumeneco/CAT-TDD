"""Typed Set connections must preserve element-distinctness, not only element types.

The CAT Set domain has a domain-aware element equality contract. It cannot be
widened to another Set whose equality merges two values validly distinct in
the producer. JSON treats the numeric values 1 and 1.0 as equal; a plain
real Domain currently treats their different scalar representations as
distinct. Source-to-Model/Provider truth is not established by these tests.
"""
from __future__ import annotations

import unittest
import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
from catlib import semantic_types, semantic_subtyping
import cat_process_composition as composition
from test_process_composition import model, binding
from test_cat_compile_readable import write_v2
from cat_compile_v2 import Blocked, load
from cat_model_conformance import validate as model_conformance


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


def direct_set_effect_sources(root, source_element):
    process, pi, tce = write_v2(root, False)
    process.write_text(process.read_text(encoding='utf-8').replace(
        'state.ready | boolean', f'state.ready | set<{source_element}>'),
        encoding='utf-8')
    pi.write_text(pi.read_text(encoding='utf-8').replace(
        'output.accepted | send | boolean',
        'output.accepted | send | set<json>'), encoding='utf-8')
    effects = tce.read_text(encoding='utf-8')
    effects = effects.replace('state.ready = true; ', '')
    effects = effects.replace('output.accepted = true',
                              'output.accepted = state.ready')
    effects = effects.replace('output.accepted = false',
                              'output.accepted = state.ready')
    tce.write_text(effects, encoding='utf-8')
    # Synthetic approved-Source fixture for exercising the existing
    # Compiler contract; these labels are not real product authority.
    for path in (process, pi, tce):
        path.write_text(
            path.read_text(encoding='utf-8').replace(
                'status: draft', 'status: confirmed').replace(
                "decision_ref: ''",
                'decision_ref: https://example.org/approved'),
            encoding='utf-8')
    return process, pi, tce


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

    def test_real_with_integral_member_retains_collision(self):
        restricted = {'type': 'real', 'min': 0, 'max': 0}
        self.assert_unsound_witness_rejected(restricted, JSON, [0, 0.0])

    def test_real_interval_excluding_integers_can_widen_json_set(self):
        restricted = {'type': 'real', 'min': 0.1, 'max': 0.9}
        source = set_of(restricted)
        target = set_of(JSON)
        self.assertTrue(semantic_subtyping.subset(source, target))
        self.assertTrue(semantic_types.contains(source, [0.1, 0.9]))
        self.assertTrue(semantic_types.contains(target, [0.1, 0.9]))

    def test_union_element_contract_does_not_hide_real_json_collision(self):
        source = {'type': 'union', 'variants': [REAL, STRING]}
        target = {'type': 'union', 'variants': [JSON, STRING]}
        self.assert_unsound_witness_rejected(source, target, [1, 1.0])

    def test_confirmed_compiler_must_not_prove_false_real_set_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            source = direct_set_effect_sources(Path(temp), 'real')
            with self.assertRaisesRegex(Blocked, 'Effect output.accepted: type mismatch'):
                load(*source, allow_partial=True)

    def test_confirmed_compiler_and_independent_model_keep_safe_integer_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = direct_set_effect_sources(root, 'integer')
            compiled = load(*source, allow_partial=True)
            self.assertEqual(compiled['status'], 'confirmed')
            self.assertEqual(compiled['unverified_effect_ids'], [])
            self.assertEqual(
                {item['result'] for item in compiled['effect_checks'].values()},
                {'proved'})
            model_path = root / 'TestModel.json'
            model_path.write_text(json.dumps(compiled), encoding='utf-8')
            self.assertEqual(model_conformance(*source, model_path)['status'],
                             'passed')

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
