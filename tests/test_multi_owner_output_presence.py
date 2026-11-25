"""Fresh output frames belong to PI owners, not the number of providers."""
import json
from copy import deepcopy
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_scoped_output_presence import fixture, artifact, ROOT
from cat_compile_v2 import load, render_model_markdown, selection_vectors, expand_cases, make_queue, validate_queue, emit_vitest, emit_junit, D, Blocked
from cat_model_conformance import validate


def build(root, variant):
    p, pi, tce, rule = fixture(root)
    other = root/'OtherPI.md'
    p.write_text(p.read_text().replace('refs: ["probe.presence.pi"]','refs: ["probe.presence.pi", "probe.other.pi"]').replace('| probe.presence.pi |','| probe.presence.pi |\n| probe.other.pi |'), encoding='utf8')
    other.write_text(artifact('pi','probe.other.pi',['probe.presence'], '''# PI
## Boundary
| Peer process | Direction |
| --- | --- |
| probe.receiver | outgoing |
## Fields
| ID | Direction | Domain | Presence |
| --- | --- | --- | --- |
| output.notice | send | boolean | optional |
## Operations
| ID | Direction | Trigger |
| --- | --- | --- |
| publish | provide | first |
## Constraints
| Expression |
| --- |
## Operation presence
| Operation | Field | Presence |
| --- | --- | --- |
| publish | output.notice | required |''').replace('| probe.receiver | outgoing |','| probe.receiver | bidirectional |'),encoding='utf8')
    tce.write_text(tce.read_text().replace('refs: ["probe.presence.pi"]','refs: ["probe.presence.pi", "probe.other.pi"]').replace('output.answer = true`','output.answer = true; output.notice = false`'),encoding='utf8')
    rule.write_text(rule.read_text()+ '| notification.presence | fresh-output probe.other.pi publish first output.notice | @cat:declared-outcome-output-presence/v1 | cat:intrinsic-model/v1 |\n',encoding='utf8')
    if variant=='missing':tce.write_text(tce.read_text().replace('; output.notice = false',''),encoding='utf8')
    if variant=='inactive':tce.write_text(tce.read_text().replace('state.anchor = state.anchor`','state.anchor = state.anchor; output.notice = true`'),encoding='utf8')
    if variant=='ambiguous':other.write_text(other.read_text().replace('| publish | provide | first |','| publish | provide | first |\n| extra | provide | first |'),encoding='utf8')
    if variant=='unscoped':other.write_text(other.read_text().replace('| publish | provide | first |','| publish | provide | |'),encoding='utf8')
    if variant=='wrong_owner':rule.write_text(rule.read_text().replace('fresh-output probe.other.pi publish','fresh-output probe.presence.pi publish'),encoding='utf8')
    if variant=='absent':other.write_text(other.read_text().replace('output.notice | required','output.notice | absent'),encoding='utf8')
    if variant=='paired':
        tce.write_text(tce.read_text().replace('| second.reply |',
            '| first.reply | first | `true` | 2 | `output.answer = false; output.notice = true` |\n| second.reply |'),encoding='utf8')
    # Reuse the ordinary Work schema, with both owned PI inputs.
    return p,[pi,other],tce,rule


def run_gate(root):
    work={'schema':'cat-work/v1','id':'probe.presence.work','entry':'confirmed-spec',
          'mode':'implementation','flow':'spec-implementation','work_kind':'implementation',
          'parent':'','depends_on':[],'issue_ref':'spec-entry','project_entry_ref':'project-entry',
          'normative':[{'uri':'spec'}],'evidence':[{'uri':'evidence'}],
          'specification':{'status':'confirmed','decision_ref':'synthetic-test-only','artifact_refs':['probe.presence.tce']},
          'scope':{'process_ids':['probe.presence'],'changed_ids':[],'preserved_ids':[]},
          'technologies':[],'repositories':[],'checks':[],'gates':[],
          'compilation':{'schema':'cat-compile/v2','process':'Process.md','pi':'PI.md',
                         'pis':['PI.md','OtherPI.md'],'tce':'TCE.md','domain_specs':['Rule.md'],
                         'model':'Model.json','allow_draft':False,'allow_partial':True}}
    path=root/'Work.json'
    path.write_text(json.dumps(work),encoding='utf8')
    return subprocess.run([sys.executable,str(ROOT/'.cat-system/scripts/cat_flow.py'),'conformance','--work',str(path),'--kind','process-closure'],capture_output=True,text=True,timeout=75)


