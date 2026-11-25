"""Technology adapters must preserve separate, source-bound observation coordinates."""
import json
from copy import deepcopy
import os
import tempfile
import unittest
from pathlib import Path
from test_observed_structural_relations import source, OBS, gate, load, validate
from test_multi_owner_output_presence import build, run_gate
from cat_compile_v2 import selection_vectors, expand_cases, emit_vitest, emit_junit, Blocked


def bindings(model):
    return ({'schema':'cat-test-driver/v2','process':model['process'],'driver':'./driver'},
            {'schema':'cat-junit-driver-binding/v1','process':model['process'],
             'test_package':'probe','test_class':'ProbeTest','driver_class':'probe.ProbeDriver'})


def render(root, model, vectors, binding, renderer):
    path=root/'Binding.json';path.write_text(json.dumps(binding),encoding='utf8')
    return renderer(model,vectors,path)


class TransportTests(unittest.TestCase):
    def test_observation_transport(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pi,t,r=source(root,OBS,'branch')
            result=gate(root);self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'passed')
            m=load(p,pi,t,domain_specs=[r]);v=selection_vectors(m)
            self.assertEqual({c['observations']['observation.received'] for c in v['cases']},{True,False})
            js,java=bindings(m)
            for binding,renderer,mode in ((js,emit_vitest,'js-driver-observed/v1'),(java,emit_junit,'java-driver-observed/v1')):
                with self.subTest(mode=mode):
                    with self.assertRaises(Blocked):render(root,m,v,binding,renderer)
                    with self.assertRaises(Blocked):render(root,m,v,{**binding,'observation_transport':'unknown'},renderer)
                    new={**binding,'observation_transport':mode}
                    code=render(root,m,v,new,renderer)
                    self.assertEqual(code,render(root,m,v,new,renderer))
                    self.assertIn('prepareObservations',code)
                    self.assertIn('triggerObserved',code)
                    self.assertIn('synthetic.received-result',code)
                    self.assertIn('trigger-entry',code)
                    self.assertIn('CAT observed coordinates differ',code)
                    self.assertNotIn('driver.trigger(',code)
                    if renderer is emit_junit:
                        with self.assertRaises(Blocked):render(root,m,v,{**new,'capability_scope':{'kind':'pi-only-unverified','observations':['observation.received'],'actions':[]}},renderer)
                    dest=os.getenv('CAT_OBS_VITEST_SMOKE_DIR' if renderer is emit_vitest else 'CAT_OBS_JUNIT_SMOKE_DIR')
                    if dest:
                        d=Path(dest);d.mkdir(parents=True,exist_ok=True)
                        (d/('observation.test.ts' if renderer is emit_vitest else 'Generated.java')).write_text(code,encoding='utf8')
                        (d/('driver.ts' if renderer is emit_vitest else 'ProbeDriver.java')).write_text(JS_DRIVER if renderer is emit_vitest else JAVA_OBS_DRIVER,encoding='utf8')

    def test_combined_observation_and_owner_frames(self):
        # A state observation relation needs no single-provider assumption;
        # its execution may also produce multiple owner-scoped outputs.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pis,t,r=build(root,'paired')
            scope={'trigger':'first','pi':'probe.presence.pi','operation':'request_first',
                   'peer':'probe.caller','cut':'trigger-entry','source':'synthetic.received-result'}
            p.write_text(p.read_text(encoding='utf8').replace(
                '| ID | Source | Domain |\n| --- | --- | --- |',
                '| ID | Source | Domain | Available on |\n| --- | --- | --- | --- |\n| observation.received | same-execution-observation '+json.dumps(scope,separators=(',',':'))+' | boolean | first |'),encoding='utf8')
            t.write_text(t.read_text(encoding='utf8').replace('output.answer = true; output.notice = false',
                'state.anchor = observation.received; output.answer = true; output.notice = false').replace('output.answer = false; output.notice = true',
                'state.anchor = observation.received; output.answer = false; output.notice = true'),encoding='utf8')
            relation={k:scope[k] for k in ('trigger','pi','operation','peer')}
            relation.update(when='true',fields=['state.anchor'],relation='after.state.anchor == observation.received',observations=['observation.received'])
            r.write_text(r.read_text(encoding='utf8')+'| relation.observation | observed-transition-relation '+json.dumps(relation,separators=(',',':'))+' | @cat:observed-transition-relation/v1 | cat:intrinsic-model/v1 |\n',encoding='utf8')
            result=run_gate(root);self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'passed')
            m=load(p,pis,t,domain_specs=[r]);v=selection_vectors(m)
            self.assertIn('observations',v['cases'][0]);self.assertNotIn('observations',v['cases'][1])
            js,java=bindings(m)
            for binding,renderer,obs,frames in ((js,emit_vitest,'js-driver-observed/v1','js-driver-provides/v1'),(java,emit_junit,'java-driver-observed/v1','java-driver-provides/v1')):
                with self.subTest(frames=frames):
                    binding['observation_transport']=obs
                    with self.assertRaises(Blocked):render(root,m,v,binding,renderer)
                    binding['output_operation_transport']=frames
                    code=render(root,m,v,binding,renderer)
                    self.assertEqual(code,render(root,m,v,binding,renderer))
                    self.assertIn('triggerObserved',code)
                    self.assertIn('triggerProvidedOperations',code)
                    self.assertIn('flattenProvidedOperations(actualOutput,',code)
                    for mutation in ('missing-inventory','wrong-source','unproved','action'):
                        bad=deepcopy(m)
                        if mutation=='missing-inventory':bad['fields'].append({'id':'observation.extra','role':'observation','domain':{'type':'boolean'},'source':'unbound'})
                        elif mutation=='wrong-source':next(f for f in bad['fields'] if f['id']=='observation.received')['source']='unbound'
                        elif mutation=='unproved':bad['intrinsic_rule_proofs']=[]
                        elif mutation=='action':bad['fields'].append({'id':'action.extra','role':'action','domain':{'type':'boolean'}})
                        with self.subTest(mutation=mutation),self.assertRaises(Blocked):render(root,bad,v,binding,renderer)
                    dest=os.getenv('CAT_COMBINED_VITEST_SMOKE_DIR' if renderer is emit_vitest else 'CAT_COMBINED_JUNIT_SMOKE_DIR')
                    if dest:
                        d=Path(dest);d.mkdir(parents=True,exist_ok=True)
                        (d/('combined.test.ts' if renderer is emit_vitest else 'Generated.java')).write_text(code,encoding='utf8')
                        (d/('driver.ts' if renderer is emit_vitest else 'ProbeDriver.java')).write_text(JS_COMBINED_DRIVER if renderer is emit_vitest else JAVA_COMBINED_DRIVER,encoding='utf8')

    def test_junit_multi_owner_transport(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,pis,t,r=build(root,'paired')
            result=run_gate(root);self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'passed')
            m=load(p,pis,t,domain_specs=[r]);v=selection_vectors(m)
            _,binding=bindings(m)
            with self.assertRaises(Blocked):render(root,m,v,binding,emit_junit)
            binding['output_operation_transport']='java-driver-provides/v1'
            code=render(root,m,v,binding,emit_junit)
            self.assertEqual(code,render(root,m,v,binding,emit_junit))
            self.assertIn('flattenProvidedOperations',code)
            self.assertIn('triggerProvidedOperations',code)
            self.assertIn('reply_second',code)
            self.assertNotIn('driver.trigger(',code)
            dest=os.getenv('CAT_MULTI_JUNIT_SMOKE_DIR')
            if dest:
                d=Path(dest);d.mkdir(parents=True,exist_ok=True)
                (d/'Generated.java').write_text(code,encoding='utf8')
                (d/'ProbeDriver.java').write_text(JAVA_MULTI_DRIVER,encoding='utf8')


