"""Candidate compiler extension: meaningful domain, codec and integration probes."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from fractions import Fraction
import json
import random
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system/scripts'))
from catlib import semantic_types as types, semantic_named_types as named, semantic_subtyping as sub
from catlib import semantic_json_instant as codec
import cat_compile_v2 as compiler
import cat_model_conformance as conformance
from test_cat_compile_readable import write_v2
from test_named_type_resolution import spec,add_named_field


class JsonInstantTests(unittest.TestCase):
    def test_upstream_core_confirmed_source_and_unverified_rule_boundary(self):
        from catlib import semantic_rules
        from catlib.markdown import parse_frontmatter
        path=ROOT/'Docs/Constraints/cat.compiler.json-instant.domain-spec.md'
        decision=ROOT/'Docs/Decisions/CAT31-json-instant-approval-20261118.md'
        self.assertTrue(decision.is_file())
        front=parse_frontmatter(path)
        self.assertEqual(front['status'],'confirmed')
        self.assertEqual(front['decision_ref'],decision.relative_to(ROOT).as_posix())
        self.assertIn('fe6d7ff63928f5b9a243a2e737b6e6b569f7b7d3ecdd83522f57c85baa7d44fe',
                      decision.read_text(encoding='utf-8'))
        source=semantic_rules.load(path,'cat.compiler',allow_draft=False)
        self.assertEqual(source['id'],'cat.compiler.json-instant')
        self.assertEqual(source['kind'],'domain-spec')
        self.assertEqual(source['status'],'confirmed')
        self.assertTrue(source['scope_verified'])
        self.assertEqual({rule['id'] for rule in source['rules']},{
            'JT.domains','JT.json-tree','JT.json-equality','JT.instant',
            'JT.typed-comparison','JT.codec','JT.inclusion','JT.source-model',
            'JT.fail-closed','JT.authority'})
        self.assertTrue(all(rule['verification_status']=='unverified'
                            for rule in source['rules']))
        with tempfile.TemporaryDirectory() as td:
            fake=Path(td)/'no-approval.md'
            text=path.read_text(encoding='utf-8')
            self.assertIn('status: confirmed',text)
            fake.write_text(text.replace('decision_ref: '+front['decision_ref'],
                                         "decision_ref: ''",1),encoding='utf-8')
            with self.assertRaisesRegex(semantic_rules.RuleError,'missing decision_ref'):
                semantic_rules.load(fake,'cat.compiler',allow_draft=False)
            fake.write_text(text.replace('status: confirmed','status: candidate',1),
                            encoding='utf-8')
            with self.assertRaisesRegex(semantic_rules.RuleError,'unconfirmed normative input'):
                semantic_rules.load(fake,'cat.compiler',allow_draft=False)

    def test_parse_validate_format_bilingual(self):
        for names,domain in [(['json','JSON値'],{'type':'json','root':'value'}),(['json-object','JSONオブジェクト'],{'type':'json','root':'object'}),(['instant','瞬間値'],{'type':'instant'})]:
            for name in names:self.assertEqual(types.validate(types.parse(name)),domain)
            for lang in ('en','ja'):self.assertEqual(types.parse(compiler.format_domain(domain,lang)),domain)

    def test_ambiguous_bare_names_do_not_create_registry_entries(self):
        for text in ('JSON','時点'):
            with self.assertRaises(types.DomainError):types.parse(text)
        self.assertFalse(named.resolve(types.parse('ref<JSON>'),{})['resolved'])

    def test_extra_or_invalid_ir_keys_rejected(self):
        for d in ({'type':'json'},{'type':'json','root':'array'},{'type':'json','root':'value','maxDepth':5},{'type':'instant','precision':3}):
            with self.assertRaises(types.DomainError):types.validate(d)

    def test_json_object_and_value_roots(self):
        general=types.parse('json');obj=types.parse('json-object')
        for value in [None,False,0,Decimal('1.0'),'text',[],{}, {'key':[None,True,Decimal('1e400')]}]:
            self.assertTrue(types.contains(general,value))
            self.assertEqual(types.contains(obj,value),type(value) is dict)

    def test_json_rejects_cycles_undefined_nonfinite_nonstring_keys(self):
        cycle=[];cycle.append(cycle)
        for value in (cycle,types.UNDEFINED,{1:'no'},float('inf'),float('nan'),Decimal('NaN'),{'x':b'bytes'},(1,)):
            self.assertFalse(types.contains(types.parse('json'),value))

    def test_deep_tree_without_fixed_depth_and_shared_children(self):
        value={'n':Decimal('1.00')}
        for _ in range(2000):value=[value]
        encoded=codec.json_dumps_exact(value)
        self.assertTrue(codec.json_contains(value))
        self.assertTrue(codec.json_equal(value,codec.json_loads_exact(encoded)))
        shared={'x':[1]};self.assertTrue(codec.json_contains([shared,shared]))

    def test_jsonb_equality_and_presence(self):
        d=types.parse('json')
        for a,b in [(1,Decimal('1.00')),(0,-0.0),({'a':1,'b':2},{'b':2,'a':1.0})]:
            self.assertTrue(types.same_in_domain(d,a,b))
        for a,b in [(True,1),([1,2],[2,1]),({'a':None},{}),(None,{})]:
            self.assertFalse(types.same_in_domain(d,a,b))
        self.assertFalse(types.same(1,1.0))
        self.assertEqual(types.check_presence(types.parse('json-object'),'optional'),('missing',True))
        self.assertEqual(types.check_presence(types.parse('json-object'),'optional',None),('null',False))

    def test_exact_codec_retains_large_numeric_tokens_and_unicode(self):
        text='{"n":9007199254740993,"small":1.234567890123456789e-100,"text":"😀"}'
        value=codec.json_loads_exact(text)
        self.assertEqual(value['n'],Decimal('9007199254740993'))
        self.assertEqual(value['small'],Decimal('1.234567890123456789e-100'))
        self.assertTrue(codec.json_equal(value,codec.json_loads_exact(codec.json_dumps_exact(value))))
        self.assertFalse(codec.json_equal(value,{'n':9007199254740992,'small':value['small'],'text':'😀'}))

    def test_large_integer_codec_has_no_python_decimal_digit_limit(self):
        n=10**5000+3
        self.assertTrue(codec.json_equal(n,codec.json_loads_exact(codec.json_dumps_exact(n))))

    def test_json_grammar_rejects_trailing_commas_and_invalid_tokens(self):
        for text in ('','[1,]','{"x":1,}','[1 2]','{"x" 1}','01','1x','NaN','Infinity','[','{"x":','[undefined]','truefalse'):
            with self.assertRaises(codec.BindingError,msg=text):codec.json_loads_exact(text)
        self.assertTrue(codec.json_equal(codec.json_loads_exact('{"a":1,"a":2}'),{'a':2}))

    def test_json_codec_escapes_and_nested_empty_containers(self):
        value={'a':[],'b':{},'q':'a"b\\c\n\t','c':[{},[],False,None]}
        self.assertTrue(codec.json_equal(value,codec.json_loads_exact(codec.json_dumps_exact(value))))

    def test_iterative_codec_differential_against_standard_json_grammar(self):
        randomizer=random.Random(314159)
        scalars=[None,False,True,0,-1,1.25,10**30,'','quote"slash\\\n','😀']
        def tree(depth):
            if depth==0 or randomizer.randrange(3)==0:return randomizer.choice(scalars)
            if randomizer.randrange(2):return [tree(depth-1) for _ in range(randomizer.randrange(4))]
            return {'key'+str(i):tree(depth-1) for i in range(randomizer.randrange(4))}
        for _ in range(250):
            value=tree(5)
            text=json.dumps(value,ensure_ascii=True,allow_nan=False)
            for candidate in (text,text[:-1],text+'x',' '+text+' ', '['+text+']'):
                try:reference=json.loads(candidate,parse_int=Decimal,parse_float=Decimal)
                except (ValueError,OverflowError):
                    with self.assertRaises(codec.BindingError):codec.json_loads_exact(candidate)
                else:self.assertTrue(codec.json_equal(reference,codec.json_loads_exact(candidate)))
            self.assertTrue(codec.json_equal(value,codec.json_loads_exact(codec.json_dumps_exact(value))))

    def test_instant_offset_equality_and_microsecond_order(self):
        d=types.parse('instant')
        a=codec.decode_offset_datetime('2026-11-16T00:00:00.000001Z')
        b=codec.decode_offset_datetime('2026-11-16T09:00:00.000001+09:00')
        c=codec.decode_offset_datetime('2026-11-16T00:00:00.000002Z')
        self.assertTrue(types.same_in_domain(d,a,b))
        self.assertEqual(types.compare_in_domain(d,a,c),-1)
        self.assertEqual(types.compare_in_domain(d,c,a),1)
        self.assertFalse(types.same_in_domain(d,a,c))

    def test_instant_subnanosecond_and_transport(self):
        a=codec.decode_offset_datetime('1969-12-31T23:59:59.999999999999999999Z')
        self.assertEqual(a.seconds,Fraction(-1,10**18))
        self.assertEqual(codec.decode_instant_transport(codec.encode_instant_transport(a)),a)
        huge=codec.InstantValue(Fraction(10**5000+1,3))
        self.assertEqual(codec.decode_instant_transport(codec.encode_instant_transport(huge)),huge)

    def test_instant_raw_strings_naive_and_unknown_offsets_not_coerced(self):
        self.assertFalse(types.contains(types.parse('instant'),'2026-11-16T00:00:00Z'))
        for text in ('2026-11-16T00:00:00','2026-11-16T00:00:00-00:00','2026-02-30T00:00:00Z','2026-11-16T24:00:00Z','2026-11-16T00:00:60Z','2026-11-16T00:00:00+24:00'):
            with self.assertRaises(codec.BindingError):codec.decode_offset_datetime(text)
        with self.assertRaises(codec.BindingError):codec.decode_aware_datetime(datetime(2026,11,16))
        with self.assertRaises(codec.BindingError):codec.InstantValue(1.0)

    def test_offset_datetime_codec_rejects_non_ascii_digits(self):
        # The explicit offset codec uses a fixed ISO-style lexical grammar.
        # Python regex \d and int() otherwise accept many Unicode digits.
        for text in (
            '２０２６-１１-１６T００:００:００Z',
            '٢٠٢٦-١١-١٦T٠٠:٠٠:٠٠Z',
            '2026-11-16T00:00:00.١Z',
            '2026-11-16T00:00:00+０９:００',
        ):
            with self.subTest(text=text):
                with self.assertRaises(codec.BindingError):
                    codec.decode_offset_datetime(text)

    def test_aware_datetime_codec_uses_actual_offset(self):
        value=datetime(2026,11,16,9,0,0,123456,tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(codec.decode_aware_datetime(value),codec.decode_offset_datetime('2026-11-16T00:00:00.123456Z'))

    def test_offset_codec_differential_against_aware_datetime(self):
        epoch=datetime(1970,1,1,tzinfo=timezone.utc)
        for year in (1900,1969,1970,2000,2026):
            for offset in (-720,-330,0,330,840):
                value=datetime(year,3,1,0,0,0,123456,tzinfo=timezone(timedelta(minutes=offset)))
                delta=value.astimezone(timezone.utc)-epoch
                reference=Fraction(delta.days*86400+delta.seconds)+Fraction(delta.microseconds,1000000)
                self.assertEqual(codec.decode_offset_datetime(value.isoformat()).seconds,reference)
                self.assertEqual(codec.decode_aware_datetime(value).seconds,reference)

    def test_instant_transport_is_strict_and_schema_bound(self):
        for value in ({'$cat_instant':{'n':'0','d':'0'}},{'$cat_instant':{'n':'00','d':'1'}},{'$cat_instant':{'n':0,'d':'1'}},{'$cat_instant':{'n':'0','d':'1'},'other':True}):
            with self.assertRaises(codec.BindingError):codec.decode_instant_transport(value)
        self.assertTrue(codec.json_contains({'$cat_instant':{'n':'0','d':'1'}}))
        self.assertFalse(types.contains(types.parse('instant'),{'$cat_instant':{'n':'0','d':'1'}}))

    def test_typed_record_set_and_optional_presence(self):
        record=types.parse('record<data:json-object,note[optional]:nullable<string>>')
        self.assertTrue(types.same_in_domain(record,{'data':{'n':1}},{'data':{'n':1.0}}))
        self.assertFalse(types.same_in_domain(record,{'data':{}},{'data':{},'note':None}))
        collection=types.parse('set<json-object>')
        self.assertFalse(types.contains(collection,[{'n':1},{'n':1.0}]))
        self.assertTrue(types.same_in_domain(collection,[{'n':1},{'n':2}],[{'n':2.0},{'n':1.0}]))
        self.assertEqual(len(types.set_add_in_domain(types.parse('json-object'),[{'n':1}],{'n':1.0})),1)
        self.assertEqual(types.set_remove_in_domain(types.parse('json-object'),[{'n':1}],{'n':1.0}),[])

    def test_typed_set_helpers_reject_invalid_existing_sets(self):
        d=types.parse('json-object')
        duplicate=[{'n':1},{'n':1.0}]
        self.assertFalse(types.contains(types.parse('set<json-object>'),duplicate))
        for operation in (types.set_add_in_domain,types.set_remove_in_domain):
            with self.assertRaises(types.DomainError):operation(d,duplicate,{'n':9})
        self.assertTrue(types.contains(types.parse('set<json-object>'),
                                       types.set_add_in_domain(d,[{'n':1}],{'n':2})))

    def test_union_ambiguous_equality_is_not_guessed(self):
        with self.assertRaises(types.DomainError):types.same_in_domain(types.parse('union<real,json>'),1,1.0)

    def test_new_domains_do_not_fabricate_finite_coverage(self):
        for d in ('json','json-object','instant'):self.assertIsNone(types.finite_values(types.parse(d)))

    def test_subtyping_is_conservative(self):
        value=types.parse('json');obj=types.parse('json-object');instant=types.parse('instant')
        self.assertTrue(sub.subset(obj,value));self.assertFalse(sub.subset(value,obj))
        self.assertTrue(sub.subset(instant,instant));self.assertFalse(sub.subset(instant,types.parse('string')))
        self.assertTrue(sub.subset(types.parse('record<a:integer,b[optional]:json>'),obj))
        self.assertFalse(sub.subset(types.parse('record<a[undefined]:integer>'),obj))
        self.assertFalse(sub.subset(value,types.parse('record<a:integer>')))
        self.assertTrue(sub.subset(types.parse('sequence<json>'),value))

    def test_legacy_equality_expression_cannot_self_certify_new_semantics(self):
        for domain in ('json','instant','record<data:json-object>'):
            fields={'input.a':{'id':'input.a','role':'input','domain':types.parse(domain)}}
            with self.assertRaisesRegex(compiler.Blocked,'explicit domain binding'):
                compiler.inspect_expr({'op':'eq','args':[{'ref':'input.a'},{'ref':'input.a'}]},fields,{})

    def test_existing_renderer_cannot_silently_encode_new_carriers(self):
        with self.assertRaisesRegex(compiler.Blocked,'explicit JSON/instant binding'):
            compiler.emit_vitest({'fields':[{'domain':types.parse('instant')}]},None,None)

    def test_explicit_owner_binding_preserves_nested_roles_json_and_instants(self):
        d=types.parse('record<actor:string,body:json-object,at:instant,note[optional]:nullable<string>>')
        value={'actor':'actor-A','body':codec.json_loads_exact('{"n":9007199254740993}'),'at':'2026-11-16T09:00:00.000001+09:00'}
        with self.assertRaises(types.DomainError):types.bind_in_domain(d,value)
        bound=types.bind_in_domain(d,value,instant_decoder=codec.decode_offset_datetime)
        self.assertEqual(bound['actor'],'actor-A')
        self.assertEqual(bound['body']['n'],Decimal('9007199254740993'))
        self.assertEqual(bound['at'],codec.decode_offset_datetime('2026-11-16T00:00:00.000001Z'))
        self.assertNotIn('note',bound)
        with self.assertRaises(types.DomainError):types.bind_in_domain(d,{**value,'note':False},instant_decoder=codec.decode_offset_datetime)

    def test_named_roots_model_and_independent_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,pi,t=write_v2(root,False)
            add_named_field(pi,'ref<Payload>')
            ds=spec(root,'| JSON | json-object |\n| Instant | instant |\n| Payload | record<body:ref<JSON>,at:ref<Instant>> |\n')
            model=compiler.load(p,pi,t,domain_specs=[ds],allow_draft=True,allow_partial=True)
            self.assertEqual(len(model['named_type_definitions']),3)
            self.assertFalse(model['unresolved_domains'])
            output=root/'Model.json';output.write_text(json.dumps(model,ensure_ascii=False),encoding='utf8')
            self.assertEqual(conformance.validate(p,pi,[t],output,domain_specs=[ds],allow_draft=True)['status'],'passed')
            # Generated negative fixture, never a correction of the real Model.
            field=next(f for f in model['fields'] if f['id']=='input.data')
            field['domain']['of']['fields'][0]['domain']['of']={'type':'json','root':'value'}
            tampered=root/'TamperedModel.json';tampered.write_text(json.dumps(model,ensure_ascii=False),encoding='utf8')
            self.assertEqual(conformance.validate(p,pi,[t],tampered,domain_specs=[ds],allow_draft=True)['status'],'blocked')


if __name__=='__main__':unittest.main()
