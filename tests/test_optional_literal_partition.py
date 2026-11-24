"""Exact optional scalar partitions preserve absence and evaluation order."""
import json
import subprocess
import hashlib
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".cat-system" / "scripts"))
from test_cat_compile_readable import write_v2
from cat_compile_v2 import load, selection_vectors, expand_cases
import cat_model_conformance


class OptionalLiteralPartitionTests(unittest.TestCase):
    def source(self, root, domain, comparator, literal, unsafe=False, gap=False):
        p, pi, tce = write_v2(root, False)
        pi.write_text(pi.read_text(encoding='utf8').replace('| input.enabled | receive | boolean | required |',
            f'| input.enabled | receive | {domain} | optional |'), encoding='utf8')
        expr = f'input.enabled {comparator} {literal}'
        complement = {'==': '!=', '<': '>='}[comparator]
        other = f'input.enabled {complement} {literal}'
        positive = expr if unsafe else f'is_present(input.enabled) and {expr}'
        negative = f'is_present(input.enabled) and {other}'
        text = tce.read_text(encoding='utf8').replace('`input.enabled`', f'`{positive}`').replace('`not input.enabled`', f'`{negative}`')
        if not gap:
            text += '| demo.missing | submit | `is_missing(input.enabled)` | 1 | `output.accepted = false` |\n'
        tce.write_text(text, encoding='utf8')
        return p, pi, tce

    def test_exact_present_and_missing_cells(self):
        for domain, comparator, literal, method in [('string', '==', '"yes"', 'optional-string-literal-equality-partition/v1'),
                ('integer[1..]', '<', '9', 'optional-integer-literal-partition/v1')]:
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                p, pi, tce = self.source(root, domain, comparator, literal)
                model = load(p, pi, tce, allow_draft=True)
                check = model['coverage_checks']['submit']
                self.assertEqual(check['result'], 'proved', check)
                self.assertEqual(check['proof_method'], method)
                self.assertEqual(model['presence_unproven'], [])
                out = root / 'model.json'; out.write_text(json.dumps(model), encoding='utf8')
                self.assertEqual(cat_model_conformance.validate(p, pi, tce, out, allow_draft=True)['status'], 'passed')
                # Selection is tested against the same source's confirmed test fixture,
                # not as an assertion of authority for a product Artifact.
                for path in (p,pi,tce):
                    path.write_text(path.read_text(encoding='utf8').replace('status: draft', 'status: confirmed').replace("decision_ref: ''", 'decision_ref: https://example.org/fixture-decision'), encoding='utf8')
                confirmed = load(p,pi,tce)
                out.write_text(json.dumps(confirmed), encoding='utf8')
                self.assertEqual(cat_model_conformance.validate(p,pi,tce,out)['status'],'passed')
                confirmed['coverage_checks']['submit']['abstract_state_count'] -= 1
                out.write_text(json.dumps(confirmed), encoding='utf8')
                self.assertEqual(cat_model_conformance.validate(p,pi,tce,out)['status'],'blocked')
                confirmed = load(p,pi,tce)
                vectors = selection_vectors(confirmed)
                self.assertEqual(len(expand_cases(confirmed,vectors)),3)
                self.assertTrue(any('input.enabled' not in case['input'] for case in vectors['cases']))

    def test_canonical_process_closure(self):
        for gap in (False, True):
            with self.subTest(gap=gap), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                sources = self.source(root, 'string', '==', '"yes"', gap=gap)
                for path in sources:
                    path.write_text(path.read_text(encoding='utf8').replace('status: draft', 'status: confirmed').replace("decision_ref: ''", 'decision_ref: synthetic-test-only'), encoding='utf8')
                work = {
                    'schema':'cat-work/v1', 'id':'demo.optional-partition.work',
                    'entry':'confirmed-spec', 'mode':'implementation', 'flow':'spec-implementation',
                    'work_kind':'implementation', 'parent':'', 'depends_on':[],
                    'issue_ref':'spec-entry', 'project_entry_ref':'project-entry',
                    'normative':[{'uri':'spec'}], 'evidence':[{'uri':'evidence'}],
                    'specification':{'status':'confirmed','decision_ref':'decision','artifact_refs':['demo.tce']},
                    'scope':{'process_ids':['demo.process'],'changed_ids':[],'preserved_ids':[]},
                    'technologies':[], 'repositories':[], 'checks':[], 'gates':[],
                    'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md',
                                   'tce':'TCE.md','model':'Model.json','allow_draft':False,'allow_partial':True},
                }
                work_path=root/'Work.json'; work_path.write_text(json.dumps(work), encoding='utf8')
                argv=[sys.executable,str(Path(__file__).resolve().parents[1]/'.cat-system/scripts/cat_flow.py'),
                      'conformance','--work',str(work_path),'--kind','process-closure']
                run=subprocess.run(argv,capture_output=True,text=True,check=False,timeout=75)
                self.assertEqual(run.returncode,0,(run.stdout,run.stderr))
                gate=json.loads(run.stdout)
                self.assertEqual(gate['status'],'inconclusive' if gap else 'passed',gate)
                receipt=root/'.cat-flow/conformance/process-closure.json'
                model=root/'.cat-flow/cache/process-closure.model.json'
                digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
                print('OPTIONAL-PARTITION-GATE',json.dumps({'gap':gap,'argv':argv,'exit':run.returncode,
                      'status':gate['status'],'source_sha256':{p.name:digest(p) for p in sources},
                      'receipt_sha256':digest(receipt),'model_sha256':digest(model)},sort_keys=True),flush=True)

    def test_unsafe_and_gap_remain_nonproved(self):
        for domain, comparator, literal in [('string','==','"yes"'),('integer[1..]','<','9')]:
            for unsafe,gap,expected in [(True,False,'unproven'),(False,True,'uncovered')]:
                with self.subTest(domain=domain,expected=expected), tempfile.TemporaryDirectory() as d:
                    model=load(*self.source(Path(d),domain,comparator,literal,unsafe,gap),allow_draft=True)
                    self.assertEqual(model['coverage_checks']['submit']['result'],expected)

if __name__ == '__main__': unittest.main()
