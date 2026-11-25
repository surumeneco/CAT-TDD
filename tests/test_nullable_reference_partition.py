"""Exact local equality classes for required nullable opaque identifiers/revisions.

Null is a value, not missing. The semantic oracle is the Source's complement
(or its deliberately incomplete/overlapping variants), not a test fixture of
preselected product IDs. Non-equality and optional Presence remain unsupported.
"""
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.cat-system/scripts'))
from cat_compile_v2 import load, render_model_markdown, selection_vectors, Blocked
from cat_model_conformance import validate
from test_cat_compile_readable import write_v2
from test_intrinsic_rule_proofs import approve_fixture
from test_conformance_runtime import base_work
from cat_flow import conformance_work


def fixture(root, domain='string', guard='input.request == state.resolved', reject=None,
            observation=False, presence='required', extras=()):
    p, pi, t = write_v2(root, False)
    left = 'observation.resolved' if observation else 'state.resolved'
    if observation:
        p.write_text(p.read_text().replace('## Actions', f'| {left} | same resolved value | nullable<{domain}> |\n## Actions'))
    else:
        p.write_text(p.read_text().replace('| state.ready | boolean |', f'| state.ready | boolean |\n| {left} | nullable<{domain}> |'))
    pi.write_text(pi.read_text().replace('| input.enabled | receive | boolean | required |',
        f'| input.request | receive | {domain} | {presence} |' + ''.join(f'\n| {n} | receive | {d} | required |' for n,d in extras)))
    guard = guard.replace('state.resolved', left)
    reject = f'not ({guard})' if reject is None else reject.replace('state.resolved',left)
    t.write_text(t.read_text().replace('`input.enabled`', f'`{guard}`').replace('`not input.enabled`', f'`{reject}`'))
    for f in (p,pi,t):approve_fixture(f)
    return p,pi,t


class NullableReferencePartitionTests(unittest.TestCase):
    def test_exact_local_gate_and_independent_models(self):
        for domain,guard in [('string','input.request == state.resolved'),
                             ('string','state.resolved == null or input.request == state.resolved'),
                             ('string','state.resolved != null and state.resolved == "fixed" and input.request == state.resolved'),
                             ('string','state.resolved == "series" or state.resolved == "language"'),
                             ('integer','input.request == state.resolved'),
                             ('integer[1..]','input.request == state.resolved')]:
            for obs in (False,True):
                with self.subTest(domain=domain,guard=guard,observation=obs),tempfile.TemporaryDirectory() as d:
                    root=Path(d); source=fixture(root,domain,guard,observation=obs)
                    work=base_work();work['compilation']={'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','model':'Model.json','allow_draft':False,'allow_partial':True}
                    wp=root/'Work.json';wp.write_text(json.dumps(work))
                    result=conformance_work(wp,work,'process-closure')
                    self.assertEqual(result['status'],'passed',result)
                    model=load(*source)
                    self.assertEqual(model['coverage_checks']['submit']['proof_method'],'nullable-reference-equality-partition/v1')
                    for name,body in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                        path=root/name;path.write_text(body,encoding='utf-8')
                        self.assertEqual(validate(*source,path)['status'],'passed')
                    if not obs:
                        self.assertEqual(len(selection_vectors(model)['cases']),2)

    def test_cli_receipts_preserve_negative_verdicts(self):
        for reject,passed in [(None,True),('state.resolved != null and input.request != state.resolved',False),('input.request == state.resolved',False)]:
            with self.subTest(reject=reject),tempfile.TemporaryDirectory() as d:
                root=Path(d);fixture(root,reject=reject,observation=True)
                work=base_work();work['compilation']={'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md','tce':'TCE.md','model':'Model.json','allow_draft':False,'allow_partial':True}
                wp=root/'Work.json';wp.write_text(json.dumps(work))
                cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),'conformance','--kind','process-closure','--work',str(wp)]
                r=subprocess.run(cmd,text=True,capture_output=True,timeout=30)
                actual=json.loads(r.stdout);self.assertEqual(actual['status']=='passed',passed,actual)
                receipt=json.loads((root/'.cat-flow/conformance/process-closure.json').read_text())
                self.assertEqual(receipt['verdict'],actual['status'])

    def test_null_and_unequal_gaps_overlap_and_unsupported(self):
        for reject in ('state.resolved != null and input.request != state.resolved',
                       'state.resolved == null', 'input.request == state.resolved'):
            with self.subTest(reject=reject),tempfile.TemporaryDirectory() as d:
                root=Path(d);source=fixture(root,reject=reject)
                model=load(*source,allow_draft=True,allow_partial=True)
                self.assertIn(model['coverage_checks']['submit']['result'],('uncovered','conflict'))
                self.assertNotEqual(model['status'],'confirmed')
        for kw in ({'guard':'concat(input.request,"x") == state.resolved'},
                   {'presence':'optional'}):
            with self.subTest(kw=kw),tempfile.TemporaryDirectory() as d:
                source=fixture(Path(d),**kw)
                model=load(*source,allow_draft=True,allow_partial=True)
                self.assertNotEqual(model['coverage_checks']['submit']['result'],'proved')

    def test_separate_connected_components_and_tampered_proof(self):
        # 7 names total, but independent equality groups of size 3, 2, 2.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=fixture(root,guard='input.request == state.resolved and input.request == input.other and input.a == input.b and input.c == input.d',
                extras=(('input.other','nullable<string>'),('input.a','string'),('input.b','nullable<string>'),('input.c','integer'),('input.d','nullable<integer>')))
            model=load(*source)
            self.assertEqual(model['coverage_checks']['submit']['result'],'proved')
            model['coverage_checks']['submit']['abstract_state_count']+=1
            target=root/'Model.json';target.write_text(json.dumps(model))
            self.assertNotEqual(validate(*source,target)['status'],'passed')

if __name__=='__main__':unittest.main()
