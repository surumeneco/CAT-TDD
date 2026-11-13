#!/usr/bin/env python3
"""Regression: explicit operation Presence is never silently normalized to a value."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
import cat_compile_v2 as compiler


def model(presence='optional'):
    return {
        'schema': 'cat-test-model/v2', 'process':'demo.process',
        'status':'confirmed','triggers':[{'id':'submit','origin':'demo.pi'}],
        'fields':[
            {'id':'input.flag','role':'input','source_pi':'demo.pi','presence':'required','domain':{'type':'boolean'}},
            {'id':'state.ready','role':'state','domain':{'type':'boolean'}},
            {'id':'output.ok','role':'output','source_pi':'demo.pi','presence':'required','domain':{'type':'boolean'}},
        ],
        'pi_operations':[{'id':'submit.op','direction':'accept','trigger':'submit','source_pi':'demo.pi'}],
        'operation_presence':[{'operation':'submit.op','field':'input.flag','presence':presence,'source_pi':'demo.pi'}],
        'definitions':[],'pi_constraints':[],
        'rules':[{'id':'demo.rule','trigger':'submit','when':{'literal':True},
                  'allowed':[{'write':[{'target':'output.ok','expr':{'literal':True}}],
                              'unchanged':['state.ready'],'absent_outputs':[]}]}],
    }


def vectors(*cases):
    return {'schema':compiler.V,'process':'demo.process','cases':list(cases)}


def case(input_,operation=None):
    out={'id':'case.demo.rule','trigger':'submit','input':input_,
         'state':{'state.ready':False}}
    if operation is not None:out['operation']=operation
    return out


class ExplicitPresenceVectorTest(unittest.TestCase):
    def test_optional_missing_is_preserved_and_queue_accepts_explicit_witness(self):
        m=model('optional')
        v=vectors(case({}))
        expanded=compiler.expand_cases(m,v)
        self.assertEqual(expanded[0]['input'],{})
        self.assertTrue(expanded[0]['allowed'][0]['output']['output.ok'])
        q=compiler.make_queue(m,v,b'fixed-model',b'fixed-vectors')
        self.assertEqual(q['items'][0]['model_ref'],'demo.rule')

    def test_explicit_undefined_is_not_null_or_missing(self):
        m=model('undefined')
        value={'$cat_presence':'undefined'}
        expanded=compiler.expand_cases(m,vectors(case({'input.flag':value})))
        self.assertEqual(expanded[0]['input']['input.flag'],value)
        for payload in ({}, {'input.flag':None},{'input.flag':False}):
            with self.subTest(payload=payload):
                with self.assertRaises(compiler.Blocked):
                    compiler.expand_cases(m,vectors(case(payload)))

    def test_operation_override_does_not_rewrite_domain(self):
        m=model('absent')
        compiler.expand_cases(m,vectors(case({})))
        with self.assertRaisesRegex(compiler.Blocked,'Presence'):
            compiler.expand_cases(m,vectors(case({'input.flag':False})))

    def test_guard_may_not_read_missing_input_without_explicit_semantics(self):
        m=model('optional')
        m['rules'][0]['when']={'ref':'input.flag'}
        with self.assertRaisesRegex(compiler.Blocked,'reads missing'):
            compiler.expand_cases(m,vectors(case({})))

    def test_ambiguous_operation_requires_explicit_binding(self):
        m=model('optional')
        m['pi_operations'].append({'id':'other.op','direction':'accept',
                                   'trigger':'submit','source_pi':'demo.pi'})
        with self.assertRaisesRegex(compiler.Blocked,'ambiguous accepted'):
            compiler.expand_cases(m,vectors(case({})))
        self.assertEqual(len(compiler.expand_cases(m,vectors(case({},'submit.op')))),1)

    def test_output_presence_requires_explicit_provide_operation(self):
        m=model('required')
        m['pi_operations'].append({'id':'reply.op','direction':'provide',
                                   'trigger':'submit','source_pi':'demo.pi'})
        m['operation_presence'].append({'operation':'reply.op','field':'output.ok',
                                        'presence':'optional','source_pi':'demo.pi'})
        with self.assertRaisesRegex(compiler.Blocked,'output_operation'):
            compiler.expand_cases(m,vectors(case({'input.flag':True})))
        witness=case({'input.flag':True});witness['output_operation']='reply.op'
        self.assertEqual(len(compiler.expand_cases(m,vectors(witness))),1)
        m['operation_presence'][-1]['presence']='absent'
        with self.assertRaisesRegex(compiler.Blocked,'absent output emitted'):
            compiler.expand_cases(m,vectors(witness))

    def test_required_provided_output_cannot_be_silently_absent(self):
        m=model('required')
        m['pi_operations'].append({'id':'reply.op','direction':'provide',
                                   'trigger':'submit','source_pi':'demo.pi'})
        witness=case({'input.flag':True});witness['output_operation']='reply.op'
        m['rules'][0]['allowed'][0]['write']=[]
        with self.assertRaisesRegex(compiler.Blocked,'required output missing'):
            compiler.expand_cases(m,vectors(witness))

    def test_automatic_witness_refuses_nonrequired_presence(self):
        with self.assertRaisesRegex(compiler.Blocked,'non-required operation Presence'):
            compiler.selection_vectors(model('optional'))

    def test_undefined_renderer_requires_transport_binding(self):
        m=model('undefined');v=vectors(case({'input.flag':{'$cat_presence':'undefined'}}))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'binding.json'
            p.write_text(json.dumps({'schema':compiler.D,'process':'demo.process','driver':'./driver'}))
            with self.assertRaisesRegex(compiler.Blocked,'undefined transport binding'):
                compiler.emit_vitest(m,v,p)


    def test_explicit_js_undefined_transport_generates_real_undefined_input(self):
        m=model('undefined');v=vectors(case({'input.flag':{'$cat_presence':'undefined'}}))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'binding.json'
            p.write_text(json.dumps({'schema':compiler.D,'process':'demo.process',
                'driver':'./driver','undefined_transport':'js-undefined/v1'}))
            content=compiler.emit_vitest(m,v,p)
            self.assertIn('decodeUndefinedInput(rawInput)',content)
            self.assertIn('decoded[id] = undefined',content)
            self.assertIn('driver as {undefinedTransport?: string}',content)
            self.assertIn('toBe("js-undefined/v1")',content)
            self.assertIn('hasOwnProperty.call(input, "input.flag")',content)
            self.assertIn('input["input.flag"]).toBeUndefined()',content)
            self.assertEqual(content,compiler.emit_vitest(m,v,p))

    def test_wrong_undefined_transport_is_blocked_even_with_correct_presence(self):
        m=model('undefined');v=vectors(case({'input.flag':{'$cat_presence':'undefined'}}))
        for transport in (None,'json-null/v1','fake',''):
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as td:
                binding={'schema':compiler.D,'process':'demo.process','driver':'./driver'}
                if transport is not None:binding['undefined_transport']=transport
                p=Path(td)/'binding.json'
                p.write_text(json.dumps(binding))
                with self.assertRaises(compiler.Blocked):
                    compiler.emit_vitest(m,v,p)

    def test_ordinary_presence_does_not_require_undefined_transport(self):
        m=model('required');v=vectors(case({'input.flag':True}))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'binding.json'
            p.write_text(json.dumps({'schema':compiler.D,'process':'demo.process','driver':'./driver'}))
            rendered=compiler.emit_vitest(m,v,p)
            self.assertNotIn('decodeUndefinedInput',rendered)
            self.assertNotIn('undefinedTransport',rendered)


if __name__=='__main__':unittest.main()
