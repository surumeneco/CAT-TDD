"""A constructed record must fit the declared result Domain, not its broad kind."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'.cat-system'/'scripts')]
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load, render_model_markdown, Blocked
from cat_model_conformance import validate

class RecordUnionEffects(unittest.TestCase):
    def fixture(self, root, expr, other=None, input_domain='integer[0..10]'):
        p,pi,tce=write_v2(root,False)
        target='union<record<kind:enum{ok},value:record<n:integer[0..10]>>,record<kind:enum{error},reason:string>>'
        pi.write_text(pi.read_text(encoding='utf-8').replace('| output.accepted | send | boolean | required |',
            '| input.number | receive | '+input_domain+' | required |\n'
            '| input.reason | receive | string | required |\n'
            '| input.result | receive | '+target+' | required |\n'
            '| output.accepted | send | '+target+' | required |'),encoding='utf-8')
        tce.write_text(tce.read_text(encoding='utf-8').replace('output.accepted = true','output.accepted = '+expr).replace('output.accepted = false','output.accepted = '+(other or expr)),encoding='utf-8')
        return p,pi,tce

    def test_proved_construction_and_reference(self):
        good='{"kind":"ok","value":{"n":input.number}}'
        error='{"kind":"error","reason":input.reason}'
        for expr,other in [(good,error),('input.result',None),('{"kind":"ok","value":{"n":0}}',None)]:
            with self.subTest(expr=expr), tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,tce=self.fixture(root,expr,other)
                model=load(p,pi,tce,allow_draft=True,allow_partial=True)
                self.assertEqual(model['unverified_effect_ids'],[])
                for name,data in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                    path=root/name;path.write_text(data,encoding='utf-8')
                    self.assertEqual(validate(p,pi,tce,path,allow_draft=True)['status'],'passed')

    def test_invalid_or_unproved_construction(self):
        for expr in ['{"kind":"other","value":{"n":0}}','{"kind":"ok"}',
                     '{"kind":"ok","value":{"n":0},"reason":"extra"}',
                     '{"kind":"error","reason":"bad","value":{"n":0}}',
                     '{"kind":"ok","value":{"n":11}}','{"kind":"error","reason":1}',
                     '{"kind":"ok","value":{"n":input.number}}']:
            with self.subTest(expr=expr), tempfile.TemporaryDirectory() as td:
                p,pi,tce=self.fixture(Path(td),expr,input_domain='integer')
                with self.assertRaises(Blocked):load(p,pi,tce,allow_draft=True,allow_partial=True)

if __name__=='__main__':unittest.main()
