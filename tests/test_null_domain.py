"""W05-W08: singleton null is neither an absent field nor a nullable guess."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from catlib import semantic_types as typed
from cat_compile_v2 import load,parse_domain_text,format_domain,selection_vectors
from cat_process_composition import _type_subset
from cat_model_conformance import validate as model_conformance
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture
from test_generic_type_references import definitions


class NullOnlyDomainTests(unittest.TestCase):
    def test_singleton_null_roundtrips_without_optional_or_undefined(self):
        for spelling in ('null','明示null'):
            with self.subTest(spelling=spelling):
                d=typed.parse(spelling)
                self.assertEqual(d,{'type':'null'})
                self.assertIs(typed.validate(d),d)
                self.assertTrue(typed.contains(d,None))
                for other in (False,0,'',[],{},'null'):
                    self.assertFalse(typed.contains(d,other))
                self.assertEqual(typed.finite_values(d),[None])
                self.assertEqual(parse_domain_text(format_domain(d,'ja')),d)
                self.assertEqual(parse_domain_text(format_domain(d,'en')),d)
                self.assertEqual(typed.check_presence(d,'required',None),('null',True))
                self.assertEqual(typed.check_presence(d,'optional',typed.MISSING),
                                 ('missing',True))
                self.assertEqual(typed.check_presence(d,'undefined',typed.UNDEFINED),
                                 ('undefined',True))
                self.assertEqual(typed.check_presence(d,'undefined',None),
                                 ('null',False))

    def test_nullable_null_has_only_one_finite_value(self):
        self.assertEqual(typed.finite_values(typed.parse('nullable<null>')),[None])
        self.assertEqual(typed.finite_values(typed.parse('union<null,boolean>')),
                         [None,False,True])

    def test_null_domain_is_source_bound_named_type_not_assumed_from_alias(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p,pi,t=write_v2(root,False)
            for src in (p,pi,t):approve_fixture(src)
            ds=definitions(root,'| 明示null | null |\n')
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                '| input.enabled | receive | boolean | required |',
                '| input.enabled | receive | boolean | required |\n'
                '| input.empty | receive | 型参照<明示null> | required |'),encoding='utf-8')
            model=load(p,pi,t,domain_specs=[ds])
            self.assertEqual(model['status'],'confirmed')
            domain=next(x['domain'] for x in model['fields'] if x['id']=='input.empty')
            self.assertEqual(domain['type'],'reference')
            self.assertEqual(domain['of'],{'type':'null'})
            vectors=selection_vectors(model)
            self.assertTrue(all(case['input']['input.empty'] is None for case in vectors['cases']))
            mp=root/'Model.json'
            mp.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(model_conformance(p,pi,[t],mp,domain_specs=[ds])['status'],'passed')
            domain['of']={'type':'string'}
            mp.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(model_conformance(p,pi,[t],mp,domain_specs=[ds])['status'],'blocked')

    def test_process_composition_preserves_null_subtyping(self):
        null=typed.parse('null')
        nullable_text=typed.parse('nullable<string>')
        text=typed.parse('string')
        self.assertIs(_type_subset(null,nullable_text),True)
        self.assertIs(_type_subset(null,text),False)
        self.assertIs(_type_subset(nullable_text,null),False)
        self.assertIs(_type_subset(null,typed.parse('union<null,string>')),True)


if __name__=='__main__':unittest.main()
