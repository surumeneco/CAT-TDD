"""W06: closed-record and union subset proofs in typed Process composition."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_process_composition import _type_subset
from catlib.semantic_types import parse,finite_values


class StructuralSubsetTests(unittest.TestCase):
    def test_same_record_shape_proves_inclusion_ignoring_source_provenance(self):
        a={'type':'record','name':'User','resolved':True,'fields':[
            {'id':'name','domain':parse('string'),'presence':'required'},
            {'id':'age','domain':parse('integer[0..120]'),'presence':'required'}],
            'definition_source':'project.a','definition_sha256':'a'*64}
        b={'type':'record','name':'Account','resolved':True,'fields':[
            {'id':'name','domain':parse('string'),'presence':'required'},
            {'id':'age','domain':parse('integer[0..150]'),'presence':'required'}],
            'definition_source':'project.b','definition_sha256':'b'*64}
        self.assertIs(_type_subset(a,b),True)
        self.assertIs(_type_subset(b,a),False)

    def test_closed_record_extra_field_is_not_subset(self):
        source=parse('record<x:boolean,y:boolean>')
        target=parse('record<x:boolean>')
        self.assertIs(_type_subset(source,target),False)
        self.assertIs(_type_subset(target,source),False)

    def test_unresolved_and_optional_records_stay_unproved(self):
        unknown=parse('record<User>')
        resolved=parse('record<x:boolean>')
        self.assertIsNone(_type_subset(unknown,resolved))
        optional=parse('record<x:boolean>')
        optional['fields'][0]['presence']='optional'
        self.assertIsNone(_type_subset(optional,resolved))

    def test_union_members_can_jointly_cover_finite_source(self):
        self.assertIs(_type_subset(parse('integer[0..2]'),
                                   parse('Union<enum{0},enum{1},enum{2}>')),True)
        self.assertIs(_type_subset(parse('integer[0..3]'),
                                   parse('Union<enum{0},enum{1},enum{2}>')),False)
        self.assertIs(_type_subset(parse('enum{true,1}'),
                                   parse('Union<enum{true},enum{1}>')),True)
        self.assertIsNone(_type_subset(parse('integer'),
                                       parse('Union<enum{0},enum{1}>')))


if __name__=='__main__':unittest.main()
