"""W05/W06: source-bound generic type refs must never imply invented UUID/Delta meaning."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from catlib import semantic_types as typed
from cat_compile_v2 import load, Blocked, format_domain, parse_domain_text
import cat_model_conformance as conformance
from test_cat_compile_readable import write_v2, fm
from test_typed_spec_test_sync import approve_fixture


def definitions(root,body):
    ds=root/'DomainSpec.md'
    ds.write_text(fm('domain-spec','demo.types',[],language='en')+
                  '\n## Types\n| ID | Domain |\n| --- | --- |\n'+body,encoding='utf-8')
    approve_fixture(ds)
    return ds


class GenericTypeReferences(unittest.TestCase):
    def test_unresolved_type_reference_never_claims_a_shape(self):
        unresolved=typed.parse('型参照<UUID>')
        self.assertEqual(unresolved,{'type':'reference','name':'UUID','resolved':False})
        self.assertEqual(typed.parse('record<id:型参照<UUID>>')['fields'][0]['domain'],unresolved)
        typed.validate(unresolved)
        with self.assertRaises(typed.DomainError):
            typed.contains(unresolved,'anything')
        self.assertIsNone(typed.finite_values(unresolved))
        self.assertEqual(parse_domain_text(format_domain(unresolved,'ja')),unresolved)

    def test_scalar_enum_and_structural_declarations_have_fresh_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,pi,t=write_v2(root,False)
            for src in (p,pi,t):approve_fixture(src)
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.enabled | receive | boolean | required |',
                '| input.enabled | receive | boolean | required |\n'
                '| input.data | receive | record<id:型参照<UUID>,mode:型参照<Mode>> | required |'),
                encoding='utf-8')
            ds=definitions(root,'| UUID | string |\n| Mode | enum{A,B} |\n')
            model=load(p,pi,t,domain_specs=[ds])
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['unresolved_domains'],[])
            d=next(x['domain'] for x in model['fields'] if x['id']=='input.data')
            self.assertEqual(d['fields'][0]['domain']['type'],'reference')
            self.assertEqual(d['fields'][1]['domain']['of']['values'],['A','B'])
            self.assertEqual(d['fields'][0]['domain']['definition_source'],'demo.types')
            self.assertTrue(typed.contains(d,{'id':'example','mode':'A'}))
            self.assertFalse(typed.contains(d,{'id':4,'mode':'A'}))
            self.assertFalse(typed.contains(d,{'id':'example','mode':'C'}))
            ref=d['fields'][1]['domain']
            self.assertEqual(parse_domain_text(format_domain(ref,'ja')),
                             {'type':'reference','name':'Mode','resolved':False})
            path=root/'model.json';path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(conformance.validate(p,pi,[t],path,domain_specs=[ds])['status'],'passed')
            ref['of']['values']=['A','C']
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=conformance.validate(p,pi,[t],path,domain_specs=[ds])
            self.assertEqual(result['status'],'blocked')
            self.assertIn('domains',result['mismatches'])

    def test_unknown_source_alias_stays_draft_and_does_not_prove_intrinsic_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,pi,t=write_v2(root,False)
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.enabled | receive | boolean | required |',
                '| input.enabled | receive | boolean | required |\n'
                '| input.data | receive | 型参照<Unknown> | required |'),encoding='utf-8')
            m=load(p,pi,t,allow_draft=True)
            self.assertEqual(m['status'],'draft')
            self.assertIn('input.data',m['unresolved_domains'])

    def test_type_reference_cycles_and_missing_definition_are_rejected(self):
        for content in (
            '| A | 型参照<B> |\n| B | 型参照<A> |\n',
            '| A | 型参照<Missing> |\n',
        ):
            with self.subTest(content=content),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);p,pi,t=write_v2(root,False)
                ds=definitions(root,content)
                with self.assertRaisesRegex(Blocked,'cyclic|unresolved'):
                    load(p,pi,t,allow_draft=True,domain_specs=[ds])

    def test_named_record_legacy_syntax_remains_source_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,pi,t=write_v2(root,False)
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.enabled | receive | boolean | required |',
                '| input.enabled | receive | boolean | required |\n'
                '| input.data | receive | record<Change> | required |'),encoding='utf-8')
            ds=definitions(root,'| Change | record<name:string,note[optional]:nullable<string>> |\n')
            model=load(p,pi,t,allow_draft=True,domain_specs=[ds])
            d=next(x['domain'] for x in model['fields'] if x['id']=='input.data')
            self.assertEqual(d['type'],'record')
            self.assertEqual(d['name'],'Change')
            self.assertTrue(d['resolved'])
            self.assertTrue(typed.contains(d,{'name':'ok'}))


if __name__=='__main__':unittest.main()
