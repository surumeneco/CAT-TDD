#!/usr/bin/env python3
"""Effect source/target type identities must be preserved by the compiler."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from cat_compile_v2 import Blocked, load
from test_cat_compile_readable import write_v2

class EffectTypedIdentityTests(unittest.TestCase):
    def fixture(self, root, source, target):
        p, pi, tce = write_v2(root, False)
        p.write_text(p.read_text(encoding='utf-8').replace(
            'state.ready | boolean', f'state.ready | enum{{{source}}}'), encoding='utf-8')
        pi.write_text(pi.read_text(encoding='utf-8').replace(
            'output.accepted | send | boolean',
            f'output.accepted | send | {target}'), encoding='utf-8')
        tce.write_text(tce.read_text(encoding='utf-8')
            .replace('output.accepted = true','output.accepted = state.ready')
            .replace('output.accepted = false','output.accepted = state.ready'),encoding='utf-8')
        return p,pi,tce

    def test_nullable_boolean_enum_must_not_accept_integer_enum(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(Path(td),'true','nullable<enum{1}>')
            with self.assertRaisesRegex(Blocked,'Effect output.accepted: type mismatch'):
                load(*args,allow_draft=True,allow_partial=True)

    def test_union_boolean_enum_must_not_accept_integer_enum_branch(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(Path(td),'true','union<enum{1},enum{2}>')
            with self.assertRaisesRegex(Blocked,'Effect output.accepted: type mismatch'):
                load(*args,allow_draft=True,allow_partial=True)

    def test_integer_reference_must_fit_narrower_output_range(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.fixture(Path(td),'true','integer[0..5]')
            old=p.read_text(encoding='utf-8')
            p.write_text(old.replace('state.ready | enum{true}',
                                     'state.ready | integer[0..10]'),encoding='utf-8')
            original=tce.read_text(encoding='utf-8')
            tce.write_text(original.replace('state.ready = true',
                                            'state.ready = 0'),encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'Effect output.accepted: type mismatch'):
                load(p,pi,tce,allow_draft=True,allow_partial=True)

    def test_integer_reference_can_fit_wider_output_range(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.fixture(Path(td),'true','integer[0..10]')
            p.write_text(p.read_text(encoding='utf-8').replace(
                'state.ready | enum{true}',
                'state.ready | integer[0..5]'),encoding='utf-8')
            tce.write_text(tce.read_text(encoding='utf-8').replace(
                'state.ready = true','state.ready = 0'),encoding='utf-8')
            self.assertEqual(load(p,pi,tce,allow_draft=True,allow_partial=True)['status'],'draft')

    def test_set_of_string_cannot_be_copied_to_set_of_integer(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.fixture(Path(td),'true','set<integer>')
            p.write_text(p.read_text(encoding='utf-8').replace(
                'state.ready | enum{true}',
                'state.ready | set<string>'),encoding='utf-8')
            tce.write_text(tce.read_text(encoding='utf-8').replace(
                'state.ready = true; ',''),encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'Effect output.accepted: type mismatch'):
                load(p,pi,tce,allow_draft=True,allow_partial=True)

    def test_out_of_range_integer_literal_is_rejected_at_compile(self):
        with tempfile.TemporaryDirectory() as td:
            p,pi,tce=self.fixture(Path(td),'true','integer[0..1]')
            tce.write_text(tce.read_text(encoding='utf-8').replace(
                'output.accepted = state.ready','output.accepted = 2'),encoding='utf-8')
            with self.assertRaisesRegex(Blocked,'Effect output.accepted: type mismatch'):
                load(p,pi,tce,allow_draft=True,allow_partial=True)

    def test_same_typed_nullable_and_union_branches_remain_accepted(self):
        for target in ('nullable<enum{true}>','union<enum{true},enum{false}>'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as td:
                args=self.fixture(Path(td),'true',target)
                model=load(*args,allow_draft=True,allow_partial=True)
                self.assertEqual(model['status'],'draft')

if __name__=='__main__':unittest.main()