JS_DRIVER='''export function createDriver() {
  let state: Record<string,unknown> = {}, environment = false, called = false;
  return {
    observationTransport: 'js-driver-observed/v1',
    async prepare(pre: Record<string,unknown>, input: Record<string,unknown>) {
      if ('observation.received' in input) throw new Error('Observation leaked into caller input');
      state = {...pre}; called = false;
    },
    async observeState() { return {...state}; },
    async prepareObservations(scope: Record<string,any>, values: Record<string,unknown>) {
      if (scope['observation.received'].source !== 'synthetic.received-result' || scope['observation.received'].cut !== 'trigger-entry') throw new Error('Wrong scope');
      environment = values['observation.received'] === true;
    },
    async triggerObserved(operations: string[], trigger: string, input: Record<string,unknown>) {
      if (called || operations.length !== 0 || trigger !== 'compare' || 'observation.received' in input) throw new Error('Wrong execution scope');
      called = true;
      const mode = process.env.CAT_OBS_MODE || 'direct';
      // Independent controlled source read, not the expected oracle.
      const actual = mode === 'wrong-observation' ? !environment : environment;
      const observations = mode === 'missing' ? {} : mode === 'extra' ? {'observation.received': actual, extra: true} : {'observation.received': actual};
      return {observations, output: {'output.answer': mode === 'wrong-output' ? !actual : actual}};
    }
  };
}
'''

