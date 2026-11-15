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

    def test_exact_scalar_branch_stays_well_typed(self):
        d={'type':'union','variants':[{'type':'boolean'},self.unresolved]}
        self.assertIs(subtyping.subset({'type':'boolean'},d),True)
        self.assertIsNot(subtyping.subset({'type':'integer'},d),True)

if __name__=='__main__':
    unittest.main()
