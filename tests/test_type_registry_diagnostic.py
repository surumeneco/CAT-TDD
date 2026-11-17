"""UP20-01: source-bound named type failure diagnosis, without type invention."""
from __future__ import annotations
import sys, json, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system' / 'scripts'))
from catlib import semantic_named_types as named, semantic_rules
import cat_named_type_diagnostic as diagnostic


def decl(name, domain, source='demo.types', source_sha='a'*64):
    return {'name':name,'domain':domain,'source_artifact':source,'source_sha256':source_sha}

def ref(name):
    return {'type':'reference','name':name,'resolved':False}

def record(fields):
    return {'type':'record','resolved':True,'fields':[
        {'id':n,'domain':d,'presence':'required'} for n,d in fields]}

class RegistryDiagnosticTests(unittest.TestCase):
    def test_missing_nested_alias_reports_declared_root_and_exact_path(self):
        delta=record([('ops',{'type':'sequence','element':record([
            ('attributes', ref('JSON'))])})])
        defs={'Delta':decl('Delta',delta),
              'Article':decl('Article',record([('body_delta',ref('Delta'))]),'article.types','b'*64)}
        result=diagnostic.diagnose(defs)
        self.assertEqual(result['declared_count'],2)
        self.assertEqual(result['resolved_count'],0)
        self.assertFalse(result['all_resolved'])
        root={x['name']:x for x in result['types']}
        self.assertEqual(root['Delta']['issues'][0]['dependency_chain'],['Delta','JSON'])
        self.assertEqual(root['Delta']['issues'][0]['missing_name'],'JSON')
        self.assertIn('ops',root['Delta']['issues'][0]['field_path'])
        self.assertEqual(root['Article']['issues'][0]['dependency_chain'],['Article','Delta','JSON'])
        self.assertEqual(root['Article']['issues'][0]['source_artifact'],'article.types')
        self.assertEqual(root['Article']['issues'][0]['source_sha256'],'b'*64)
        self.assertEqual(result['status'],'diagnostic')  # Never a formal Gate

    def test_existing_defined_chain_resolves_and_retains_provenance(self):
        defs={'UUID':decl('UUID',{'type':'string'}),
              'Owner':decl('Owner',record([('id',ref('UUID'))]))}
        result=diagnostic.diagnose(defs)
        self.assertEqual(result['resolved_count'],2)
        self.assertTrue(result['all_resolved'])
        self.assertTrue(all(x['status']=='resolved' for x in result['types']))
        self.assertEqual({x['source_artifact'] for x in result['types']},{'demo.types'})

    def test_missing_timestamp_does_not_turn_into_string(self):
        defs={'Article':decl('Article',record([('created_at',ref('時点'))]))}
        result=diagnostic.diagnose(defs)
        self.assertEqual(result['resolved_count'],0)
        self.assertEqual(result['missing_roots'],['時点'])
        self.assertEqual(result['types'][0]['issues'][0]['kind'],'missing-declaration')
        with self.assertRaises(named.NamedTypeError):named.resolved_definitions(defs)

    def test_cycles_are_reported_without_fabricating_a_resolution(self):
        defs={'Alpha':decl('Alpha',record([('next',ref('Beta'))])),
              'Beta':decl('Beta',record([('prev',ref('Alpha'))]))}
        result=diagnostic.diagnose(defs)
        self.assertEqual(result['resolved_count'],0)
        self.assertEqual(result['missing_roots'],[])
        self.assertTrue(all(x['issues'][0]['kind']=='cyclic-dependency' for x in result['types']))
        self.assertIn('Alpha',result['types'][0]['issues'][0]['dependency_chain'])

    def test_missing_and_known_union_arm_remains_unresolved_in_inventory(self):
        defs={'Notice':decl('Notice',{'type':'union','variants':[{'type':'string'},ref('UnknownNotice')]})}
        result=diagnostic.diagnose(defs)
        self.assertEqual(result['resolved_count'],0)
        self.assertEqual(result['missing_roots'],['UnknownNotice'])

    def test_draft_source_requires_opt_in_and_does_not_become_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'Demo.md'
            path.write_text('''---
cat_version: '0.3'
kind: domain-spec
id: demo.types
status: candidate
process: demo
source_refs:
  - https://example.org/original
refs: []
decision_ref: ''
semantic_contract: markdown-v2
language: en
---
## Types
| ID | Domain |
| --- | --- |
| Delta | record<attributes:ref<JSON>> |
''',encoding='utf-8')
            with self.assertRaises(semantic_rules.RuleError):
                semantic_rules.load_many([path],'demo',allow_draft=False)
            report=diagnostic.diagnose_sources([path],process='demo',allow_draft=True)
            self.assertEqual(report['inputs'][0]['status'],'candidate')
            self.assertEqual(report['declared_count'],1)
            self.assertEqual(report['missing_roots'],['JSON'])
            self.assertFalse(report['all_resolved'])

if __name__=='__main__':unittest.main()
