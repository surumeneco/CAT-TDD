"""Explicit per-operation Presence is preserved and scoped to the originating PI."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts'))
from cat_compile_v2 import load,Blocked
import cat_model_conformance as conformance
import cat_operation_presence as presence
import test_impl_obligations_extended as fixture

class OperationPresenceTests(unittest.TestCase):
 def create(self,root):
  p,a,b,t,cr,ds=fixture.TestObligations().setup(root)
  source=a.read_text()
  source=source.replace('| op.first | accept | submit |','| op.first | accept | submit |\n| op.other | accept | submit |')
  source+='''
## Operation presence
| Operation | Field | Presence |
| --- | --- | --- |
| op.first | input.ready | optional |
| op.other | input.ready | absent |
'''
  a.write_text(source)
  return p,a,b,t,cr,ds
 def test_operation_specific_presence_does_not_erase_null_identity(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);p,a,b,t,cr,ds=self.create(root)
   model=load(p,[a,b],[t],allow_partial=True)
   self.assertEqual(len(model['operation_presence']),2)
   path=root/'Model.json';path.write_text(json.dumps(model))
   self.assertEqual(conformance.validate(p,[a,b],[t],path)['status'],'passed')
   result=presence.diagnostics(model,path.read_bytes())
   scope={(x['operation'],x['field']):x for x in result['probes']}
   optional=scope[('op.first','input.ready')]
   absent=scope[('op.other','input.ready')]
   values=lambda x:{c['kind']:c for c in x['cases']}
   self.assertTrue(values(optional)['missing']['type_accepts'])
   self.assertFalse(values(optional)['null']['type_accepts'])
   self.assertTrue(values(optional)['representative-value']['type_accepts'])
   self.assertTrue(values(absent)['missing']['type_accepts'])
   self.assertFalse(values(absent)['representative-value']['type_accepts'])
   self.assertEqual(result['conformance_status'],'not-run')
   self.assertEqual(result['test_execution_status'],'not-run')
   model['operation_presence'][0]['presence']='required'
   path.write_text(json.dumps(model))
   self.assertIn('operation_presence',conformance.validate(p,[a,b],[t],path)['mismatches'])
 def test_other_pi_operation_or_field_binding_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);p,a,b,t,cr,ds=self.create(root)
   data=a.read_text().replace('| op.other | input.ready | absent |',
                              '| op.second | input.ready | absent |')
   a.write_text(data)
   with self.assertRaisesRegex(Blocked,'operation outside owning PI'):
    load(p,[a,b],[t],allow_partial=True)


class OperationNominalDiagnosticsTests(unittest.TestCase):
    def test_resolved_named_type_and_null_are_observable_without_fabricated_gate(self):
        domains=(
          {'type':'reference','name':'Approved','resolved':True,
           'of':{'type':'enum','values':['A']}},
          {'type':'null'},
          {'type':'union','variants':[{'type':'null'},{'type':'boolean'}]},
        )
        for domain in domains:
            with self.subTest(domain=domain):
                m={'pi_operations':[{'id':'get','source_pi':'pi.one',
                                     'direction':'provide'}],
                   'fields':[{'id':'output.value','role':'output','source_pi':'pi.one',
                              'presence':'required','domain':domain}],
                   'operation_presence':[]}
                r=presence.diagnostics(m,json.dumps(m).encode())
                cases=r['probes'][0]['cases']
                rep=next(x for x in cases if x['kind']=='representative-value')
                self.assertTrue(rep['type_accepts'],rep)
                self.assertEqual(r['conformance_status'],'not-run')

if __name__=='__main__':unittest.main()
