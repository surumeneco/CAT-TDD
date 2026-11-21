"""Source-bound Markdown Model semantics: resolved nominal types, PI operation Presence, observation timing."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_compile_v2 import load,render_model_markdown,Blocked
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_named_type_resolution import add_named_field,spec
from test_operation_presence import OperationPresenceTests
from test_observation_operation_availability import sample


class MarkdownSemanticProvenanceTests(unittest.TestCase):
    def check(self,p,pis,t,model,path,**kwargs):
        path.write_text(render_model_markdown(model),encoding='utf-8')
        verdict=validate(p,pis,[t],path,allow_draft=True,**kwargs)
        self.assertEqual(verdict['status'],'passed',verdict)
        return path.read_text(encoding='utf-8')

    def test_named_domains_preserve_structure_and_source(self):
        for ja in (False,True):
            with self.subTest(ja=ja), tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,t=write_v2(root,ja)
                if ja:
                    raw=pi.read_text(encoding='utf-8')
                    pi.write_text(raw.replace('| input.enabled | 受信 | 真偽 | 必須 |',
                                   '| input.enabled | 受信 | 真偽 | 必須 |\n| input.data | 受信 | record<Change> | 必須 |'),
                                  encoding='utf-8')
                else:add_named_field(pi)
                ds=spec(root,'| User | record<name:string,active:boolean> |\n'
                             '| Change | record<owner:record<User>,mode:nullable<enum{A,B}>> |\n')
                model=load(p,pi,t,allow_draft=True,domain_specs=[ds]);dest=root/'Model.md'
                original=self.check(p,pi,t,model,dest,domain_specs=[ds])
                self.assertIn('Resolved named types' if not ja else '解決済み名前付き型',original)
                variants=(original.replace('"source_artifact": "demo.types"','"source_artifact": "unrelated.source"',1),
                          original.replace('## Resolved named types' if not ja else '## 解決済み名前付き型','## omitted'))
                for modified in variants:
                    with self.subTest(variant='tamper'):
                        self.assertNotEqual(modified,original)
                        dest.write_text(modified,encoding='utf-8')
                        try:verdict=validate(p,pi,[t],dest,allow_draft=True,domain_specs=[ds])
                        except Blocked:continue
                        self.assertEqual(verdict['status'],'blocked',verdict)
                dest.write_text(original.replace('レコード<Change>' if ja else 'record<Change>',
                                                'レコード<Other>' if ja else 'record<Other>',1),encoding='utf-8')
                self.assertIn('domains',validate(p,pi,[t],dest,allow_draft=True,domain_specs=[ds])['mismatches'])

    def test_operation_presence_exact_source_binding(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,a,b,t,cr,ds=OperationPresenceTests().create(root)
            model=load(p,[a,b],[t],allow_partial=True,allow_draft=True);dest=root/'Model.md'
            original=self.check(p,[a,b],t,model,dest)
            self.assertIn('Operation presence',original)
            dest.write_text(original.replace('| op.first | input.ready | optional |',
                                             '| op.first | input.ready | required |',1),encoding='utf-8')
            self.assertIn('operation_presence',validate(p,[a,b],[t],dest,allow_draft=True)['mismatches'])

    def test_observation_trigger_binding_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pis,t=sample(root,'B');model=load(p,pis,t)
            dest=root/'Model.md';original=self.check(p,pis,t,model,dest)
            self.assertIn('Observation availability',original)
            dest.write_text(original.replace('| observation.completed | correlated completion observation |',
                                             '| observation.completed | forged observation provider |',1),encoding='utf-8')
            self.assertIn('observation_availability',validate(p,pis,[t],dest,allow_draft=True)['mismatches'])


if __name__=='__main__':unittest.main()
