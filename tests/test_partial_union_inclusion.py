#!/usr/bin/env python3
"""A known union arm is admissible without resolving unrelated arms.

This is a type-inclusion regression, not a process-closure or external effect
proof. Unresolved aliases and changed definition hashes remain unproved.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from catlib import semantic_subtyping as subtyping


def resolved(name, domain, fingerprint='a'*64):
    return {'type':'reference','name':name,'resolved':True,'of':domain,
            'definition_source':'example.domain-spec','definition_sha256':fingerprint}


class PartialUnionInclusionTests(unittest.TestCase):
    def setUp(self):
        self.notice=resolved('Notice',{'type':'record','resolved':True,
            'fields':[{'id':'event_id','domain':{'type':'string'},'presence':'required'}]})
        self.unresolved={'type':'reference','name':'DailyNotice','resolved':False}
        self.target={'type':'union','variants':[self.notice,self.unresolved]}

    def test_known_resolved_arm_in_partially_unresolved_union_is_proved(self):
        self.assertIs(subtyping.subset(self.notice,self.target),True)

    def test_unresolved_alias_remains_unproved(self):
        self.assertIsNone(subtyping.subset(self.unresolved,self.target))

    def test_unrelated_resolved_alias_is_not_approved(self):
        other=resolved('Other',{'type':'string'})
        self.assertIsNot(subtyping.subset(other,self.target),True)

    def test_same_name_but_different_source_fingerprint_not_equal(self):
        changed=resolved('Notice',self.notice['of'],'b'*64)
        self.assertIsNot(subtyping.subset(changed,self.target),True)

    def test_strict_enum_subtype_of_known_arm_with_unresolved_sibling(self):
        target={'type':'union','variants':[{'type':'integer'},self.unresolved]}
        self.assertIs(subtyping.subset({'type':'enum','values':[1,2]},target),True)

    def test_bounded_integer_subtype_of_known_arm_with_unresolved_sibling(self):
        target={'type':'union','variants':[{'type':'integer'},self.unresolved]}
        self.assertIs(subtyping.subset({'type':'integer','min':0,'max':2},target),True)

    def test_structural_record_subtype_of_known_arm_with_unresolved_sibling(self):
        source={'type':'record','resolved':True,
                'fields':[{'id':'x','domain':{'type':'integer','min':0,'max':2},'presence':'required'}]}
        broad={'type':'record','resolved':True,
               'fields':[{'id':'x','domain':{'type':'integer'},'presence':'required'}]}
        self.assertIs(subtyping.subset(source,{'type':'union','variants':[broad,self.unresolved]}),True)

    def test_nullable_nonfinite_subtype_of_known_json_arm_with_unresolved_sibling(self):
        target={'type':'union','variants':[{'type':'json','root':'value'},self.unresolved]}
        self.assertIs(subtyping.subset({'type':'nullable','of':{'type':'string'}},target),True)

    def test_incompatible_known_arm_does_not_overrule_unresolved_sibling(self):
        target={'type':'union','variants':[{'type':'integer'},self.unresolved]}
        self.assertIsNone(subtyping.subset({'type':'enum','values':[True]},target))

    def test_nominal_provenance_never_widened_by_partial_union(self):
        source=resolved('Notice',self.notice['of'],'b'*64)
        target={'type':'union','variants':[self.notice,self.unresolved]}
        self.assertIsNone(subtyping.subset(source,target))

    def test_malformed_sibling_cannot_certify_partial_union(self):
        target={'type':'union','variants':[{'type':'integer'},
                                          {'type':'integer','min':3,'max':2}]}
        self.assertIsNone(subtyping.subset({'type':'enum','values':[1]},target))

    def test_exact_scalar_branch_stays_well_typed(self):
        d={'type':'union','variants':[{'type':'boolean'},self.unresolved]}
        self.assertIs(subtyping.subset({'type':'boolean'},d),True)
        self.assertIsNot(subtyping.subset({'type':'integer'},d),True)

if __name__=='__main__':
    unittest.main()
