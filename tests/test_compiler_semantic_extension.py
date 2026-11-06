"""Canonical CAT Compiler semantic extensions: concrete and fail-closed regressions."""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'
sys.path.insert(0,str(SCRIPTS))
from catlib import semantic_types as types
from catlib import verifier_contracts as v
import cat_compile_v2 as compiler
import cat_compose


class RecursiveDomainTests(unittest.TestCase):
    def test_nested_record_nullable_collection_and_distinct_values(self):
        typ=types.parse_domain('record<items:sequence<nullable<record<id:integer[0..],active:boolean>>>,tag?:string>')
        types.validate_domain(typ)
        self.assertTrue(types.in_domain(typ,{'items':[None,{'id':0,'active':False}]}))
        self.assertTrue(types.in_domain(typ,{'items':[]}))
        self.assertFalse(types.in_domain(typ,{'items':[{'id':-1,'active':False}]}))
        self.assertFalse(types.in_domain(typ,{'items':[{'id':0,'active':0}]}))
        self.assertFalse(types.in_domain(typ,{'items':[{'id':0,'active':None}]}))
        self.assertFalse(types.in_domain(typ,{'items':[], 'unknown':'extra'}))

    def test_undefined_absent_missing_and_null_are_not_collapsed(self):
        d=types.parse_domain('nullable<string>')
        self.assertTrue(types.check_presence('optional',types.MISSING,d))
        self.assertTrue(types.check_presence('required',None,d))
        self.assertFalse(types.check_presence('required',types.MISSING,d))
        self.assertFalse(types.check_presence('absent',None,d))
        self.assertTrue(types.check_presence('absent',types.MISSING,d))
        self.assertTrue(types.check_presence('undefined',types.UNDEFINED,d))
        self.assertFalse(types.check_presence('undefined',types.MISSING,d))
        self.assertFalse(types.check_presence('optional',types.UNDEFINED,d))

    def test_opaque_record_requires_schema(self):
        named=types.parse_domain('record<UploadPayload>')
        self.assertFalse(types.is_fully_interpreted(named))
        self.assertFalse(types.in_domain(named,{'id':'would be an unsupported guess'}))

    def test_bytes_bounds_and_set_duplicates(self):
        binary={'type':'bytes','min_length':2,'max_length':4}
        types.validate_domain(binary)
        self.assertTrue(types.in_domain(binary,b'\x00\x01'))
        self.assertFalse(types.in_domain(binary,'AAEC'))
        self.assertFalse(types.in_domain(binary,b'\x00'))
        rec=types.parse_domain('set<record<a:integer,b:boolean>>')
        self.assertFalse(types.in_domain(rec,[{'a':0,'b':False},{'b':False,'a':0}]))
        self.assertTrue(types.in_domain(rec,[{'a':0,'b':False},{'a':1,'b':False}]))

    def test_real_is_nonboolean_finite_and_bounded(self):
        d=types.parse_domain('real[0..]')
        self.assertTrue(types.in_domain(d,0.0));self.assertTrue(types.in_domain(d,2.5))
        self.assertFalse(types.in_domain(d,-1.0))
        self.assertFalse(types.in_domain(d,float('inf')))
        self.assertFalse(types.in_domain(d,float('nan')))
        self.assertFalse(types.in_domain(d,False))

    def test_union_validates_tagless_values_and_type_identity(self):
        d=types.parse_domain('union<string,integer>')
        self.assertTrue(types.in_domain(d,0));self.assertTrue(types.in_domain(d,'0'))
        self.assertFalse(types.in_domain(d,False))
        self.assertFalse(types.same_value(False,0))

    def test_unsupported_domain_fails_closed(self):
        with self.assertRaises(types.DomainError):types.parse_domain('MagicUnknownType')
        with self.assertRaises(types.DomainError):types.validate_domain({'type':'object'})


