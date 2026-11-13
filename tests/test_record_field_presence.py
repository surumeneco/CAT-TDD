"""W06/W07: nested record field Presence is a source property, not a type rewrite."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from catlib import semantic_types as typed
import cat_compile_v2 as compiler
import cat_model_conformance as conformance
from test_cat_compile_readable import write_v2


class RecordFieldPresenceTests(unittest.TestCase):
    def test_recursive_record_optional_absent_undefined_and_nullable_are_separate(self):
        d=typed.parse('record<name:string,note[optional]:nullable<string>,'
                      'removed[absent]:boolean,flag[undefined]:boolean>')
        typed.validate(d)
        self.assertEqual([x['presence'] for x in d['fields']],
                         ['required','optional','absent','undefined'])
        self.assertTrue(typed.contains(d,{'name':'Ada'} if False else
                       {'name':'Ada','flag':typed.UNDEFINED}))
        self.assertTrue(typed.contains(d,{'name':'Ada','note':None,
                                          'flag':typed.UNDEFINED}))
        self.assertFalse(typed.contains(d,{'name':'Ada','note':False,
                                           'flag':typed.UNDEFINED}))
        self.assertFalse(typed.contains(d,{'name':'Ada','removed':False,
                                           'flag':typed.UNDEFINED}))
        self.assertFalse(typed.contains(d,{'name':'Ada'}))
        self.assertFalse(typed.contains(d,{'name':'Ada','note':None,
                                           'flag':None}))

    def test_roundtrip_preserves_field_presence_in_both_languages(self):
        for language,source in (
            ('ja','レコード<name:文字列,note[optional]:文字列またはnull>'),
            ('en','record<name:string,note[optional]:nullable<string>>'),
        ):
            with self.subTest(language=language):
                parsed=compiler.parse_domain_text(source)
                formatted=compiler.format_domain(parsed,language)
                self.assertEqual(compiler.parse_domain_text(formatted),parsed)
                self.assertIn('note[optional]',formatted)
                self.assertTrue(typed.contains(parsed,{'name':'Ada'}))
                self.assertTrue(typed.contains(parsed,{'name':'Ada','note':None}))
                self.assertFalse(typed.contains(parsed,{'name':'Ada','note':2}))

    def test_nested_inside_union_and_sequence(self):
        d=typed.parse('union<sequence<record<id:integer,remark[optional]:string>>,'
                      'record<state:enum{A,B}>>')
        typed.validate(d)
        self.assertTrue(typed.contains(d,[{'id':1},{'id':2,'remark':'ok'}]))
        self.assertFalse(typed.contains(d,[{'id':1,'remark':False}]))
        self.assertEqual(compiler.parse_domain_text(compiler.format_domain(d)),d)

    def test_rejects_unknown_presence_malformed_keys_and_duplicates(self):
        specs=(
            'record<x[maybe]:string>',
            'record<x[optional]:string,x:string>',
            'record<x[optional]:string,x[required]:string>',
            'record<x[]:string>',
            'record<x[optional:integer>',
            'record<x[optional][optional]:integer>',
        )
        for spec in specs:
            with self.subTest(spec=spec),self.assertRaises((typed.DomainError,compiler.Blocked)):
                typed.parse(spec)

    def test_compiler_and_independent_model_conformance_retain_nested_presence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p,pi,t=write_v2(root,False)
            needle='| input.enabled | receive | boolean | required |'
            self.assertIn(needle,pi.read_text(encoding='utf-8'))
            pi.write_text(pi.read_text(encoding='utf-8').replace(
                needle,needle+'\n| input.data | receive | '
                'record<name:string,note[optional]:nullable<string>> | required |'),
                encoding='utf-8')
            model=compiler.load(p,pi,t,allow_draft=True)
            field=next(x for x in model['fields'] if x['id']=='input.data')
            self.assertEqual(field['domain']['fields'][1]['presence'],'optional')
            self.assertEqual(model['status'],'draft')
            path=root/'model.json'
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(conformance.validate(p,pi,[t],path,allow_draft=True)['status'],'passed')
            field['domain']['fields'][1]['presence']='required'
            path.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=conformance.validate(p,pi,[t],path,allow_draft=True)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('domains',result['mismatches'])


if __name__=='__main__':unittest.main()
