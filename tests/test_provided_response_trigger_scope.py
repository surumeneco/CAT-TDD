"""CAT41 U02: a response received on a provided PI is readable only at an explicit Process Trigger.

Fixtures are synthetic; Trigger alignment does NOT prove peer/request correlation or delivery.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.cat-system'/'scripts'),str(ROOT/'tests')]
from cat_compile_v2 import Blocked, load, expand_cases,selection_vectors
from cat_model_conformance import validate
from test_pi_constraint_operation_scope import fixture


def source(root, *, linked=True, duplicate=False):
    p,pis,tce=fixture(root)
    b=pis[1]
    raw=b.read_text(encoding='utf-8')
    raw=raw.replace('| demo.caller | receive |','| demo.caller | bidirectional |')
    # A reply from an independently provided PI is not another accepted request.
    if linked:
        op='| BotReply | provide | A |'
        if duplicate:
            op+='\n| OtherReply | provide | A |'
    else:
        op='| BotReply | provide | — |'
    raw=raw.replace('| B | accept | B |','| B | accept | B |\n'+op)
    b.write_text(raw,encoding='utf-8')
    t=tce.read_text(encoding='utf-8')
    t=t.replace('| A.done | A | `true` | 1 | `state.done = true` |',
                '| A.true | A | `input.other` | 1 | `state.done = true` |\n'
                '| A.false | A | `not input.other` | 1 | `state.done = false` |')
    tce.write_text(t,encoding='utf-8')
    return p,pis,tce

class ProvidedResponseScopeTests(unittest.TestCase):
    def test_explicit_provided_operation_makes_response_readable_in_trigger(self):
        with tempfile.TemporaryDirectory() as td:
            p,pis,tce=source(Path(td))
            model=load(p,pis,tce)
            self.assertEqual(model['status'],'confirmed')
            self.assertEqual(model['coverage_checks']['A']['result'],'proved')
            self.assertIn('input.other',model['coverage_checks']['A']['guard_refs'])
            path=Path(td)/'Model.json';path.write_text(json.dumps(model),encoding='utf-8')
            self.assertEqual(validate(p,pis,tce,path)['status'],'passed')
            cases=selection_vectors(model)['cases']
            self.assertEqual({x['trigger'] for x in cases},{'A','B'})
            self.assertTrue(all('input.other' in x['input'] for x in cases if x['trigger']=='A'))
            expanded=expand_cases(model,{'schema':'cat-test-vectors/v2','process':'demo.scope',
                'cases':[{'id':'a_reply','trigger':'A','input':{'input.a':True,'input.b':True,'input.other':False},
                          'state':{'state.done':False}}]})
            self.assertEqual(expanded[0]['source_tce'],'A.false')

    def test_model_cannot_rewrite_provider_trigger_as_unbound(self):
        with tempfile.TemporaryDirectory() as td:
            p,pis,tce=source(Path(td))
            model=load(p,pis,tce)
            provider=next(op for op in model['pi_operations'] if op['id']=='BotReply')
            provider['trigger']=None
            model_path=Path(td)/'Model.json'
            model_path.write_text(json.dumps(model),encoding='utf-8')
            result=validate(p,pis,tce,model_path)
            self.assertEqual(result['status'],'blocked')
            self.assertIn('operations',result['mismatches'])

    def test_unbound_provided_operation_does_not_grant_reply_access(self):
        with tempfile.TemporaryDirectory() as td:
            p,pis,tce=source(Path(td),linked=False)
            with self.assertRaises(Blocked):load(p,pis,tce)

    def test_ambiguous_provided_owners_cannot_grant_reply_access(self):
        with tempfile.TemporaryDirectory() as td:
            p,pis,tce=source(Path(td),duplicate=True)
            with self.assertRaises(Blocked):load(p,pis,tce)

if __name__=='__main__':unittest.main()