JAVA_OBS_DRIVER='''package probe;
import java.util.*;
public class ProbeDriver {
    private Map<String,Object> state;
    private boolean environment, called;
    public void prepare(Map<String,Object> pre, Map<String,Object> input) {
        if (input.containsKey("observation.received")) throw new AssertionError("Observation leaked into caller input");
        state = new HashMap<>(pre); called = false;
    }
    public Map<String,Object> observeState() { return new HashMap<>(state); }
    public void prepareObservations(Map<String,Map<String,String>> scope, Map<String,Object> values) {
        if (!scope.get("observation.received").get("source").equals("synthetic.received-result") || !scope.get("observation.received").get("cut").equals("trigger-entry")) throw new AssertionError("Wrong scope");
        environment = (Boolean)values.get("observation.received");
    }
    public Map<String,Object> triggerObserved(List<String> operations, String trigger, Map<String,Object> input) {
        if (called || !operations.isEmpty() || !trigger.equals("compare") || input.containsKey("observation.received")) throw new AssertionError("Wrong execution scope");
        called = true;
        String mode = System.getenv().getOrDefault("CAT_OBS_MODE", "direct");
        boolean actual = mode.equals("wrong-observation") ? !environment : environment;
        Map<String,Object> observed = mode.equals("missing") ? Map.of() : mode.equals("extra") ? Map.of("observation.received",actual,"extra",true) : Map.of("observation.received",actual);
        return Map.of("observations",observed,"output",Map.of("output.answer",mode.equals("wrong-output") ? !actual : actual));
    }
}
'''

JAVA_MULTI_DRIVER='''package probe;
import java.util.*;
public class ProbeDriver {
    private Map<String,Object> state;
    private boolean called;
    public void prepare(Map<String,Object> pre, Map<String,Object> input) { state = new HashMap<>(pre); called = false; }
    public Map<String,Object> observeState() { return new HashMap<>(state); }
    public Map<String,Map<String,Object>> triggerProvidedOperations(List<String> operations, String trigger, Map<String,Object> input) {
        if (called) throw new AssertionError("Trigger executed twice"); called = true;
        String mode = System.getenv().getOrDefault("CAT_MULTI_OWNER_MODE","direct");
        if (trigger.equals("second")) {
            if (!operations.equals(List.of("reply_second"))) throw new AssertionError("Wrong second scope");
            return Map.of("reply_second",mode.equals("absent") ? Map.of("output.answer",false) : Map.of());
        }
        if (!new HashSet<>(operations).equals(Set.of("publish","reply_first"))) throw new AssertionError("Wrong first scope");
        return switch (mode) {
            case "missing" -> Map.of("reply_first",Map.of("output.answer",true));
            case "extra" -> Map.of("publish",Map.of("output.notice",false),"reply_first",Map.of("output.answer",true),"unrelated",Map.of());
            case "wrong-owner" -> Map.of("publish",Map.of("output.answer",true),"reply_first",Map.of("output.notice",false));
            case "wrong-pair" -> Map.of("publish",Map.of("output.notice",true),"reply_first",Map.of("output.answer",true));
            case "missing-field" -> Map.of("publish",Map.of(),"reply_first",Map.of("output.answer",true));
            case "alternate" -> Map.of("reply_first",Map.of("output.answer",false),"publish",Map.of("output.notice",true));
            default -> Map.of("publish",Map.of("output.notice",false),"reply_first",Map.of("output.answer",true));
        };
    }
}
'''

