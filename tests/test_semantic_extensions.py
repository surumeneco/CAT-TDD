#!/usr/bin/env python3
"""Regression tests for structured domains and rule-inventory fail-closed behavior."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from catlib import semantic_types as types
from catlib import semantic_rules


class SemanticTypesTests(unittest.TestCase):
    def test_nullable_is_not_presence(self):
        value=types.parse('文字列またはnull')
        self.assertEqual(value['type'],'nullable')
        self.assertEqual(types.check_presence(value,'required'),('missing',False))
        self.assertEqual(types.check_presence(value,'optional'),('missing',True))
        self.assertEqual(types.check_presence(value,'required',None),('null',True))
        self.assertEqual(types.check_presence(value,'required',''),('value',True))

    def test_undefined_is_distinct(self):
        domain=types.parse('真偽')
        self.assertEqual(types.check_presence(domain,'undefined',types.UNDEFINED),('undefined',True))
        self.assertEqual(types.check_presence(domain,'required',types.UNDEFINED),('undefined',False))
        self.assertEqual(types.check_presence(domain,'absent',False),('value',False))
        self.assertEqual(types.check_presence(domain,'required',False),('value',True))
        self.assertEqual(types.check_presence(domain,'required',0),('out-of-domain',False))

    def test_recursive_record_and_sequence(self):
        d=types.parse('列<レコード<x:整数,z:整数>>')
        types.validate(d)
        self.assertTrue(types.contains(d,[{'x':2,'z':0},{'x':2,'z':0}]))
        self.assertFalse(types.contains(d,[{'x':2,'z':False}]))
        self.assertFalse(types.contains(d,[{'x':'2','z':0}]))

    def test_structured_set_deduplicates_by_value(self):
        d=types.parse('集合<レコード<x:整数,z:整数>>')
        self.assertFalse(types.contains(d,[{'x':0,'z':1},{'x':0,'z':1}]))
        self.assertTrue(types.contains(d,[{'x':0,'z':1},{'x':1,'z':0}]))
        self.assertEqual(len(types.set_add([{'x':0,'z':1}],{'x':0,'z':1})),1)
        self.assertEqual(types.set_remove([{'x':0,'z':1}],{'x':0,'z':1}),[])

    def test_bytes_have_octet_identity(self):
        d=types.parse('バイト列')
        self.assertTrue(types.contains(d,b'\x00\xff'))
        self.assertTrue(types.contains(d,[0,255]))
        self.assertFalse(types.contains(d,[-1]))
        self.assertFalse(types.contains(d,[256]))
        self.assertFalse(types.contains(d,'AP8='))

    def test_real_domain_is_finite(self):
        d=types.parse('実数[0..]')
        self.assertTrue(types.contains(d,0.125))
        self.assertTrue(types.contains(d,0))
        for v in (-0.1,float('nan'),float('inf'),float('-inf'),True):
            self.assertFalse(types.contains(d,v))

    def test_union_and_nullable_are_different(self):
        d=types.parse('Union<文字列,整数>')
        self.assertTrue(types.contains(d,1))
        self.assertFalse(types.contains(d,True))
        self.assertFalse(types.contains(d,None))

    def test_nominal_record_requires_shape_proof(self):
        d=types.parse('レコード<企業編集>')
        self.assertFalse(d['resolved'])
        types.validate(d)
        with self.assertRaises(types.DomainError):
            types.contains(d,{'anything':'x'})

    def test_untyped_record_does_not_infer_fields(self):
        d=types.parse('レコード<edition,username>')
        self.assertFalse(d['resolved'])
        with self.assertRaises(types.DomainError):
            types.contains(d,{'edition':'JE','username':'alice'})

    def test_union_known_witness_outweighs_unresolved_branch(self):
        nominal=types.parse('レコード<User>')
        domain={'type':'union','variants':[nominal,{'type':'string'}]}
        self.assertTrue(types.contains(domain,'accepted'))
        self.assertFalse(types.contains(domain,42))
        with self.assertRaisesRegex(types.DomainError,'unresolved record shape'):
            types.contains(domain,{'id':1})

    def test_recursive_collections_check_definite_rejection_before_unknown(self):
        nominal=types.parse('レコード<User>')
        domain={'type':'union','variants':[nominal,{'type':'string'}]}
        seq={'type':'sequence','element':domain}
        self.assertTrue(types.contains(seq,['ok']))
        self.assertFalse(types.contains(seq,[{'id':1},42]))
        with self.assertRaises(types.DomainError):
            types.contains(seq,[{'id':1},'ok'])
        set_domain={'type':'set','element':domain}
        self.assertFalse(types.contains(set_domain,[{'id':1},{'id':1}]))

    def test_recursive_record_preserves_definite_failure_with_unknown_field(self):
        unknown=types.parse('レコード<User>')
        record={'type':'record','resolved':True,'fields':[
            {'id':'user','domain':unknown,'presence':'required'},
            {'id':'enabled','domain':{'type':'boolean'},'presence':'required'}]}
        self.assertFalse(types.contains(record,{'user':{'id':1},'enabled':'not-a-boolean'}))
        with self.assertRaises(types.DomainError):
            types.contains(record,{'user':{'id':1},'enabled':True})

    def test_reject_invalid_type_schema(self):
        for d in ({'type':'real','min':float('nan')},
                  {'type':'sequence','element':{'type':'unknown'}},
                  {'type':'record','resolved':True,'fields':[{'id':'a','presence':'required','domain':{'type':'unknown'}}]}):
            with self.assertRaises(types.DomainError):
                types.validate(d)

    def test_structured_value_identity(self):
        self.assertFalse(types.same(True,1))
        self.assertFalse(types.same([1,2],[2,1]))
        self.assertTrue(types.same({'x':1,'y':2},{'y':2,'x':1}))


def _rule_file(directory, file_name, identifier, requirement):
    path=directory/file_name
    path.write_text("""---
