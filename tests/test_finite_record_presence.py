"""W07: exact finite Record Presence enumeration without invented states."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from catlib import semantic_types as typed
from cat_compile_v2 import load,selection_vectors
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture


class FiniteRecordPresenceTests(unittest.TestCase):
    def test_optional_and_absent_fields_produce_exact_closed_records(self):
        d=typed.parse('record<flag:boolean,note[optional]:nullable<enum{A,B}>,'
                      'deleted[absent]:integer>')
        values=typed.finite_values(d)
        self.assertIsNotNone(values)
        self.assertEqual(len(values),8)
        self.assertEqual(len({json.dumps(x,sort_keys=True) for x in values}),8)
        self.assertTrue(all('deleted' not in x for x in values))
        self.assertEqual({json.dumps(x,sort_keys=True) for x in values},
                         {json.dumps({'flag':flag,**({'note':note} if present else {})},
                                     sort_keys=True) for flag in (False,True)
                          for present in (False,True)
                          for note in ([None] if not present else [None,'A','B'])})
        self.assertTrue(all(typed.contains(d,x) for x in values))

    def test_nested_finite_records_with_optional_null_preserve_exact_values(self):
        d=typed.parse('record<inner:record<count:integer[1..2],'
                      'label[optional]:null>,status:enum{active,closed}>')
        values=typed.finite_values(d)
        self.assertIsNotNone(values)
        self.assertEqual(len(values),8)
        self.assertTrue(all(typed.contains(d,x) for x in values))
        self.assertEqual(sum('label' not in v['inner'] for v in values),4)
        self.assertEqual(sum(v['inner'].get('label','absent') is None for v in values),4)

    def test_undefined_nested_presence_is_not_serialized_as_an_ordinary_value(self):
        d=typed.parse('record<flag[undefined]:boolean>')
        self.assertIsNone(typed.finite_values(d))
        self.assertTrue(typed.contains(d,{'flag':typed.UNDEFINED}))

    def test_finite_cap_exact_and_no_approximation(self):
        d=typed.parse('record<a[optional]:boolean,b[optional]:boolean,c[optional]:boolean>')
        self.assertEqual(len(typed.finite_values(d,max_values=27)),27)
        self.assertIsNone(typed.finite_values(d,max_values=26))
        self.assertIsNone(typed.finite_values(
            typed.parse('record<a[optional]:string>')))

    def test_compiler_can_select_nested_presence_values_without_making_up_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,pi,t=write_v2(root,False)
            for src in (p,pi,t):approve_fixture(src)
            process_text=p.read_text(encoding='utf-8').replace(
                '| state.ready | boolean |',
                '| state.ready | record<active:boolean,note[optional]:boolean> |')
            p.write_text(process_text,encoding='utf-8')
            t.write_text(t.read_text(encoding='utf-8').replace(
                'state.ready = true; output.accepted = true',
                'output.accepted = true'),encoding='utf-8')
            model=load(p,pi,t)
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['coverage_requirement'],'closed')
            vectors=selection_vectors(model)
            self.assertEqual(len(vectors['cases']),2)
            self.assertTrue(all('state.ready' in c['state'] for c in vectors['cases']))
            self.assertTrue(all(typed.contains(
                next(x['domain'] for x in model['fields'] if x['id']=='state.ready'),
                c['state']['state.ready']) for c in vectors['cases']))


if __name__=='__main__':unittest.main()
