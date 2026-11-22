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
    def test_unverified_optional_value_read_exposes_field_and_owned_operation(self):
        m=fixture({'type':'enum','values':['approve','reject']},
                  reason='ordinary expression reads missing/undefined field input.value')
        m['fields'][0].update(presence='optional',source_pi='demo.pi')
        m['pi_operations']=[{'id':'review','direction':'accept',
                             'trigger':'run','source_pi':'demo.pi'}]
        m['operation_presence']=[]
        m['rules']=[{'id':'review.approve','trigger':'run',
                     'when':{'op':'eq','args':[{'ref':'input.value'},{'literal':'approve'}]}}]
        r=audit(m)['local_coverage'][0]
        c=r['reason_categories'][0]
        self.assertEqual(c['kind'],'ordinary-input-read-without-presence')
        self.assertEqual(c['field'],'input.value')
        self.assertEqual(c['declared_presence'],'optional')
        self.assertEqual(c['source_pi'],'demo.pi')
        self.assertEqual(c['accepted_operations'],['review'])
        self.assertEqual(c['operation_presence_overrides'],[])
        self.assertEqual(r['compiler_verdict'],'unproven')

    def test_presence_only_optional_input_not_weakly_claimed_as_ordinary_value_read(self):
        m=fixture({'type':'string'})
        m['fields'][0].update(presence='optional',source_pi='demo.pi')
        m['fields'].append({'id':'input.marker','role':'input','presence':'optional',
                            'source_pi':'demo.pi','domain':{'type':'string'}})
        m['coverage_checks']['run']['guard_refs']=['input.value','input.marker']
        m['rules']=[{'id':'check','trigger':'run','when':{
            'op':'and','args':[
                {'op':'eq','args':[{'ref':'input.value'},{'literal':'ready'}]},
                {'op':'is-present','args':[{'ref':'input.marker'}]}]}}]
        r=audit(m)['local_coverage'][0]
        concerns=[c['field'] for c in r['reason_categories']
                  if c['kind']=='nonrequired-ordinary-guard-value-read']
        self.assertEqual(concerns,['input.value'])
        self.assertEqual(r['compiler_verdict'],'unproven')

    def test_no_local_tce_rule_separately_reported_without_assuming_no_delegation(self):
        m=fixture({'type':'boolean'})
        m['coverage_checks']['run']={'result':'uncovered','uncovered_count':1,
                                      'uncovered':[{}],'guard_refs':[]}
        m['rules']=[{'id':'other-rule','trigger':'other'}]
        out=audit(m)['local_coverage'][0]
        self.assertEqual(out['reason_categories'][0]['kind'],'finite-guard-gap')
        self.assertEqual(out['reason_categories'][1]['kind'],'trigger-without-local-tce')
        self.assertEqual(out['reason_categories'][1]['evidence_scope'],
                         'submitted-TestModel-only')
        self.assertEqual(out['uncovered_examples'],[{}])
        self.assertEqual(out['compiler_verdict'],'uncovered')

    def test_overlap_records_exact_contributing_rule_ids_and_one_witness(self):
        m=fixture({'type':'boolean'})
        m['coverage_checks']['run']={'result':'conflict','overlap_count':None,
             'overlaps':[{'state':{'input.value':True},'rules':['accept','fallback']},
                         {'state':{'input.value':False},'rules':['fallback','accept']}],
             'guard_refs':['input.value']}
        r=audit(m)['local_coverage'][0]
        self.assertEqual(r['overlapping_rule_groups'],[['accept','fallback']])
        self.assertEqual(r['overlap_example']['state'],{'input.value':True})
        self.assertIsNone(r['reason_categories'][0]['count'])
        self.assertEqual(r['formal_gate_status'] if 'formal_gate_status' in r
                         else audit(m)['formal_gate_status'],'not-run')

    def test_simple_real_arithmetic_retains_nonfinite_domain_diagnosis(self):
        m=fixture({'type':'real','min':0})
        m['fields'][0]['role']='observation'
        r=audit(m)['local_coverage'][0]
        self.assertEqual(r['reason_categories'][0]['kind'],'nonfinite-domain')
        self.assertEqual(r['reason_categories'][0]['domain_kind'],'real')
        self.assertEqual(r['compiler_verdict'],'unproven')

    def test_unknown_missing_ref_is_not_fabricated_into_declared_field(self):
        m=fixture({'type':'boolean'},
                  reason='ordinary expression reads missing/undefined field input.unknown')
        r=audit(m)['local_coverage'][0]
        self.assertEqual(r['reason_categories'][0]['kind'],'unbound-ordinary-value-read')
        self.assertEqual(r['reason_categories'][0]['field'],'input.unknown')
if __name__=='__main__':unittest.main()
