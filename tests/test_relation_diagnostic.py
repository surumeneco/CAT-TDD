"""UP20-04: relational fixtures, not approved Style/HOCON conformance."""
import hashlib,json,sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_relation_diagnostic as relation
from catlib import fixture_probe

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
    def test_generic_identity_accepts_an_alternate_projection_without_marker_fields(self):
        fixture={'validated':{'objects_by_id':{'a':{'owner':'other'},'b':{'owner':'other'}},
                              'links_by_id':{'a':'b'}}}
        data=json.dumps(fixture,sort_keys=True).encode()
        contract={'schema':'cat-relation-probe/v1','source_artifact':'demo.styles',
                  'source_sha256':hashlib.sha256(SOURCE).hexdigest(),
                  'rule_id':'style.links','fixture_sha256':hashlib.sha256(data).hexdigest(),
                  'relation':'alternative-reference-projection/v1'}
        decoded,evidence=fixture_probe.verify_identity(SOURCE,data,contract)
        self.assertEqual(decoded,fixture)
        self.assertEqual(evidence['relation'],'alternative-reference-projection/v1')
        self.assertEqual(evidence['normative_status'],'inconclusive')
        self.assertEqual(evidence['formal_gate_status'],'not-run')
        self.assertNotIn('status',evidence)  # identity alone has no verdict
        # The legacy marker CLI must not silently accept a different profile.
        with self.assertRaisesRegex(relation.RelationError,'unsupported relation predicate'):
            relation.inspect(SOURCE,data,contract)

    def test_generic_identity_rejects_spoofed_source_or_fixture_on_any_projection(self):
        fixture={'validated':{'objects_by_id':{'a':{}},'links_by_id':{}}}
        data=json.dumps(fixture).encode()
        contract={'schema':'cat-relation-probe/v1','source_artifact':'demo.styles',
                  'source_sha256':hashlib.sha256(SOURCE).hexdigest(),
                  'rule_id':'style.links','fixture_sha256':hashlib.sha256(data).hexdigest(),
                  'relation':'alternative-reference-projection/v1'}
        with self.assertRaisesRegex(relation.RelationError,'fixture SHA-256 mismatch'):
            fixture_probe.verify_identity(SOURCE,data+b' ',contract)
        with self.assertRaisesRegex(relation.RelationError,'Source SHA-256 mismatch'):
            fixture_probe.verify_identity(SOURCE+b'\n',data,contract)

    def test_marker_profile_is_optional_and_does_not_expand_common_gate(self):
        original=check(base())
        self.assertEqual(original['status'],'passed-fixture-only')
        self.assertEqual(original['normative_status'],'inconclusive')
        self.assertEqual(original['formal_gate_status'],'not-run')
        self.assertEqual(original['external_hocon_status'],'not-run')
        self.assertEqual(original['verification_scope'],'fixture-relational-integrity-only')
if __name__=='__main__':unittest.main()
