"""W07/W08: missing, undefined, null and value states are not interchangeable."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import Blocked, load, selection_vectors, expand_cases, emit_vitest
from test_cat_compile_readable import write_v2
from test_typed_spec_test_sync import approve_fixture


def source(root,presence='optional',accept='is_present(input.enabled) and input.enabled',
           reject='not (is_present(input.enabled) and input.enabled)',operation=False):
    p,pi,t=write_v2(root,False)
    pi.write_text(pi.read_text(encoding='utf-8').replace(
        '| input.enabled | receive | boolean | required |',
        f'| input.enabled | receive | boolean | {presence if not operation else "required"} |')
        +(('\n## Operation presence\n| Operation | Field | Presence |\n| --- | --- | --- |\n'
           f'| submit_op | input.enabled | {presence} |\n') if operation else ''),
        encoding='utf-8')
    t.write_text(t.read_text(encoding='utf-8').replace(
        '| demo.accept | submit | `input.enabled` |',
        f'| demo.accept | submit | `{accept}` |').replace(
        '| demo.reject | submit | `not input.enabled` |',
        f'| demo.reject | submit | `{reject}` |'),encoding='utf-8')
    for path in (p,pi,t):approve_fixture(path)
    return p,pi,t


class PresenceClosureTests(unittest.TestCase):
    def test_optional_missing_and_value_are_partitioned_with_full_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,t=source(Path(tmp))
            m=load(p,pi,t)
            self.assertEqual(m['coverage_requirement'],'closed')
            self.assertEqual(m['status'],'confirmed')
            self.assertEqual(m['presence_unproven'],[])
            vs=selection_vectors(m)
            cases=expand_cases(m,vs)
            self.assertEqual({c['source_tce'] for c in cases},{'demo.accept','demo.reject'})
            self.assertEqual(next(c for c in cases if c['source_tce']=='demo.reject')['input'],{})
            self.assertEqual(next(c for c in cases if c['source_tce']=='demo.accept')['input'],
                             {'input.enabled':True})
            self.assertEqual(selection_vectors(m),vs)

    def test_operation_presence_override_is_used_in_closure_and_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,t=source(Path(tmp),operation=True)
            m=load(p,pi,t)
            self.assertEqual(m['coverage_requirement'],'closed')
            self.assertEqual(m['status'],'confirmed')
            vs=selection_vectors(m)
            self.assertTrue(all(x.get('operation')=='submit_op' for x in vs['cases']))
            self.assertEqual(len(expand_cases(m,vs)),2)

    def test_unguarded_optional_read_never_proves_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,pi,t=source(Path(tmp),accept='input.enabled',reject='not input.enabled')
            m=load(p,pi,t,allow_draft=True)
            self.assertEqual(m['coverage_requirement'],'partial')
            self.assertEqual(m['status'],'draft')
            self.assertEqual(m['coverage_checks']['submit']['result'],'unproven')
            self.assertIn('input.enabled',m['presence_unproven'])

    def test_absent_and_undefined_are_distinct(self):
        for presence,guard in (('absent','is_missing(input.enabled)'),
                               ('undefined','is_undefined(input.enabled)')):
            with self.subTest(presence=presence),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                p,pi,t=source(root,presence,guard,'false')
                t.write_text('\n'.join(line for line in t.read_text(encoding='utf-8').splitlines()
                                       if '| demo.reject |' not in line)+'\n',encoding='utf-8')
                m=load(p,pi,t)
                self.assertEqual(m['status'],'confirmed')
                vs=selection_vectors(m)
                self.assertEqual(len(vs['cases']),1)
                self.assertEqual(vs['cases'][0]['input'],
                                 {} if presence=='absent' else
                                 {'input.enabled':{'$cat_presence':'undefined'}})
                self.assertEqual(len(expand_cases(m,vs)),1)
                if presence=='undefined':
                    binding=root/'binding.json'
                    binding.write_text(json.dumps({
                        'schema':'cat-test-driver/v2','process':'demo.process',
                        'driver':'./driver'}),encoding='utf-8')
                    with self.assertRaisesRegex(Blocked,'undefined transport'):
                        emit_vitest(m,vs,binding)

    def test_optional_nullable_null_is_distinct_from_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,pi,t=source(root,presence='optional',
                accept='is_missing(input.enabled)',
                reject='is_present(input.enabled)')
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                'input.enabled | receive | boolean | optional',
                'input.enabled | receive | nullable<boolean> | optional'),encoding='utf-8')
            m=load(p,pi,t)
            self.assertEqual(m['status'],'confirmed')
            vs=selection_vectors(m)
            self.assertEqual(len(vs['cases']),2)
            self.assertEqual(vs['cases'][0]['input'],{})
            present=next(x for x in vs['cases'] if x['id']=='case.demo.reject')
            self.assertEqual(present['input'],{'input.enabled':None})

    def test_nonrequired_output_does_not_pass_without_operation_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t=source(root,presence='required',accept='input.enabled',
                          reject='not input.enabled')
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| output.accepted | send | boolean | required |',
                '| output.accepted | send | boolean | optional |'),encoding='utf-8')
            m=load(p,pi,t,allow_draft=True)
            self.assertEqual(m['status'],'draft')
            self.assertIn('output.accepted',m['presence_unproven'])


if __name__=='__main__':unittest.main()
