"""Independent live stream-boundary acceptance through the canonical Work Gate."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'.cat-system/scripts'
sys.path.insert(0,str(SCRIPTS))
import cat_flow
from catlib.work import work_file


def run_git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.STDOUT).decode().strip()


def source(kind,pid,ident,refs,body):
    return (f"---\ncat_version: '0.3'\nkind: {kind}\nid: {ident}\nstatus: confirmed\nprocess: {pid}\n"
            'source_refs: ["synthetic-test-only"]\ndecision_ref: synthetic-test-only\n'
            f'refs: {json.dumps(refs)}\nsemantic_contract: markdown-v2\nlanguage: en\n---\n\n'+body+'\n')


def flow(work,*args):
    run=subprocess.run([sys.executable,str(SCRIPTS/'cat_flow.py'),args[0],'--work',str(work),*args[1:]],
        capture_output=True,text=True,encoding='utf-8',timeout=60)
    return run,json.loads(run.stdout or run.stderr)


def dep(path,base):
    return {'path':path.relative_to(base).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def write_implementation(repo,variant):
    producer='''import json,sys
frame=json.load(sys.stdin)
v=frame['fields']['input.flag']
result={'execution':frame['execution'],'process':'producer','pi':'producer.out','operation':'emit','fields':{'output.flag':v}}
print(json.dumps(result))
'''
    receiver='''import json,sys
frame=json.load(sys.stdin)
v=frame['fields']['output.flag']
result={'execution':frame['execution'],'process':'receiver','pi':'receiver.out','operation':'emit','fields':{'output.flag':not v}}
print(json.dumps(result))
'''
    if variant=='alternate':
        producer=producer.replace('v=frame[\'fields\'][\'input.flag\']','v=bool(frame[\'fields\'][\'input.flag\'])')
        receiver=receiver.replace('not v','v is False')
    if variant=='wrong-source':producer=producer.replace("'output.flag':v","'output.flag':not v")
    if variant=='wrong-operation':producer=producer.replace("'operation':'emit'","'operation':'wrong'")
    if variant=='wrong-process':producer=producer.replace("'process':'producer'","'process':'other'")
    if variant=='wrong-receiver':receiver=receiver.replace("'output.flag':not v","'output.flag':v")
    if variant=='wrong-execution':receiver=receiver.replace("frame['execution']","'replayed'")
    if variant=='missing':receiver='import sys\nsys.stdin.read()\n'
    if variant=='fake-receipt':receiver='print(\'{"status":"passed"}\')\n'
    if variant=='duplicate':producer=producer.replace('print(json.dumps(result))','print(json.dumps(result))\nprint(json.dumps(result))')
    if variant=='wrong-type':producer=producer.replace("'output.flag':v","'output.flag':int(v)")
    for pid,code in [('producer',producer),('receiver',receiver)]:
        (repo/(pid+'.py')).write_text(code,encoding='utf-8')
    run_git(repo,'add','.');run_git(repo,'commit','--allow-empty','-qm','fixture implementation: '+variant)
    return run_git(repo,'rev-parse','HEAD')


def fixture(root,variant='positive'):
    repo=root/'repo';repo.mkdir()
    run_git(repo,'init','-q');run_git(repo,'config','user.name','CAT fixture');run_git(repo,'config','user.email','cat@example.invalid');run_git(repo,'config','core.autocrlf','false')
    head=write_implementation(repo,variant)
    docs=root/'work';docs.mkdir(); models={};assemblies={};works={}
    for pid,peer_in,peer_out,expr in [('producer','caller','receiver','input.flag'),('receiver','producer','observer','not(input.flag)')]:
        folder=docs/pid;folder.mkdir()
        p=folder/'Process.md';pis=[folder/'In.md',folder/'Out.md'];tce=folder/'TCE.md'
        ids=[pid+'.in',pid+'.out']
        p.write_text(source('process',pid,pid,ids, f'''# Process
## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| {ids[0]} |
| {ids[1]} |
## State
| ID | Domain |
| --- | --- |
## Observations
| ID | Source | Domain |
| --- | --- | --- |
## Actions
| ID | Target | Domain |
| --- | --- | --- |
## Triggers
| ID | Source |
| --- | --- |
| start | {ids[0]}/receive |
'''),encoding='utf-8')
        for pi,ident,peer,direction,field,op,role in zip(pis,ids,[peer_in,peer_out],['receive','send'],['input.flag','output.flag'],['receive','emit'],['accept','provide']):
            pi.write_text(source('pi',pid,ident,[],f'''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| {peer} | {direction} |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| {field} | {direction} | boolean | required |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| {op} | {role} | start |
## Constraints
| Expression |
| --- |
'''),encoding='utf-8')
        tce.write_text(source('tce',pid,pid+'.tce',ids,f'''# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |
| transfer | start | `true` | 1 | `output.flag = {expr}` |
'''),encoding='utf-8')
        w={'schema':'cat-work/v1','id':pid+'.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'synthetic-test-only','project_entry_ref':'synthetic-test-only','normative':[{'uri':'synthetic-test-only'}],'evidence':[{'uri':'synthetic-test-only'}],'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':[pid+'.tce']},'scope':{'process_ids':[pid],'changed_ids':[],'preserved_ids':[]},'technologies':[],'repositories':[{'name':'fixture','path':str(repo),'allowed_paths':['*.py'],'production_paths':['*.py'],'test_paths':[]}],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'In.md','pis':['In.md','Out.md'],'tce':'TCE.md','model':'Model.json','obligations':'Obligations.json','allow_draft':False}}
        wp=folder/'Work.json';wp.write_text(json.dumps(w),encoding='utf-8');works[pid]=wp
        for args in [('conformance','--kind','process-closure'),('compile','--kind','model'),('conformance','--kind','model-conformance'),('obligations',)]:
            run,rec=flow(wp,*args)
            if rec.get('status')!='passed':raise AssertionError((pid,args,run.stdout,run.stderr))
        models[pid]=dep(folder/'Model.json',docs)
        assemblies[pid]={'process':dep(p,docs),'pis':[dep(pi,docs) for pi in pis],'tces':[dep(tce,docs)]}
    binding={'schema':'cat-runtime-boundary-binding/v1','profile':'finite-required-stream/v1','models':models,'source_assemblies':assemblies,'links':[{'source_process':'producer','source_pi':'producer.out','source_operation':'emit','target_process':'receiver','target_pi':'receiver.in','target_operation':'receive','field_links':[{'source_field':'output.flag','target_field':'input.flag'}]}],'endpoints':{pid:{'repository':'fixture','head':head,'script':dep(repo/(pid+'.py'),repo)} for pid in works}}
    # Work paths are confined to declared roots. The common binding and both
    # assemblies sit inside a declared read-only fixture repository root.
    # Here they are kept at the same parent as both Work directories instead.
    bp=docs/'Boundary.json';bp.write_text(json.dumps(binding),encoding='utf-8')
    return works,bp,binding,repo


def enable(work,bp):
    w=json.loads(work.read_text(encoding='utf-8'))
    # Explicitly declare the evidence source root, not a traversal from @work.
    w['repositories'].append({'name':'boundary-inputs','path':str(bp.parent),'allowed_paths':[],'production_paths':[],'test_paths':[]})
    w['compilation']['runtime_boundary_binding']='@repo:boundary-inputs/Boundary.json'
    work.write_text(json.dumps(w),encoding='utf-8')


class RuntimeBoundaryTest(unittest.TestCase):
    def test_live_positive_and_missing_binding(self):
        with tempfile.TemporaryDirectory() as td:
            works,bp,binding,repo=fixture(Path(td))
            wp=works['producer']
            run,receipt=flow(wp,'conformance','--kind','implementation-conformance')
            data=json.loads((wp.parent/'.cat-flow/cache/implementation-obligations-evaluated.json').read_bytes())
            self.assertEqual(next(x for x in data['items'] if x['id']=='cross-process.boundary.producer.out.receiver')['status'],'inconclusive')
            enable(wp,bp)
            run,receipt=flow(wp,'conformance','--kind','implementation-conformance')
            self.assertEqual(receipt.get('status'),'inconclusive',(run.stdout,run.stderr))
            data=json.loads((wp.parent/'.cat-flow/cache/implementation-obligations-evaluated.json').read_bytes())
            passed=[x['id'] for x in data['items'] if x['category']=='cross-process' and x['status']=='passed']
            self.assertEqual(passed,['cross-process.boundary.producer.out.receiver'])
            evidence=Path(receipt['runtime_boundary_evidence']); obs=json.loads(evidence.read_bytes())
            self.assertEqual(len(obs['observations']),2)
            self.assertEqual({o['source_output']['fields']['output.flag'] for o in obs['observations']},{False,True})
            self.assertEqual(len({o['execution'] for o in obs['observations']}),2)
            p,w=work_file(wp)
            self.assertEqual(cat_flow.conformance_evidence_status(p,w,'implementation-conformance')['status'],'inconclusive')
            evidence.write_text('{}',encoding='utf-8')
            self.assertEqual(cat_flow.conformance_evidence_status(p,w,'implementation-conformance')['status'],'stale')
            enable(works['receiver'],bp)
            run,receipt=flow(works['receiver'],'conformance','--kind','implementation-conformance')
            self.assertEqual(receipt.get('status'),'inconclusive',(run.stdout,run.stderr))
            data=json.loads((works['receiver'].parent/'.cat-flow/cache/implementation-obligations-evaluated.json').read_bytes())
            self.assertEqual([x['id'] for x in data['items'] if x['category']=='cross-process' and x['status']=='passed'],['cross-process.boundary.receiver.in.producer'])

    def test_markdown_work_binding(self):
        with tempfile.TemporaryDirectory() as td:
            works,bp,binding,repo=fixture(Path(td));wp=works['producer']
            md=wp.with_suffix('.md')
            md.write_text(f"""---
