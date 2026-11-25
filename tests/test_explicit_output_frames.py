"""Source-defined output activation, separate from the input evaluation cut."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'.cat-system/scripts'
sys.path.insert(0,str(SCRIPTS))
from cat_compile_v2 import Blocked, load, render_model_markdown, expand_cases, selection_vectors, emit_vitest, emit_junit
from cat_model_conformance import validate


def source(kind,ident,refs,body):
    return (f"---\ncat_version: '0.3'\nkind: {kind}\nid: {ident}\nstatus: confirmed\nprocess: frameprobe\n"
            'source_refs: ["synthetic-test-only"]\ndecision_ref: synthetic-test-only\n'
            f'refs: {json.dumps(refs)}\nsemantic_contract: markdown-v2\nlanguage: en\n---\n\n'+body+'\n')


def fixture(root, *, split=False, variant='positive'):
    p,pi,tce=(root/n for n in ('Process.md','PI.md','TCE.md'))
    triggers='| start | frameprobe.pi/request |'
    if split:triggers+='\n| terminal | frameprobe.pi/send |'
    p.write_text(source('process','frameprobe',['frameprobe.pi'],'''# Process
## Contract
Closed world: true
## Interfaces
| PI |
| --- |
| frameprobe.pi |
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
'''+triggers),encoding='utf-8')
    if split:
        fields='| input.deliver | receive | boolean | required |\n| output.payload | send | boolean | required |'
        operations='| request | accept | start |\n| send | provide | terminal |'
        presence=''
        frames='| start | deliver | 1 | send | zero-or-one |\n| start | skip | 1 | — | zero-or-one |\n| terminal | done | 1 | — | none |'
        behaviors='| deliver | start | `input.deliver` | 1 | `output.payload = true` |\n| skip | start | `not(input.deliver)` | 1 | — |\n| done | terminal | `true` | 1 | — |'
        if variant=='resend':behaviors=behaviors.replace('| done | terminal | `true` | 1 | — |','| done | terminal | `true` | 1 | `output.payload = true` |')
        if variant=='inactive-write':behaviors=behaviors.replace('| skip | start | `not(input.deliver)` | 1 | — |','| skip | start | `not(input.deliver)` | 1 | `output.payload = false` |')
        if variant=='missing-output':behaviors=behaviors.replace('`output.payload = true`','—')
        if variant=='missing-cut':frames='\n'.join(frames.splitlines()[:2])
        if variant=='duplicate-cut':frames=frames.replace('| terminal | done | 1 | — | none |','| terminal | done | 1 | send | one |')
    else:
        fields='| input.good | receive | boolean | required |\n| output.value | send | boolean | required |\n| output.error | send | boolean | required |'
        operations='| request | accept | start |\n| ok | provide | start |\n| fail | provide | start |'
        presence='''## Operation presence
| Operation | Field | Presence |
| --- | --- | --- |
| ok | output.value | required |
| ok | output.error | absent |
| fail | output.value | absent |
| fail | output.error | required |
'''
        frames='| start | success | 1 | ok | one |\n| start | failure | 1 | fail | one |'
        behaviors='| success | start | `input.good` | 1 | `output.value = true` |\n| failure | start | `not(input.good)` | 1 | `output.error = true` |'
        if variant=='both':behaviors=behaviors.replace('output.value = true','output.value = true; output.error = true')
        if variant=='wrong-owner':frames=frames.replace('| 1 | ok |','| 1 | other |')
        if variant=='missing-outcome':frames=frames.splitlines()[0]
        if variant=='duplicate-outcome':frames+='\n'+frames.splitlines()[0]
        if variant=='none':frames=frames.replace('| 1 | ok |','| 1 | — |')
        if variant=='swapped':frames=frames.replace('| ok |','| temp |').replace('| fail |','| ok |').replace('| temp |','| fail |')
        if variant=='nondeterministic':
            behaviors='| success | start | `true` | 1 | `output.value = true` |\n| success | start | `true` | 2 | `output.error = true` |'
            frames='| start | success | 1 | ok | one |\n| start | success | 2 | fail | one |'
    frame_section='\n## Output frames\n| Trigger | Behavior | Outcome | Operation | Mode |\n| --- | --- | --- | --- | --- |\n'+frames+'\n' if variant!='legacy' else ''
    pi.write_text(source('pi','frameprobe.pi',['frameprobe'],'''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| caller | bidirectional |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
'''+fields+'''\n## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
'''+operations+'\n'+presence+frame_section+'\n## Constraints\n| Expression |\n| --- |'),encoding='utf-8')
    tce.write_text(source('tce','frameprobe.tce',['frameprobe.pi'],'''# TCE
Coverage requirement: closed
## Behaviors
| ID | Trigger | Condition | Outcome | Effects |
| --- | --- | --- | --- | --- |\n'''+behaviors),encoding='utf-8')
    work={'schema':'cat-work/v1','id':'frameprobe.work','entry':'confirmed-spec','mode':'implementation','flow':'spec-implementation','work_kind':'implementation','parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry','normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':['frameprobe.tce']},'scope':{'process_ids':['frameprobe'],'changed_ids':[],'preserved_ids':[]},'technologies':['Vitest'],'repositories':[],'checks':[],'gates':[],'compilation':{'schema':'cat-compile/v2','process':p.name,'pi':pi.name,'tce':tce.name,'model':'Model.json','vectors':'Vectors.json','queue':'Queue.json','binding':'Binding.json','tests_output':'Generated.test.ts','allow_draft':False,'allow_partial':True}}
    (root/'Work.json').write_text(json.dumps(work),encoding='utf-8')
    (root/'Binding.json').write_text(json.dumps({'schema':'cat-test-driver/v2','process':'frameprobe','driver':'./driver','output_operation_transport':'js-driver-provides/v1'}),encoding='utf-8')
    return p,pi,tce


def flow(root,*args):
    run=subprocess.run([sys.executable,str(SCRIPTS/'cat_flow.py'),args[0],'--work',str(root/'Work.json'),*args[1:]],capture_output=True,text=True,encoding='utf-8',timeout=30)
    return run,json.loads(run.stdout)


class OutputFramesTests(unittest.TestCase):
    def test_source_and_frame_negatives(self):
        cases=[(False,'positive','passed'),(True,'positive','passed'),(False,'legacy','inconclusive'),
               (False,'both','inconclusive'),(False,'swapped','inconclusive'),(True,'resend','inconclusive'),
               (True,'inactive-write','inconclusive'),(True,'missing-output','inconclusive'),
               (False,'wrong-owner','blocked'),(False,'missing-outcome','blocked'),(False,'duplicate-outcome','blocked'),
               (False,'none','blocked'),(True,'missing-cut','blocked'),(True,'duplicate-cut','blocked'),
               (False,'nondeterministic','passed')]
        for split,variant,expected in cases:
            with self.subTest(split=split,variant=variant),tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,tce=fixture(root,split=split,variant=variant)
                run,receipt=flow(root,'conformance','--kind','process-closure')
                self.assertEqual(receipt['status'],expected,(run.stdout,run.stderr))
                if expected=='blocked':continue
                model=load(p,pi,tce,allow_partial=True)
                for suffix,body in [('.json',json.dumps(model)),('.md',render_model_markdown(model))]:
                    path=root/('Independent'+suffix);path.write_text(body,encoding='utf-8')
                    self.assertEqual(validate(p,pi,tce,path)['status'],'passed')
                if variant=='nondeterministic':
                    self.assertEqual(len(model['output_frames']),2)
                    vectors=selection_vectors(model)
                    cases=expand_cases(model,vectors)
                    self.assertEqual(cases[0]['output_operations'],['fail','ok'])
                    self.assertEqual([a['output_operations'] for a in cases[0]['allowed']],[['ok'],['fail']])
                elif expected=='passed':
                    path=root/'Model.json';model['output_frames'][0]['operation']='forged'
                    path.write_text(json.dumps(model),encoding='utf-8')
                    self.assertNotEqual(validate(p,pi,tce,path)['status'],'passed')

    def test_generation_and_empty_transport(self):
        for split,variant in ((False,'positive'),(True,'positive'),(False,'nondeterministic')):
            with self.subTest(split=split,variant=variant),tempfile.TemporaryDirectory() as td:
                root=Path(td);p,pi,tce=fixture(root,split=split,variant=variant)
                for kind in ('model','vectors','queue','tests'):
                    for check in ([],['--check']):
                        run,receipt=flow(root,'compile','--kind',kind,*check)
                        self.assertEqual(receipt['status'],'passed',(kind,run.stdout,run.stderr))
                model=load(p,pi,tce)
                vectors=selection_vectors(model)
                cases=expand_cases(model,vectors)
                if split:self.assertEqual({c['source_tce']:c['output_operations'] for c in cases},{'deliver':['send'],'skip':[],'done':[]})
                elif variant=='nondeterministic':self.assertEqual({c['source_tce']:c['output_operations'] for c in cases},{'success':['fail','ok']})
                else:self.assertEqual({c['source_tce']:c['output_operations'] for c in cases},{'success':['ok'],'failure':['fail']})
                # Renderer must validate the actual observed empty operation inventory.
                code=emit_vitest(model,vectors,root/'Binding.json')
                if split:self.assertIn('observedOperationIDs(observed, inventory)',code)
                # JUnit binding is separate; both renderers preserve the same case semantics.
                jbinding=root/'JUnitBinding.json'
                jbinding.write_text(json.dumps({'schema':'cat-junit-driver-binding/v1','process':'frameprobe','test_package':'probe','test_class':'GeneratedTest','driver_class':'probe.Driver','output_operation_transport':'java-driver-provides/v1'}),encoding='utf-8')
                java=emit_junit(model,vectors,jbinding)
                self.assertIn('selectedFields(actualOutput',java)
                # Real smoke fixture generated via the Vitest binding and full vectors.
                fixture_name='split' if split else 'alternatives' if variant=='nondeterministic' else 'exclusive'
                smoke=os.environ.get('CAT_EXPLICIT_FRAMES_VITEST_SMOKE_DIR')
                if smoke:
                    dest=Path(smoke)/fixture_name;dest.mkdir(parents=True,exist_ok=True)
                    (dest/'Generated.test.ts').write_text(code,encoding='utf-8')
                    (dest/'driver.ts').write_text('''export function createDriver() {
  return { outputOperationTransport: 'js-driver-provides/v1', async prepare() {}, async observeState() { return {}; },
    async triggerProvidedOperations(_inventory: string[], trigger: string, input: Record<string,unknown>) {
      const mode=process.env.CAT_FRAME_MODE;
      let actual: Record<string,unknown>;
      if ('input.good' in input) {
        const choice = FIXTURE === 'alternatives' ? mode !== 'alternate' : input['input.good'];
        actual=choice ? {'ok':{'output.value':true}} : {'fail':{'output.error':true}};
        if(mode==='both-active') actual={'ok':{'output.value':true},'fail':{'output.error':true}};
        if(mode==='mixed') actual={'ok':{'output.error':true}};
        if(mode==='both') actual={...actual,'extra':{}};
        if(mode==='wrong') actual=input['input.good'] ? {'fail':{'output.value':true}} : {'ok':{'output.error':true}};
      } else {
        actual=trigger==='start'&&input['input.deliver'] ? {'send':{'output.payload':true}} : {};
        if(mode==='resend'&&trigger==='terminal') actual={'send':{'output.payload':true}};
        if(mode==='inactive'&&trigger==='start'&&!input['input.deliver']) actual={'send':{}};
      }
      return actual;
    }
  };
}
'''.replace('FIXTURE',json.dumps(fixture_name)),encoding='utf-8')
                junit_smoke=os.environ.get('CAT_EXPLICIT_FRAMES_JUNIT_SMOKE_DIR')
                if junit_smoke:
                    dest=Path(junit_smoke)/fixture_name/'probe';dest.mkdir(parents=True,exist_ok=True)
                    (dest/'Generated.java').write_text(java,encoding='utf-8')
                    (dest/'Driver.java').write_text('''package probe;
import java.util.*;
public class Driver {
    public void prepare(Map<String,Object> state, Map<String,Object> input) {}
    public Map<String,Object> observeState() { return Map.of(); }
    public Object triggerProvidedOperations(List<String> inventory, String trigger, Map<String,Object> input) {
        String mode=System.getenv("CAT_FRAME_MODE");
        if (input.containsKey("input.good")) {
            boolean choice=FIXTURE.equals("alternatives") ? !"alternate".equals(mode) : (Boolean)input.get("input.good");
            if ("both-active".equals(mode)) return Map.of("ok",Map.of("output.value",true),"fail",Map.of("output.error",true));
            if ("both".equals(mode)) return Map.of("extra",Map.of());
            if ("mixed".equals(mode)) return Map.of("ok",Map.of("output.error",true));
            if ("wrong".equals(mode)) return choice?Map.of("fail",Map.of("output.value",true)):Map.of("ok",Map.of("output.error",true));
            return choice?Map.of("ok",Map.of("output.value",true)):Map.of("fail",Map.of("output.error",true));
        }
        if ("resend".equals(mode)&&trigger.equals("terminal")) return Map.of("send",Map.of("output.payload",true));
        if (trigger.equals("start")) {
            if (Boolean.TRUE.equals(input.get("input.deliver"))) return Map.of("send",Map.of("output.payload",true));
            if ("inactive".equals(mode)) return Map.of("send",Map.of());
        }
        return Map.of();
    }
}
'''.replace('FIXTURE',json.dumps(fixture_name)),encoding='utf-8')


if __name__=='__main__':unittest.main()
