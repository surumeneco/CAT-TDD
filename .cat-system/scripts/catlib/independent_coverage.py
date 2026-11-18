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


def _independent_integer_cells(domain, field, clauses):
    # Independent from compiler's partition helper. Accept ONLY literal
    # comparisons of this integer field under Boolean composition.
    if not isinstance(domain,dict) or domain.get('type')!='integer':return None
    lo,hi=domain.get('min'),domain.get('max')
    if lo is not None and type(lo) is not int:return None
    if hi is not None and type(hi) is not int:return None
    if lo is not None and hi is not None and lo>hi:return None
    points=[]
    def reads(node):
        return (isinstance(node,dict) and
                (node.get('ref')==field or any(reads(child) for child in node.get('args',[]))))
    def walk(node):
        if not isinstance(node,dict):return False
        if node.get('op')=='call':return False  # Opaque DomainRule bodies
        if not reads(node):return True
        op=node.get('op')
        args=node.get('args',[])
        if op in ('and','or','not') and isinstance(args,list):
            if (op=='not' and len(args)!=1) or (op!='not' and len(args)<2):return False
            return all(walk(part) for part in args)
        if op not in ('eq','ne','lt','le','gt','ge') or len(args)!=2:
            return False
        for left,right in ((args[0],args[1]),(args[1],args[0])):
            if (isinstance(left,dict) and set(left)=={'ref'} and left['ref']==field
                and isinstance(right,dict) and set(right)=={'literal'}
                and type(right['literal']) is int):
                points.append(right['literal']);return True
        return False
    if not all(walk(expr) for expr in clauses) or not points:return None
    points=sorted(set(points))
    reps={points[0]-1,points[-1]+1}
    for k in points:reps.update((k-1,k,k+1))
    if lo is not None:reps.add(lo)
    if hi is not None:reps.add(hi)
    reps=sorted(k for k in reps if (lo is None or k>=lo) and (hi is None or k<=hi))
    return reps if reps and len(reps)<=LIMIT else None


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
    output_unproved=set()
    covered_owners=set()
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
        names=set()
        # Only semantically referenced nonrequired inputs partition Guard truth.
        for clause in [*constraints,*(r['when'] for r in applicable)]:
            names.update(used_refs(clause,definitions))
        dimensions=[];possible=True;partition_fields=[]
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
            if values is None and (field not in inputs or current_presence(field)=='required'):
                values=_independent_integer_cells(domains[field],field,
                             [*constraints,*(r['when'] for r in applicable)])
                if values is not None:partition_fields.append(field)
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
        receipt={'result':'unproven' if unknown else 'conflict' if overlaps else 'uncovered' if gaps else 'proved',
                 'guard_refs':sorted(names),'unreachable_rules':unvisited,
                 'uncovered_count':gaps if not partition_fields else None,
                 'overlap_count':overlaps if not partition_fields else None,
                 'uncovered':uncovered_examples,'overlaps':overlap_examples,
                 'excluded_by_pi_constraints':bool(constraints)}
        if partition_fields:
            receipt.update(proof_method='integer-literal-partition/v1',
                           partition_fields=partition_fields,
                           abstract_state_count=math.prod(map(len,dimensions)),
                           proof_scope='local-guard-truth-partition-not-effect-or-implementation')
        result[ident]=receipt
        if outputs:
            providers=[op for op in operations if op['direction']=='provide'
                       and (op.get('trigger') is None or op['trigger']==ident)]
            # Nonrequired output frames need an explicit, unique provider.
            # Required fields must be emitted by each alternative regardless
            # of whether a nonrequired field or a provide operation exists.
            # A provide Operation only scopes an output frame when the
            # Source declares nonrequired or operation-specific output Presence.
            # Otherwise the legacy direct TCE frame covers all required outputs,
            # even when an unrelated PI declares a provide Operation.
            needs_provider=(bool(output_special) or any(ov['field'] in outputs for ov in overrides))
            provider=providers[0] if needs_provider and len(providers)==1 else None
            if provider is not None:
                covered_owners.add(provider['source_pi'])
            scoped_outputs=(outputs if provider is None else {
                field:info for field,info in outputs.items()
                if info['owner']==provider['source_pi']})
            if output_special and (provider is None
                or any(ov['operation']!=provider['id'] for ov in overrides
                       if ov['field'] in scoped_outputs)):
                output_ok=False
                output_unproved.update(output_special)
            for rule in applicable:
                for outcome in rule['allowed']:
                    emitted={x['target'] for x in outcome['write']}
                    if provider is not None:
                        unowned=emitted & (outputs.keys()-scoped_outputs.keys())
                        if unowned:
                            output_ok=False
                            output_unproved.update(unowned)
                    for field,info in scoped_outputs.items():
                        ps=([ov['presence'] for ov in overrides
                             if ov['field']==field and ov['operation']==provider['id']]
                            if provider is not None else [])
                        presence=ps[0] if ps else info['presence']
                        if (presence=='undefined' or (presence=='required' and field not in emitted)
                                or (presence=='absent' and field in emitted)):
                            output_ok=False
                            output_unproved.add(field)
    orphaned={field for field in output_special
              if outputs[field]['owner'] not in covered_owners}
    if orphaned:
        output_ok=False
        output_unproved.update(orphaned)
    return {'triggers':result,'output_presence_proved':output_ok,
            'unproved_output_fields':sorted(output_unproved)}
