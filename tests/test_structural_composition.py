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
        self.assertIs(_type_subset(optional,resolved),False)
        self.assertIs(_type_subset(optional,optional),True)

    def test_presence_compatible_record_fields_are_proved(self):
        required=parse('record<name:string,flag[required]:boolean>')
        optional=parse('record<name:string,flag[optional]:boolean>')
        missing_only=parse('record<name:string,flag[absent]:boolean>')
        undefined_only=parse('record<name:string,flag[undefined]:boolean>')
        self.assertIs(_type_subset(required,optional),True)
        self.assertIs(_type_subset(optional,required),False)
        self.assertIs(_type_subset(missing_only,optional),True)
        self.assertIs(_type_subset(optional,missing_only),False)
        self.assertIs(_type_subset(undefined_only,undefined_only),True)
        self.assertIs(_type_subset(undefined_only,optional),False)
        self.assertIs(_type_subset(optional,undefined_only),False)

    def test_closed_record_omitted_fields_respect_absent_presence(self):
        source=parse('record<name:string>')
        target_optional=parse('record<name:string,age[optional]:integer>')
        target_absent=parse('record<name:string,age[absent]:integer>')
        target_required=parse('record<name:string,age:integer>')
        target_undefined=parse('record<name:string,age[undefined]:integer>')
        source_absent=parse('record<name:string,age[absent]:integer>')
        self.assertIs(_type_subset(source,target_optional),True)
        self.assertIs(_type_subset(source,target_absent),True)
        self.assertIs(_type_subset(source,target_required),False)
        self.assertIs(_type_subset(source,target_undefined),False)
        self.assertIs(_type_subset(source_absent,source),True)

    def test_nested_record_presence_and_value_domain_must_both_include(self):
        narrow=parse('record<owner:record<id:string,level[optional]:integer[0..2]>>')
        broad=parse('record<owner:record<id:string,level[optional]:integer[0..5]>>')
        strict=parse('record<owner:record<id:string,level:integer[0..5]>>')
        self.assertIs(_type_subset(narrow,broad),True)
        self.assertIs(_type_subset(broad,narrow),False)
        self.assertIs(_type_subset(narrow,strict),False)
        unknown=parse('record<owner:record<id:string,level[optional]:string<safe-signed-integer>>>')
        # Any string is not proved to be a safe signed integer string.
        self.assertIsNone(_type_subset(
            parse('record<owner:record<id:string,level[optional]:string>>'),unknown))

    def test_closed_records_are_order_independent(self):
        a=parse('record<x[optional]:boolean,y[absent]:integer>')
        b=parse('record<y[absent]:integer,x[optional]:boolean>')
        self.assertIs(_type_subset(a,b),True)

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