cat_version: '0.2'
kind: work
id: producer.work
status: draft
process: producer
source_refs: ["synthetic-test-only"]
decision_ref: synthetic-test-only
refs: ["producer.tce"]
entry: confirmed-spec
mode: implementation
flow: spec-implementation
work_kind: implementation
parent: ''
depends_on: []
issue_ref: synthetic-test-only
project_entry_ref: synthetic-test-only
spec_status: confirmed
---
# Work
## Evidence
| URI |
| --- |
| synthetic-test-only |
## Scope
| Process IDs | Changed IDs | Preserved IDs |
| --- | --- | --- |
| producer | — | — |
## Repositories
| Name | Path | Allowed paths | Production paths | Test paths |
| --- | --- | --- | --- | --- |
| fixture | {repo.as_posix()} | *.py | *.py | — |
| boundary-inputs | {bp.parent.as_posix()} | — | — | — |
## Compilation
| Process | PI | TCE | Model | Obligations | Runtime boundary binding | Allow draft |
| --- | --- | --- | --- | --- | --- | --- |
| Process.md | In.md;Out.md | TCE.md | Model.json | Obligations.json | @repo:boundary-inputs/Boundary.json | false |
""",encoding='utf-8')
            self.assertEqual(work_file(md)[1]['compilation']['runtime_boundary_binding'],'@repo:boundary-inputs/Boundary.json')
            run,receipt=flow(md,'conformance','--kind','implementation-conformance')
            self.assertEqual(receipt.get('status'),'inconclusive',(run.stdout,run.stderr))
            self.assertEqual(json.loads(Path(receipt['runtime_boundary_evidence']).read_bytes())['status'],'passed')

    def test_live_negative_and_alternate(self):
        with tempfile.TemporaryDirectory() as td:
            works,bp,binding,repo=fixture(Path(td));wp=works['producer'];enable(wp,bp)
            evidence=wp.parent/'.cat-flow/cache/implementation-runtime-boundary.json'
            for variant in ('alternate','wrong-source','wrong-operation','wrong-process','wrong-receiver','wrong-execution','missing','fake-receipt','duplicate','wrong-type'):
                with self.subTest(variant=variant):
                    head=write_implementation(repo,variant)
                    for pid,ep in binding['endpoints'].items():
                        ep.update(head=head,script=dep(repo/(pid+'.py'),repo))
                    bp.write_text(json.dumps(binding),encoding='utf-8')
                    run,receipt=flow(wp,'conformance','--kind','implementation-conformance')
                    if variant=='alternate':
                        self.assertEqual(receipt.get('status'),'inconclusive',(run.stdout,run.stderr))
                        self.assertEqual(json.loads(Path(receipt['runtime_boundary_evidence']).read_bytes())['status'],'passed')
                    else:
                        self.assertEqual(receipt.get('status'),'blocked',(run.stdout,run.stderr))
                        self.assertIn('runtime boundary observation rejected',receipt.get('reason',''))
                        self.assertFalse(evidence.exists())

    def test_pinned_dependencies_and_submitted_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            works,bp,base,repo=fixture(Path(td));wp=works['producer'];enable(wp,bp)
            for variant in ('head','script','model','peer-source','operation','fake','same-endpoint','test-double','forged-model'):
                with self.subTest(variant=variant):
                    binding=json.loads(json.dumps(base))
                    if variant=='head':binding['endpoints']['receiver']['head']='0'*40
                    elif variant=='script':binding['endpoints']['receiver']['script']['sha256']='0'*64
                    elif variant=='model':binding['models']['receiver']['sha256']='0'*64
                    elif variant=='peer-source':binding['source_assemblies']['receiver']['process']['sha256']='0'*64
                    elif variant=='operation':binding['links'][0]['target_operation']='wrong'
                    elif variant=='fake':binding['receipt']={'status':'passed','covered_obligation_ids':['cross-process.boundary.producer.out.receiver']}
                    elif variant=='same-endpoint':binding['endpoints']['receiver']=binding['endpoints']['producer']
                    elif variant=='test-double':
                        w=json.loads(wp.read_bytes());w['repositories'][0]['test_paths']=['receiver.py'];wp.write_text(json.dumps(w),encoding='utf-8')
                    elif variant=='forged-model':
                        # Rehash a modified peer Model: a digest alone cannot
                        # substitute for independent Source correspondence.
                        path=bp.parent/binding['models']['receiver']['path']
                        model=json.loads(path.read_bytes());model['pi_operations'][0]['id']='forged'
                        path.write_text(json.dumps(model),encoding='utf-8');binding['models']['receiver']=dep(path,bp.parent)
                    bp.write_text(json.dumps(binding),encoding='utf-8')
                    run,receipt=flow(wp,'conformance','--kind','implementation-conformance')
                    self.assertEqual(receipt.get('status'),'blocked',(run.stdout,run.stderr))
                    self.assertFalse((wp.parent/'.cat-flow/cache/implementation-runtime-boundary.json').exists())
                    if variant=='test-double':
                        w=json.loads(wp.read_bytes());w['repositories'][0]['test_paths']=[];wp.write_text(json.dumps(w),encoding='utf-8')


if __name__=='__main__':unittest.main()
