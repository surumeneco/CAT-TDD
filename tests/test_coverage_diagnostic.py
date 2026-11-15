"""UP20-05: distinguish nonproof reasons without inventing closure."""
import hashlib,json,sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_coverage_diagnostic as diagnostic

SHA='a'*64

def fixture(domain,reason='guard reads non-finite or too-large domain/Presence'):
    return {'schema':'cat-test-model/v2','process':'test',
            'fields':[{'id':'input.value','role':'input','domain':domain}],
            'coverage_checks':{'run':{'result':'unproven','reason':reason,
                                      'guard_refs':['input.value']}},
            'source_records':[{'id':'source.rules','sha256':SHA}],
            'normative_rule_inputs':[{'id':'source.rules','sha256':SHA}],
            'unverified_rule_ids':['rule'],
            'rule_obligations':[{'id':'rule','source_artifact':'source.rules',
                                  'verification_contract':'external runner not-run',
                                  'verification_status':'unverified'}]}

def audit(model):
    return diagnostic.explain(model,json.dumps(model,sort_keys=True).encode())

class CoverageDiagnosticTests(unittest.TestCase):
    def test_unbounded_string_explicit_nonfinite_reason_without_pass(self):
        r=audit(fixture({'type':'string'}))
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['kind'],'nonfinite-domain')
        self.assertEqual(r['formal_gate_status'],'not-run')
        self.assertEqual(r['local_coverage'][0]['compiler_verdict'],'unproven')
    def test_unresolved_type_is_not_renamed_nonfinite(self):
        r=audit(fixture({'type':'reference','name':'JSON','resolved':False}))
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['kind'],'unresolved-type-reference')
    def test_finite_integer_above_cap_is_distinct(self):
        r=audit(fixture({'type':'integer','min':0,'max':65536}))
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['kind'],'finite-cardinality-cap')
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['lower_bound'],65537)
    def test_finite_product_limit_keeps_count(self):
        m=fixture({'type':'boolean'},reason='finite closure exceeds configured 65536 combinations')
        m['coverage_checks']['run']['combination_count']=100000
        r=audit(m)
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['kind'],'finite-product-cap')
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['combination_count'],100000)
    def test_optional_effect_read_is_presence_specific(self):
        r=audit(fixture({'type':'boolean'},reason='Effect reads a non-required PI input'))
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['kind'],'unsafe-presence-read')
    def test_uncovered_and_conflict_remain_distinct(self):
        for verdict,key,kind in [('uncovered','uncovered_count','finite-guard-gap'),
                                 ('conflict','overlap_count','guard-overlap')]:
            m=fixture({'type':'boolean'});m['coverage_checks']['run']={'result':verdict,key:2}
            out=audit(m)['local_coverage'][0]
            self.assertEqual(out['compiler_verdict'],verdict)
            self.assertEqual(out['reason_categories'][0]['kind'],kind)
    def test_existing_rule_status_and_sha_are_not_upgraded(self):
        r=audit(fixture({'type':'string'}))
        self.assertEqual(r['unverified_rules'][0]['source_sha256'],SHA)
        self.assertEqual(r['unverified_rules'][0]['category'],'unverified-normative-rule')
        self.assertEqual(r['source_conformance_status'],'not-run')
    def test_malformed_duplicate_rule_cannot_hide_obligation(self):
        m=fixture({'type':'boolean'});m['rule_obligations'].append(m['rule_obligations'][0])
        with self.assertRaisesRegex(diagnostic.CoverageDiagnosticError,'duplicate Rule'):
            audit(m)
    def test_missing_source_pin_rejected(self):
        m=fixture({'type':'boolean'});m['source_records'][0]['sha256']='b'*64
        with self.assertRaisesRegex(diagnostic.CoverageDiagnosticError,'Source Rule input identity mismatch'):
            audit(m)
    def test_undefined_record_presence_not_confused_with_null(self):
        d={'type':'record','resolved':True,'fields':[{'id':'x','presence':'undefined',
             'domain':{'type':'nullable','of':{'type':'integer','min':0,'max':1}}}]}
        r=audit(fixture(d))
        self.assertEqual(r['local_coverage'][0]['reason_categories'][0]['kind'],
                         'undefined-presence-not-enumerable')
if __name__=='__main__':unittest.main()
