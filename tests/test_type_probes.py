#!/usr/bin/env python3
"""Type probe diagnostics must not be substituted for normative TCE vectors."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_type_probes as probes

class TypeProbeTests(unittest.TestCase):
    def document(self,fields):
        return {'schema':'cat-test-model/v2','process':'example.demo','fields':fields,
                'rule_obligations':[{'id':'example.rule'}]}

    def test_missing_null_false_and_zero_remain_distinct(self):
        model=self.document([{'id':'input.flag','role':'input','presence':'optional','domain':{'type':'boolean'}}])
        d=probes.diagnostics(model,json.dumps(model).encode())
        f=d['fields'][0]
        self.assertEqual(f['cases'][0]['kind'],'missing')
        self.assertTrue(f['cases'][0]['type_accepts'])
        self.assertFalse(f['cases'][1]['type_accepts'])
        self.assertTrue(next(x for x in f['cases'] if x['kind']=='boolean-false')['type_accepts'])
        self.assertFalse(next(x for x in f['cases'] if x['kind']=='numeric-zero')['type_accepts'])
        self.assertEqual(d['conformance_status'],'not-run')

    def test_unresolved_nested_record_marks_inconclusive(self):
        model=self.document([{'id':'input.user','role':'input','presence':'required',
              'domain':{'type':'record','name':'User','resolved':False}}])
        d=probes.diagnostics(model,json.dumps(model).encode())
        self.assertIn('input.user',d['unresolved_fields'])
        self.assertEqual(d['status'],'candidate')

    def test_unresolved_record_rejects_nonrecords_but_keeps_shape_unknown(self):
        from catlib import semantic_types as types
        d={'type':'record','name':'User','resolved':False}
        self.assertFalse(types.contains(d,None))
        self.assertFalse(types.contains(d,42))
        self.assertFalse(types.contains(d,[]))
        with self.assertRaisesRegex(types.DomainError,'unresolved record shape'):
            types.contains(d,{'id':1})
        self.assertTrue(types.contains({'type':'nullable','of':d},None))

    def test_sequence_duplicates_differ_from_set_duplicates(self):
        item={'type':'integer'}
        model=self.document([
          {'id':'input.collection','role':'input','presence':'required','domain':{'type':'set','element':item}},
          {'id':'input.ordered','role':'input','presence':'required','domain':{'type':'sequence','element':item}},
        ])
        result=probes.diagnostics(model,json.dumps(model).encode())
        by_id={x['field']:x for x in result['fields']}
        a=next(c for c in by_id['input.collection']['cases'] if c['kind']=='duplicate-set-element')
        b=next(c for c in by_id['input.ordered']['cases'] if c['kind']=='duplicate-sequence-element')
        self.assertFalse(a['type_accepts'])
        self.assertTrue(b['type_accepts'])

    def test_byte_identity_is_octet_tag_not_string(self):
        model=self.document([{'id':'input.file','role':'input','presence':'required','domain':{'type':'bytes'}}])
        d=probes.diagnostics(model,json.dumps(model).encode())
        raw=next(x for x in d['fields'][0]['cases'] if x['kind']=='bytes-octets')
        self.assertEqual(raw['value']['$cat_type'],'bytes')
        self.assertTrue(raw['type_accepts'])
        invalid=next(x for x in d['fields'][0]['cases'] if x['kind']=='invalid-octet')
        self.assertFalse(invalid['type_accepts'])


# Probeability is not a normative Conformance or implementation claim.
class NominalResolvedDomainTests(unittest.TestCase):
    def test_resolved_reference_and_null_are_probeable(self):
        domains=[
            {'type':'reference','name':'MaybeInt','resolved':True,
             'of':{'type':'nullable','of':{'type':'integer','min':1,'max':1}}},
            {'type':'null'},
            {'type':'union','variants':[{'type':'null'},{'type':'boolean'}]},
        ]
        for domain in domains:
            with self.subTest(domain=domain):
                model={'process':'example','fields':[{'id':'in.a','role':'input',
                       'presence':'required','domain':domain}]}
                result=probes.diagnostics(model,json.dumps(model).encode())
                self.assertEqual(result['unresolved_fields'],[])
                self.assertTrue(next(x for x in result['fields'][0]['cases']
                         if x['kind']=='representative-value')['type_accepts'])

if __name__=='__main__':unittest.main()