class MultiOwnerPresenceTests(unittest.TestCase):
    def test_distinct_owner_frames(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pis,tce,rule=build(root,'positive')
            model=load(p,pis,tce,domain_specs=[rule],allow_partial=True)
            self.assertEqual(model['presence_unproven'],[])
            self.assertEqual(model['unverified_rule_ids'],[])
            for name,content in [('Model.json',json.dumps(model)),('Model.md',render_model_markdown(model))]:
                f=root/name;f.write_text(content,encoding='utf8');self.assertEqual(validate(p,pis,tce,f,domain_specs=[rule])['status'],'passed')
            result=run_gate(root);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['status'],'passed')
            vectors=selection_vectors(model)
            self.assertEqual(vectors,selection_vectors(model))
            first,second=vectors['cases']
            self.assertEqual(first['output_operations'],['publish','reply_first'])
            self.assertNotIn('output_operation',first)
            self.assertEqual(second['output_operation'],'reply_second')
            expanded=expand_cases(model,vectors)
            self.assertEqual(expanded[0]['allowed'][0]['output'],{'output.answer':True,'output.notice':False})
            self.assertEqual(expanded[1]['allowed'][0]['output'],{})
            q=make_queue(model,vectors,b'model',b'vectors')
            validate_queue(q,model,vectors,b'model',b'vectors')
            self.assertEqual(len(q['items']),2)
            # The set of provider operations is bound to the entire execution.
            for ops in ([],['publish'],['publish','publish'],['publish','reply_second'],['publish','reply_first','reply_second'],['publish','not-declared']):
                with self.subTest(ops=ops):
                    wrong=deepcopy(vectors);wrong['cases'][0]['output_operations']=ops
                    with self.assertRaises(Blocked):expand_cases(model,wrong)
            for explicit in ({},{'output_operation':'reply_first'},{'output_operation':'reply_first','output_operations':['publish','reply_first']}):
                wrong=deepcopy(vectors);wrong['cases'][0].pop('output_operations');wrong['cases'][0].update(explicit)
                with self.assertRaises(Blocked):expand_cases(model,wrong)
            # Ordering of the vector list is not an implementation ordering constraint.
            reordered=deepcopy(vectors);reordered['cases'][0]['output_operations'].reverse()
            self.assertEqual(expand_cases(model,reordered),expanded)
            model['operation_presence'][0]['presence']='absent'
            f=root/'forged.json';f.write_text(json.dumps(model),encoding='utf8')
            self.assertNotEqual(validate(p,pis,tce,f,domain_specs=[rule])['status'],'passed')
    def test_negative_frames(self):
        for variant in ('missing','inactive','ambiguous','unscoped','wrong_owner','absent'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as td:
                root=Path(td);build(root,variant);result=run_gate(root)
                if result.returncode==0:self.assertNotEqual(json.loads(result.stdout)['status'],'passed')
                else:self.assertEqual(result.returncode,2)

    def test_render_multi_owner_result(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pis,tce,rule=build(root,'paired')
            gate=run_gate(root)
            self.assertEqual(gate.returncode,0,gate.stderr)
            self.assertEqual(json.loads(gate.stdout)['status'],'passed')
            model=load(p,pis,tce,domain_specs=[rule])
            vectors=selection_vectors(model)
            cases=expand_cases(model,vectors)
            self.assertEqual([out['output'] for out in cases[0]['allowed']],
                [{'output.answer':True,'output.notice':False},{'output.answer':False,'output.notice':True}])
            b=root/'Binding.json'
            binding={'schema':D,'process':model['process'],'driver':'./driver'}
            for transport in (None,'js-driver-provide/v1','unrecognized'):
                candidate=dict(binding)
                if transport is not None:candidate['output_operation_transport']=transport
                b.write_text(json.dumps(candidate),encoding='utf8')
                with self.assertRaises(Blocked):emit_vitest(model,vectors,b)
            binding['output_operation_transport']='js-driver-provides/v1'
            b.write_text(json.dumps(binding),encoding='utf8')
            generated=emit_vitest(model,vectors,b)
            self.assertEqual(generated,emit_vitest(model,vectors,b))
            self.assertEqual(generated.count('.triggerProvidedOperations('),2)
            self.assertIn('(["publish","reply_first"],"first",input)',generated)
            self.assertIn('(["reply_second"],"second",input)',generated)
            self.assertIn('{"publish":["output.notice"],"reply_first":["output.answer"]}',generated)
            self.assertNotIn('await driver.trigger(',generated)
            junit=root/'JUnit.json'
            junit.write_text(json.dumps({'schema':'cat-junit-driver-binding/v1','process':model['process'],
                'test_package':'probe','test_class':'ProbeTest','driver_class':'ProbeDriver'}),encoding='utf8')
            with self.assertRaises(Blocked):emit_junit(model,vectors,junit)
            # Real Vitest smoke is executed by the generated-test acceptance workflow.
            destination=os.getenv('CAT_MULTI_OWNER_VITEST_SMOKE_DIR')
            if destination:
                target=Path(destination);target.mkdir(parents=True,exist_ok=True)
                (target/'presence.test.ts').write_text(generated,encoding='utf8')
                (target/'driver.ts').write_text(MULTI_DRIVER,encoding='utf8')
            node=shutil.which('node')
            if not node:return  # Python transport checks still run without Node.
            version=subprocess.run([node,'--version'],capture_output=True,text=True,check=True)
            if int(version.stdout.strip().lstrip('v').split('.')[0])<22:return
            helpers=generated[generated.index('function sameCATSet('):generated.index('\ndescribe(')]
            probe=root/'helper.mts'
            probe.write_text('import {isDeepStrictEqual} from "node:util";\n'+helpers+'\n'+MULTI_PROBE,encoding='utf8')
            result=subprocess.run([node,'--experimental-strip-types',str(probe)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)


MULTI_DRIVER = """export function createDriver() {
  let state: Record<string,unknown> = {};
  let called = false;
  return {
    outputOperationTransport: 'js-driver-provides/v1',
    async prepare(pre: Record<string,unknown>, _input: Record<string,unknown>) { state = {...pre}; called = false; },
    async observeState() { return {...state}; },
    async triggerProvidedOperations(operations: string[], trigger: string, _input: Record<string,unknown>) {
      if (called) throw new Error('Trigger executed twice');
      called = true;
      const mode = process.env.CAT_MULTI_OWNER_MODE || 'direct';
      if (trigger === 'second') {
        if (operations.length !== 1 || operations[0] !== 'reply_second') throw new Error('Wrong second scope');
        return {reply_second: mode === 'absent' ? {'output.answer': false} : {}};
      }
      if (operations.length !== 2 || !operations.includes('publish') || !operations.includes('reply_first')) throw new Error('Wrong first scope');
      if (mode === 'missing') return {reply_first: {'output.answer': true}};
      if (mode === 'extra') return {publish: {'output.notice': false}, reply_first: {'output.answer': true}, unrelated: {}};
      if (mode === 'wrong-owner') return {publish: {'output.answer': true}, reply_first: {'output.notice': false}};
      if (mode === 'wrong-pair') return {publish: {'output.notice': true}, reply_first: {'output.answer': true}};
      if (mode === 'missing-field') return {publish: {}, reply_first: {'output.answer': true}};
      if (mode === 'alternate') return {reply_first: {'output.answer': false}, publish: {'output.notice': true}};
      return {publish: {'output.notice': false}, reply_first: {'output.answer': true}};
    },
  };
}
"""

MULTI_PROBE = """
const fields = {publish:['output.notice'], reply_first:['output.answer']};
const after = {'state.anchor':true};
const allowed = [
    {state:after,output:{'output.answer':true,'output.notice':false}},
    {state:after,output:{'output.answer':false,'output.notice':true}}
];
const accepts = (observed: unknown) => {
  try { return accept(after,flattenProvidedOperations(observed,fields),allowed,['state.anchor'],[],[]); }
  catch { return false; }
};
if (!accepts({publish:{'output.notice':false},reply_first:{'output.answer':true}})) process.exit(1);
if (!accepts({reply_first:{'output.answer':false},publish:{'output.notice':true}})) process.exit(2);
for (const invalid of [
  {publish:{'output.notice':true},reply_first:{'output.answer':true}},
  {publish:{'output.answer':true},reply_first:{'output.notice':false}},
  {publish:{},reply_first:{'output.answer':true}},
  {reply_first:{'output.answer':true}},
  {publish:{'output.notice':false},reply_first:{'output.answer':true},extra:{}},
  {publish:{'output.notice':false},other:{'output.answer':true}},
  {publish:null,reply_first:{'output.answer':true}},
  {'output.notice':false,'output.answer':true}
]) if (accepts(invalid)) process.exit(3);
const absent = [{state:after,output:{}}];
if (!accept(after,flattenProvidedOperations({reply_second:{}},{reply_second:['output.answer']}),absent,['state.anchor'],[],[])) process.exit(4);
if (accept(after,flattenProvidedOperations({reply_second:{'output.answer':false}},{reply_second:['output.answer']}),absent,['state.anchor'],[],[])) process.exit(5);
"""