JS_COMBINED_DRIVER = """export function createDriver() {
  let state: Record<string,unknown> = {}, environment = false, called = false;
  const frames = (operations: string[], trigger: string, input: Record<string,unknown>) => {
    if (called || 'observation.received' in input) throw new Error('Wrong execution');
    called = true;
    const mode = process.env.CAT_COMBINED_MODE || 'direct';
    if (trigger === 'second') {
      if (operations.length !== 1 || operations[0] !== 'reply_second') throw new Error('Wrong second scope');
      return {reply_second: {}};
    }
    if (operations.length !== 2 || !operations.includes('publish') || !operations.includes('reply_first')) throw new Error('Wrong first scope');
    if (mode === 'wrong-owner') return {publish: {'output.answer': true}, reply_first: {'output.notice': false}};
    if (mode === 'wrong-pair') return {publish: {'output.notice': true}, reply_first: {'output.answer': true}};
    if (mode === 'alternate') return {reply_first: {'output.answer': false}, publish: {'output.notice': true}};
    return {publish: {'output.notice': false}, reply_first: {'output.answer': true}};
  };
  return {
    observationTransport: 'js-driver-observed/v1', outputOperationTransport: 'js-driver-provides/v1',
    async prepare(pre: Record<string,unknown>, input: Record<string,unknown>) { state = {...pre}; called = false; },
    async observeState() { return {...state}; },
    async prepareObservations(scope: Record<string,any>, values: Record<string,unknown>) {
      if (scope['observation.received'].trigger !== 'first' || scope['observation.received'].cut !== 'trigger-entry') throw new Error('Wrong scope');
      environment = values['observation.received'] === true;
    },
    async triggerObserved(operations: string[], trigger: string, input: Record<string,unknown>) {
      const mode = process.env.CAT_COMBINED_MODE || 'direct';
      const actual = mode === 'wrong-observation' ? !environment : environment;
      const output = frames(operations,trigger,input);
      state['state.anchor'] = mode === 'wrong-state' ? !actual : actual;
      return {observations: {'observation.received': actual}, output};
    },
    async triggerProvidedOperations(operations: string[], trigger: string, input: Record<string,unknown>) { return frames(operations,trigger,input); }
  };
}
"""

# Use the same real driver operation boundary for both paths, not two executions.
JAVA_COMBINED_DRIVER = JAVA_MULTI_DRIVER.replace(
    'private boolean called;', 'private boolean called, environment;').replace(
    'CAT_MULTI_OWNER_MODE','CAT_COMBINED_MODE').replace(
    '    public Map<String,Map<String,Object>> triggerProvidedOperations',
    '''    public void prepareObservations(Map<String,Map<String,String>> scope, Map<String,Object> values) {
        if (!scope.get("observation.received").get("trigger").equals("first") || !scope.get("observation.received").get("cut").equals("trigger-entry")) throw new AssertionError("Wrong scope");
        environment = (Boolean)values.get("observation.received");
    }
    public Map<String,Object> triggerObserved(List<String> operations, String trigger, Map<String,Object> input) {
        if (input.containsKey("observation.received")) throw new AssertionError("Observation leaked into caller input");
        String mode = System.getenv().getOrDefault("CAT_COMBINED_MODE","direct");
        boolean actual = mode.equals("wrong-observation") ? !environment : environment;
        var output = triggerProvidedOperations(operations,trigger,input);
        state.put("state.anchor", mode.equals("wrong-state") ? !actual : actual);
        return Map.of("observations",Map.of("observation.received",actual),"output",output);
    }
    public Map<String,Map<String,Object>> triggerProvidedOperations''')

if __name__=='__main__':unittest.main()
