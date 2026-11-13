"""Conservative independent finite-Guard audit for Source→Model Conformance.

Do not use the Compiler's coverage receipts as expected proof. This module
reads parsed normative Process/PI/TCE inputs and re-evaluates their truth
partitions. Unsupported/nonfinite cases stay unproven, not presumed covered.
The canonical expression evaluator defines expression semantics, not proof
outcomes; no call to cat_compile_v2.load() or its closure helpers is made.
"""
from __future__ import annotations
import itertools
import math
from catlib import semantic_types as types
from cat_compile_v2 import eval_expr,used_refs,Blocked

LIMIT=65536


def audit(process,pi_docs,tces,roles,domains,domain_rule=None):
    rules=[r for _,_,tce in tces for r in tce['rules']]
    constraints=[c for _,_,pi in pi_docs for c in pi.get('constraints',[])]
    definitions={x['id']:x for x in domain_rule['definitions']} if domain_rule else {}
    inputs={}
    outputs={}
    operations=[]
    overrides=[]
    for _,fm,pi in pi_docs:
        for field in pi['fields']:
            info={'presence':field.get('presence','required'),'owner':fm['id']}
            if field['role']=='input':inputs[field['id']]=info
            if field['role']=='output':outputs[field['id']]=info
        operations.extend({**op,'source_pi':fm['id']} for op in pi.get('operations',[]))
        overrides.extend({**ov,'source_pi':fm['id']} for ov in pi.get('operation_presence',[]))

    output_special={k for k,v in outputs.items() if v['presence']!='required'}
    output_special.update(ov['field'] for ov in overrides
                          if ov['field'] in outputs and ov['presence']!='required')
    result={}
    output_ok=True
    for trigger in process['triggers']:
        ident=trigger['id']
        applicable=[r for r in rules if r['trigger']==ident]
        accept=[op for op in operations if op['direction']=='accept' and op.get('trigger')==ident]
        if len(accept)>1:
            result[ident]={'result':'unproven','unreachable_rules':sorted(r['id'] for r in applicable)}
            continue
        chosen=accept[0] if accept else None
        def current_presence(field):
            info=inputs[field]
            selected=[ov for ov in overrides if chosen and ov['operation']==chosen['id']
                      and ov['field']==field and chosen['source_pi']==info['owner']]
            return selected[0]['presence'] if selected else info['presence']
        special={field for field in inputs if current_presence(field)!='required'}
        if any(used_refs(w['expr'],definitions)&special
               for r in applicable for outcome in r['allowed'] for w in outcome['write']):
            result[ident]={'result':'unproven','unreachable_rules':sorted(r['id'] for r in applicable)}
            continue
        names=set(special)
        for clause in [*constraints,*(r['when'] for r in applicable)]:
            names.update(used_refs(clause,definitions))
        dimensions=[];possible=True
        for field in sorted(names):
            if field not in domains or roles.get(field) in ('output','action'):
                possible=False;break
            if field in inputs:
                presence=current_presence(field)
                if presence=='absent':values=[types.MISSING]
                elif presence=='undefined':values=[types.UNDEFINED]
                else:
                    values=types.finite_values(domains[field])
                    if values is not None and presence=='optional':values=[types.MISSING,*values]
            else:values=types.finite_values(domains[field])
            if values is None:
                possible=False;break
            dimensions.append(values)
        if not possible or math.prod(map(len,dimensions))>LIMIT:
            result[ident]={'result':'unproven','unreachable_rules':sorted(r['id'] for r in applicable)}
            continue
        gaps=overlaps=0;visited=set();unknown=False
        uncovered_examples=[];overlap_examples=[]
        def snapshot(env):
            return {name:({'$cat_presence':'missing'} if value is types.MISSING else
                          {'$cat_presence':'undefined'} if value is types.UNDEFINED else value)
                    for name,value in env.items()}
        for items in itertools.product(*dimensions):
            env=dict(zip(sorted(names),items))
            try:
                if not all(eval_expr(c,env,definitions) for c in constraints):continue
                hit=[r['id'] for r in applicable if eval_expr(r['when'],env,definitions)]
            except (Blocked,TypeError,ValueError,KeyError):
                unknown=True;break
            if len(hit)==0:
                gaps+=1
                if len(uncovered_examples)<64:uncovered_examples.append(snapshot(env))
            if len(hit)>1:
                overlaps+=1
                if len(overlap_examples)<16:
                    overlap_examples.append({'state':snapshot(env),'rules':hit})
            visited.update(hit)
        unvisited=sorted({r['id'] for r in applicable}-visited)
        result[ident]={'result':'unproven' if unknown else 'conflict' if overlaps else 'uncovered' if gaps else 'proved',
                       'guard_refs':sorted(names),'unreachable_rules':unvisited,
                       'uncovered_count':gaps,'overlap_count':overlaps,
                       'uncovered':uncovered_examples,'overlaps':overlap_examples,
                       'excluded_by_pi_constraints':bool(constraints)}
        if output_special:
            providers=[op for op in operations if op['direction']=='provide'
                       and (op.get('trigger') is None or op['trigger']==ident)]
            if (len(providers)!=1 or any(info['owner']!=providers[0]['source_pi'] for info in outputs.values())
                or any(ov['operation']!=providers[0]['id'] for ov in overrides if ov['field'] in outputs)):
                output_ok=False
            else:
                provider=providers[0]
                for rule in applicable:
                    for outcome in rule['allowed']:
                        emitted={x['target'] for x in outcome['write']}
                        for field,info in outputs.items():
                            ps=[ov['presence'] for ov in overrides if ov['field']==field and ov['operation']==provider['id']]
                            presence=ps[0] if ps else info['presence']
                            if (presence=='undefined' or (presence=='required' and field not in emitted)
                                    or (presence=='absent' and field in emitted)):
                                output_ok=False
    return {'triggers':result,'output_presence_proved':output_ok}