class VectorPresenceTests(unittest.TestCase):
    @staticmethod
    def model():
        return {'schema':compiler.M,'process':'p','status':'draft',
                'fields':[{'id':'x','role':'input','presence':'optional','domain':{'type':'boolean'}},
                          {'id':'u','role':'input','presence':'undefined','domain':{'type':'string'}},
                          {'id':'data','role':'input','presence':'required','domain':{'type':'bytes','min_length':1}},
                          {'id':'s','role':'state','domain':{'type':'boolean'}},
                          {'id':'out','role':'output','domain':{'type':'boolean'}}],
                'triggers':[{'id':'go','origin':'test'}],'definitions':[],'pi_constraints':[],
                'rules':[{'id':'r','trigger':'go','when':{'literal':True},
                          'allowed':[{'write':[{'target':'out','expr':{'literal':False}}],
                                      'unchanged':['s'],'absent_outputs':[]}]}]}

    def test_optional_missing_and_explicit_undefined_without_coercion(self):
        vec={'schema':compiler.V,'process':'p','cases':[
            {'id':'case1','trigger':'go','input':{'u':{'$cat':'undefined'},'data':{'$cat':'bytes','base64':'AAE='}},'state':{'s':False}}]}
        result=compiler.expand_cases(self.model(),vec)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['allowed'][0]['output'],{'out':False})
        self.assertNotIn('x',result[0]['input'])

    def test_false_zero_missing_and_invalid_byte_must_not_conflate(self):
        vec={'schema':compiler.V,'process':'p','cases':[
            {'id':'case2','trigger':'go','input':{'x':False,'u':{'$cat':'undefined'},'data':{'$cat':'bytes','base64':'AAE='}},'state':{'s':False}}]}
        self.assertEqual(compiler.expand_cases(self.model(),vec)[0]['input']['x'],False)
        vec['cases'][0]['input']['data']='AAE='
        with self.assertRaises(compiler.Blocked):compiler.expand_cases(self.model(),vec)
        vec['cases'][0]['input']['data']={'$cat':'bytes','base64':'AAE='}
        vec['cases'][0]['input']['u']=None
        with self.assertRaises(compiler.Blocked):compiler.expand_cases(self.model(),vec)

    def test_nonfinite_selector_rejects_optional_without_implicit_required(self):
        closed=self.model();closed['status']='confirmed'
        closed['fields']=[f for f in closed['fields'] if f['id']!='data']
        with self.assertRaisesRegex(compiler.Blocked,'optional/absent/undefined'):
            compiler.selection_vectors(closed)


class VerifierContractTests(unittest.TestCase):
    def test_an_authored_pass_is_never_an_executed_pass(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'registry.json'
            data={'schema':'cat-verifier-registry/v1','entries':[
                {'rule_id':'notification.rule','capability':'discord-delivery',
                 'requirement':'delivery must succeed','execution_status':'passed'}]}
            path.write_text(json.dumps(data))
            plan=v.inspect_contracts(path,{'notification.rule'})
            self.assertEqual(plan['contracts'][0]['status'],'not-run')
            self.assertEqual(plan['status'],'inconclusive')

    def test_dom_cannot_prove_discord_delivery(self):
        contract={'rule_id':'notice.sent','capability':'discord-delivery'}
        evidence={'rule_id':'notice.sent','capability':'dom','source_sha256':'a'*64,'fixture_sha256':'b'*64,
                  'verifier_id':'browser','result':'passed','assertions':[{'expected':1,'observed':1}],
                  'external_attestation':'some-browser'}
        with self.assertRaisesRegex(v.ContractError,'ownership'):
            v.verify_evidence(contract,evidence)
        evidence['capability']='discord-delivery'
        evidence['subject_kind']='dom'
        with self.assertRaisesRegex(v.ContractError,'external effect'):
            v.verify_evidence(contract,evidence)

    def test_unattested_external_result_remains_inconclusive(self):
        contract={'rule_id':'a','capability':'discord-delivery'}
        evidence={'rule_id':'a','capability':'discord-delivery','source_sha256':'a'*64,
                  'fixture_sha256':'b'*64,'verifier_id':'bot','result':'passed','subject_kind':'discord-delivery',
                  'assertions':[{'expected':'sent','observed':'sent'}]}
        self.assertEqual(v.verify_evidence(contract,evidence)['status'],'inconclusive')


class CompositionTests(unittest.TestCase):
    @staticmethod
    def make(path,process,peer,direction):
        path.write_text(json.dumps({'schema':'cat-test-model/v2','process':process,'status':'draft',
          'coverage_requirement':'partial','pi_boundary':{'peer':peer,'direction':direction},
          'source_semantic_map':{'pi':{'artifact':process+'.pi'}}}))

    def test_missing_peer_does_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a.json';b=Path(d)/'b.json'
            self.make(a,'a','c','send');self.make(b,'b','a','receive')
            result=cat_compose.compose([a,b])
            self.assertEqual(result['status'],'inconclusive')
            self.assertGreater(len(result['unresolved']),0)

    def test_incompatible_direction_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a.json';b=Path(d)/'b.json'
            self.make(a,'a','b','send');self.make(b,'b','a','send')
            result=cat_compose.compose([a,b])
            self.assertEqual(result['status'],'blocked')
            self.assertGreater(len(result['conflicts']),0)


if __name__=='__main__':unittest.main()
