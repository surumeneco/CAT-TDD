"""W05/W06: explicit DomainSpec named records preserve shape and provenance."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import load,Blocked
import cat_model_conformance as conformance
from catlib import semantic_types
from test_cat_compile_readable import write_v2,fm


def spec(root,rows,name='DomainSpec.md',artifact='demo.types'):
    path=root/name
    path.write_text(fm('domain-spec',artifact,[],language='en')+
                    '\n## Types\n| ID | Domain |\n| --- | --- |\n'+rows,encoding='utf-8')
    return path


def add_named_field(pi,type_expr='record<Change>'):
    text=pi.read_text(encoding='utf-8')
    anchor='| input.enabled | receive | boolean | required |'
    assert anchor in text
    pi.write_text(text.replace(anchor,anchor+'\n| input.data | receive | '+type_expr+' | required |'),encoding='utf-8')


class NamedRecordTests(unittest.TestCase):
    def test_nested_records_have_source_hash_and_independent_conformance(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t=write_v2(root,False);add_named_field(pi)
            ds=spec(root,'| User | record<name:string,active:boolean> |\n'
                         '| Change | record<owner:record<User>,mode:nullable<enum{A,B}>> |\n')
            model=load(p,pi,t,allow_draft=True,domain_specs=[ds])
            field=next(x for x in model['fields'] if x['id']=='input.data')
            self.assertEqual(field['domain']['name'],'Change')
            self.assertEqual(field['domain']['definition_source'],'demo.types')
            self.assertEqual(len(field['domain']['definition_sha256']),64)
            self.assertTrue(semantic_types.contains(field['domain'],
                            {'owner':{'name':'alice','active':True},'mode':'B'}))
            self.assertFalse(semantic_types.contains(field['domain'],
                             {'owner':{'name':'alice','active':1},'mode':'B'}))
            self.assertEqual(len(model['named_type_definitions']),2)
            self.assertEqual(model['status'],'draft')  # source is Draft, not Confirmed
            target=root/'model.json'
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(conformance.validate(p,pi,[t],target,domain_specs=[ds],allow_draft=True)['status'],'passed')
            field['domain']['fields'][0]['domain']['fields'][1]['domain']={'type':'string'}
            target.write_text(json.dumps(model,ensure_ascii=False),encoding='utf-8')
            result=conformance.validate(p,pi,[t],target,domain_specs=[ds],allow_draft=True)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('domains',result['mismatches'])

    def test_undeclared_named_record_does_not_become_resolved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t=write_v2(root,False);add_named_field(pi)
            model=load(p,pi,t,allow_draft=True)
            self.assertIn('input.data',model['unresolved_domains'])
            self.assertEqual(model['status'],'draft')

    def test_cyclic_type_declarations_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t=write_v2(root,False);add_named_field(pi)
            ds=spec(root,'| Change | record<owner:record<User>> |\n'
                         '| User | record<change:record<Change>> |\n')
            with self.assertRaisesRegex(Blocked,'cyclic named type'):
                load(p,pi,t,allow_draft=True,domain_specs=[ds])

    def test_duplicate_types_from_independent_artifacts_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t=write_v2(root,False);add_named_field(pi)
            a=spec(root,'| Change | record<value:boolean> |\n',name='A.md',artifact='demo.a')
            b=spec(root,'| Change | record<value:string> |\n',name='B.md',artifact='demo.b')
            with self.assertRaisesRegex(Blocked,'duplicate named type'):
                load(p,pi,t,allow_draft=True,domain_specs=[a,b])

    def test_missing_referenced_type_causes_unresolved_definition(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,pi,t=write_v2(root,False);add_named_field(pi)
            ds=spec(root,'| Change | record<owner:record<Missing>> |\n')
            with self.assertRaisesRegex(Blocked,'unresolved named type definition'):
                load(p,pi,t,allow_draft=True,domain_specs=[ds])


if __name__=='__main__':unittest.main()