kind: domain-spec
id: %s
process: demo.parent
status: candidate
semantic_contract: markdown-v2
decision_ref: ''
source_refs:
  - local-spec
refs: []
---

## 規則
| ID | 条件 | 要求 | 検証 |
| --- | --- | --- | --- |
| demo.rule | 対象 | %s | static contract |
"""%(identifier,requirement),encoding='utf-8')
    return path


class RuleInventoryTests(unittest.TestCase):
    def test_rule_ids_hash_and_unverified_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=_rule_file(Path(tmp),'a.md','demo.parent.rule','保持')
            docs=semantic_rules.load_many([path],'demo.parent.child',True)
            self.assertEqual(docs[0]['rules'][0]['id'],'demo.rule')
            self.assertEqual(docs[0]['rules'][0]['verification_status'],'unverified')
            self.assertEqual(len(docs[0]['sha256']),64)

    def test_candidate_requires_explicit_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=_rule_file(Path(tmp),'a.md','demo.parent.rule','保持')
            with self.assertRaises(semantic_rules.RuleError):
                semantic_rules.load(path,'demo.parent.child',False)

    def test_duplicate_rule_ids_with_conflicting_meanings_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            a=_rule_file(base,'a.md','demo.parent.one','A')
            b=_rule_file(base,'b.md','demo.parent.two','B')
            with self.assertRaises(semantic_rules.RuleError):
                semantic_rules.load_many([a,b],'demo.parent.child',True)

    def test_duplicate_identical_rule_ids_are_not_merged_across_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            a=_rule_file(base,'a.md','demo.parent.one','A')
            b=_rule_file(base,'b.md','demo.parent.two','A')
            with self.assertRaisesRegex(semantic_rules.RuleError,'duplicate normative rule ID'):
                semantic_rules.load_many([a,b],'demo.parent.child',True)

    def test_same_rule_id_with_different_verification_is_conflicting(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            a=_rule_file(base,'a.md','demo.parent.one','A')
            b=_rule_file(base,'b.md','demo.parent.two','A')
            b.write_text(b.read_text(encoding='utf-8').replace('static contract','external delivery contract'),encoding='utf-8')
            with self.assertRaisesRegex(semantic_rules.RuleError,'conflicting rule'):
                semantic_rules.load_many([a,b],'demo.parent.child',True)

    def test_confirmed_rule_cannot_be_imported_outside_process_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            path=_rule_file(base,'a.md','demo.parent.rule','A')
            text=path.read_text(encoding='utf-8').replace('status: candidate','status: confirmed')
            text=text.replace("decision_ref: ''","decision_ref: https://example.org/approval")
            path.write_text(text,encoding='utf-8')
            with self.assertRaisesRegex(semantic_rules.RuleError,'outside Process scope'):
                semantic_rules.load_many([path],'unrelated.process',False)

    def test_aggregate_scope_is_not_automatically_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=_rule_file(Path(tmp),'a.md','demo.parent.rule','保持')
            doc=semantic_rules.load(path,'another.process',True)
            self.assertFalse(doc['scope_verified'])


if __name__=='__main__':unittest.main()
