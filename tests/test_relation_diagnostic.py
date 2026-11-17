"""UP20-04: relational fixtures, not approved Style/HOCON conformance."""
import hashlib,json,sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_relation_diagnostic as relation

SOURCE=b'''---
kind: domain-spec
id: demo.styles
status: candidate
---
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| style.links | candidate | See source decision | inspect |
'''

def base():
    markers=[{'id':'m1','owner':{'kind':'account'},'kind':'shape'},
             {'id':'m2','owner':{'kind':'account'},'kind':'line'}]
    first={'owner_kind':'account','approved_color':{'r':10,'g':20,'b':30}}
    second={'owner_kind':'account','approved_color':{'r':70,'g':80,'b':90}}
    fixture={'validated':{'api_markers':markers,'api_styles':[first,second],
                           'marker_styles':[{'marker_id':'m1','style':first},
                                            {'marker_id':'m2','style':second}]}}
    return fixture

def check(fixture,source=SOURCE):
    data=json.dumps(fixture,sort_keys=True,ensure_ascii=False).encode()
    contract={'schema':'cat-relation-probe/v1','source_artifact':'demo.styles',
              'source_sha256':hashlib.sha256(source).hexdigest(),
              'rule_id':'style.links','fixture_sha256':hashlib.sha256(data).hexdigest(),
              'relation':'marker-style-references/v1'}
    return relation.inspect(source,data,contract)

class RelationTests(unittest.TestCase):
    def test_two_distinct_colors_preserved_without_unique_style_owner_assumption(self):
        result=check(base())
        self.assertEqual(result['status'],'passed-fixture-only')
        self.assertEqual(result['normative_status'],'inconclusive')
        self.assertEqual(result['external_hocon_status'],'not-run')
    def test_same_style_may_be_shared_by_distinct_markers(self):
        fixture=base()
        fixture['validated']['marker_styles'][1]['style']=fixture['validated']['api_styles'][0]
        self.assertEqual(check(fixture)['status'],'passed-fixture-only')
    def test_unknown_marker_reference_fails_fixture(self):
        fixture=base();fixture['validated']['marker_styles'][1]['marker_id']='m404'
        errors=check(fixture)['errors']
        self.assertIn('unknown-marker-reference',{x['reason'] for x in errors})
    def test_duplicate_marker_id_and_link_fail_fixture(self):
        fixture=base();fixture['validated']['api_markers'][1]['id']='m1'
        fixture['validated']['marker_styles'][1]['marker_id']='m1'
        names={x['reason'] for x in check(fixture)['errors']}
        self.assertIn('duplicate-marker-id',names)
        self.assertIn('duplicate-marker-style-link',names)
    def test_owner_mismatch_fails_fixture(self):
        fixture=base();fixture['validated']['api_markers'][0]['owner']['kind']='company'
        self.assertIn('owner-kind-mismatch',{x['reason'] for x in check(fixture)['errors']})
    def test_style_must_be_present_among_api_styles(self):
        fixture=base();fixture['validated']['marker_styles'][0]['style']={'owner_kind':'account','approved_color':'green'}
        self.assertIn('style-not-declared-in-api-styles',
                      {x['reason'] for x in check(fixture)['errors']})
    def test_empty_collections_are_structurally_consistent_but_not_product_proof(self):
        fixture={'validated':{'api_markers':[],'api_styles':[],'marker_styles':[]}}
        self.assertEqual(check(fixture)['status'],'passed-fixture-only')
        self.assertEqual(check(fixture)['normative_status'],'inconclusive')
    def test_missing_validated_has_no_relational_proof(self):
        self.assertEqual(check({})['status'],'inconclusive')
    def test_source_bytes_cannot_be_rebound_by_same_id(self):
        fixture=base();data=json.dumps(fixture,sort_keys=True,ensure_ascii=False).encode()
        contract={'schema':'cat-relation-probe/v1','source_artifact':'demo.styles',
                  'source_sha256':'0'*64,'rule_id':'style.links',
                  'fixture_sha256':hashlib.sha256(data).hexdigest(),
                  'relation':'marker-style-references/v1'}
        with self.assertRaisesRegex(relation.RelationError,'Source SHA-256 mismatch'):
            relation.inspect(SOURCE,data,contract)
    def test_source_rule_id_must_exist(self):
        fixture=base();data=json.dumps(fixture,sort_keys=True,ensure_ascii=False).encode()
        contract={'schema':'cat-relation-probe/v1','source_artifact':'demo.styles',
                  'source_sha256':hashlib.sha256(SOURCE).hexdigest(),
                  'rule_id':'invented.rule',
                  'fixture_sha256':hashlib.sha256(data).hexdigest(),
                  'relation':'marker-style-references/v1'}
        with self.assertRaisesRegex(relation.RelationError,'source Rule ID absent'):
            relation.inspect(SOURCE,data,contract)
if __name__=='__main__':unittest.main()
