#!/usr/bin/env python3
"""Canonical recursive collection types must be checked by canonical IR semantics."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from cat_compile_v2 import in_domain
from catlib import semantic_types as types

class RecursiveCollectionRuntimeTests(unittest.TestCase):
    def test_valid_nested_collections_are_not_rejected_as_integer_only(self):
        for domain,value in (
            ('set<string>',['a','b']),
            ('sequence<boolean>',[True,False]),
            ('sequence<record<x:integer>>',[{'x':1}]),
            ('set<enum{A,B}>',['A']),
        ):
            with self.subTest(domain=domain):
                d=types.parse(domain)
                self.assertTrue(types.contains(d,value))
                self.assertTrue(in_domain(d,value))

    def test_wrong_element_types_and_duplicate_set_values_remain_rejected(self):
        for domain,value in (
            ('set<string>',[1]),
            ('set<string>',['a','a']),
            ('sequence<boolean>',[1]),
            ('sequence<record<x:integer>>',[{'x':True}]),
        ):
            with self.subTest(domain=domain):
                d=types.parse(domain)
                self.assertFalse(types.contains(d,value))
                self.assertFalse(in_domain(d,value))

if __name__=='__main__':unittest.main()
