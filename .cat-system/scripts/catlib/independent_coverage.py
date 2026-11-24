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

_PRESENT_CLASS=object()


def _reads_value(node, name):
    if not isinstance(node,dict):return False
    if node.get('op') in ('is-present','is-missing','is-undefined'):
        return False
    if node.get('op')=='call':return True
    return node.get('ref')==name or any(_reads_value(arg,name) for arg in node.get('args',[]))


def _implies_value(node, name):
    if not isinstance(node,dict):return False
    if node.get('op')=='is-present' and node.get('args')==[{'ref':name}]:
        return True
    if node.get('op')=='and':
        previous=[]
        for child in node.get('args',[]):
            if _implies_value(child,name) and not any(_reads_value(p,name) for p in previous):
                return True
            previous.append(child)
    if node.get('op')=='or':
        return all(_implies_value(item,name) for item in node.get('args',[]))
    return False


def _presence_exclusive(node, name):
    """Prove all possible reads of name are Presence-only (not its value)."""
    if not isinstance(node,dict):return False
    if node.get('op')=='call':return False
    if node.get('op') in ('is-present','is-missing','is-undefined'):
        return node.get('args')==[{'ref':name}] or name not in used_refs(node,{})
    if node.get('ref')==name:return False
    return all(_presence_exclusive(item,name) for item in node.get('args',[]))


def _independent_integer_cells(domain, field, clauses, allow_presence=False):
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
        if allow_presence and op in ('is-present','is-missing','is-undefined') and args==[{'ref':field}]:
            return True
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


def _independent_string_cells(domain, field, clauses, allow_presence=False):
    """Independent literal-equality truth cells, without compiler helpers."""
    if domain != {'type': 'string'}:
        return None
    constants=set()
    def mentions(node):
        return (isinstance(node,dict) and
                (node.get('ref') == field or
                 any(mentions(part) for part in node.get('args',[]))))
    def check(node):
        if not isinstance(node,dict) or node.get('op')=='call':
            return False
        if not mentions(node):
            return True
        op=node.get('op');args=node.get('args',[])
        if allow_presence and op in ('is-present','is-missing','is-undefined') and args==[{'ref':field}]:
            return True
        if op in ('and','or','not'):
            if (op=='not' and len(args)!=1) or (op!='not' and len(args)<2):
                return False
            return all(check(part) for part in args)
        if op not in ('eq','ne') or len(args)!=2:
            return False
        for left,right in ((args[0],args[1]),(args[1],args[0])):
            if (isinstance(left,dict) and set(left)=={'ref'} and left['ref']==field
                    and isinstance(right,dict) and set(right)=={'literal'}
                    and type(right['literal']) is str):
                constants.add(right['literal']);return True
        return False
    if not all(check(clause) for clause in clauses) or not constants:
        return None
    if len(constants)>=LIMIT:
        return None
    other=''
    while other in constants:
        other+='\x00'
    return [*sorted(constants),other]


def _independent_integer_pair_values(names, domains, inputs, current_presence, clauses, definitions):
    """Reconstruct finite weak-order truth classes directly from Source data.

    All direct reference/reference comparisons within a same-domain group are
    invariant under strictly monotone re-labelling of its distinct values.
    For N<=5 references, N ordered representative values cover every
    possible tie/order pattern; small bounded Domains use their entire range.
    This does not borrow a Compiler coverage receipt or establish reachability.
    """
    group=sorted(name for name in names if name in domains
                 and isinstance(domains[name],dict)
                 and domains[name].get('type')=='integer'
                 and set(domains[name]) <= {'type','min','max'}
                 and (name not in inputs or current_presence(name)=='required'))
    if len(group)<2 or len(group)>5:return {}
    domain=domains[group[0]]
    if any(domains[name]!=domain for name in group[1:]):return {}
    start,end=domain.get('min'),domain.get('max')
    if start is not None and type(start) is not int:return {}
    if end is not None and type(end) is not int:return {}
    if start is not None and end is not None and start>end:return {}
    # Cap the number of ranks by the exact finite Domain cardinality when
    # necessary. An all-distinct N-tuple then correctly becomes impossible.
    cardinality=(end-start+1) if start is not None and end is not None else None
    ranks=len(group) if cardinality is None else min(cardinality,len(group))
    if ranks<2:return {}
    if start is None:
        start=(end-ranks+1 if end is not None and end<ranks-1 else 0)
    if end is not None and start+ranks-1>end:return {}
    group_set=set(group)
    def safe(expr):
        if not isinstance(expr,dict):return False
        if not (used_refs(expr,definitions)&group_set):return True
        op=expr.get('op')
        args=expr.get('args',[])
        if op in ('and','or','not') and isinstance(args,list):
            return all(safe(x) for x in args)
        if op in ('eq','ne','lt','le','gt','ge') and isinstance(args,list) and len(args)==2:
            if not all(isinstance(x,dict) and set(x)=={'ref'} for x in args):return False
            return args[0]['ref']!=args[1]['ref'] and all(x['ref'] in group_set for x in args)
        return False
    if not all(safe(expr) for expr in clauses):return {}
    ranks_values=list(range(start,start+ranks))
    return {key:ranks_values for key in group}


def _independent_integer_range_values(names, domains, inputs, current_presence, clauses, definitions):
    """Independent Source-derived integer order cells across unequal Domains.

    The only admissible atoms use two distinct integer references or one
    reference and an exact integer literal. Domain endpoints/literals are
    singleton cells; all open cells are represented by up to N rank values.
    No Compiler proof receipt or sampled unknown state is consulted.
    """
    variables=sorted(key for key in names
                     if key in domains and isinstance(domains[key],dict)
                     and domains[key].get('type')=='integer'
                     and set(domains[key]) <= {'type','min','max'}
                     and (key not in inputs or current_presence(key)=='required'))
    if len(variables)<2 or len(variables)>3:return {}
    boundaries=set()
    for key in variables:
        dom=domains[key]
        lower,upper=dom.get('min'),dom.get('max')
        if (lower is not None and type(lower) is not int
                or upper is not None and type(upper) is not int
                or lower is not None and upper is not None and lower>upper):
            return {}
        boundaries.update(x for x in (lower,upper) if x is not None)
    allowed=set(variables)
    saw_pair=False
    def safe(expr):
        nonlocal saw_pair
        if not isinstance(expr,dict):return False
        if not (used_refs(expr,definitions)&allowed):return True
        op=expr.get('op')
        args=expr.get('args',[])
        if op in ('and','or','not') and isinstance(args,list):
            return all(safe(part) for part in args)
        if op not in ('eq','ne','lt','le','gt','ge') or not isinstance(args,list) or len(args)!=2:
            return False
        if (all(isinstance(x,dict) and set(x)=={'ref'} and x['ref'] in allowed for x in args)
                and args[0]['ref']!=args[1]['ref']):
            saw_pair=True
            return True
        for index in (0,1):
            lhs,rhs=args[index],args[1-index]
            if (isinstance(lhs,dict) and set(lhs)=={'ref'} and lhs['ref'] in allowed
                    and isinstance(rhs,dict) and set(rhs)=={'literal'}
                    and type(rhs['literal']) is int):
                boundaries.add(rhs['literal'])
                return True
        return False
    if not all(safe(clause) for clause in clauses) or not saw_pair:return {}
    cuts=sorted(boundaries)
    rank_count=len(variables)
    choices=[]
    previous=None
    for cut in cuts:
        if previous is None:
            choices.extend(range(cut-rank_count,cut))
        else:
            bottom=previous+1
            if cut>bottom:
                choices.extend(range(bottom,min(bottom+rank_count,cut)))
        choices.append(cut)
        previous=cut
    if cuts:
        choices.extend(range(cuts[-1]+1,cuts[-1]+rank_count+1))
    else:
        choices=list(range(rank_count))
    result={}
    for key in variables:
        dom=domains[key]
        low,high=dom.get('min'),dom.get('max')
        vals=[value for value in choices
              if (low is None or value>=low) and (high is None or value<=high)]
        if not vals:return {}
        result[key]=vals
    return result

def _independent_has_order_comparison(expr):
    if not isinstance(expr,dict):return False
    if expr.get('op') in ('lt','le','gt','ge'):return True
    return any(_independent_has_order_comparison(x) for x in expr.get('args',[]))


def audit(process,pi_docs,tces,roles,domains,domain_rule=None):
    rules=[r for _,_,tce in tces for r in tce['rules']]
    # Acceptance Guard-space may use only constraints whose every reference
    # is an input owned by that PI. Output/result constraints belong to a
    # later evaluation stage, even when the PI also has an accept Operation.
    constraint_sources=[(fm['id'],c,{field['id']:field['role']
                                    for field in pi['fields']})
                        for _,fm,pi in pi_docs
                        for c in pi.get('constraints',[])]
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
        constraints=[expr for owner,expr,owned_roles in constraint_sources
                     if chosen is not None and chosen['source_pi']==owner
                     and all(owned_roles.get(ref)=='input'
                             for ref in used_refs(expr,definitions))]
        def current_presence(field):
            info=inputs[field]
            selected=[ov for ov in overrides if chosen and ov['operation']==chosen['id']
                      and ov['field']==field and chosen['source_pi']==info['owner']]
            return selected[0]['presence'] if selected else info['presence']
        special={field for field in inputs if current_presence(field)!='required'}
        if any(any(not _implies_value(r['when'],ref)
                   for ref in used_refs(w['expr'],definitions)&special)
               for r in applicable for outcome in r['allowed'] for w in outcome['write']):
            result[ident]={'result':'unproven','unreachable_rules':sorted(r['id'] for r in applicable)}
            continue
        names=set()
        # Only semantically referenced nonrequired inputs partition Guard truth.
        for clause in [*constraints,*(r['when'] for r in applicable)]:
            names.update(used_refs(clause,definitions))
        dimensions=[];possible=True;partition_fields=[];partition_kinds=set()
        clauses=[*constraints,*(r['when'] for r in applicable)]
        integer_pair=_independent_integer_pair_values(names,domains,inputs,current_presence,clauses,definitions)
        integer_range=({} if integer_pair else _independent_integer_range_values(
            names,domains,inputs,current_presence,clauses,definitions))
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
            if field in integer_range:
                values=integer_range[field]
                partition_fields.append(field)
                partition_kinds.add('integer_ref_range')
            if (values is None and field in inputs and current_presence(field)=='optional'
                    and all(_presence_exclusive(predicate,field)
                            for predicate in [*constraints,*(r['when'] for r in applicable)])):
                values=[types.MISSING,_PRESENT_CLASS]
            if values is None and (field not in inputs or current_presence(field)=='required'):
                values=_independent_integer_cells(domains[field],field,
                             [*constraints,*(r['when'] for r in applicable)])
                if values is not None:
                    partition_fields.append(field)
                    partition_kinds.add('integer')
            if values is None and (field not in inputs or current_presence(field)=='required'):
                values=_independent_string_cells(domains[field],field,
                           [*constraints,*(r['when'] for r in applicable)])
                if values is not None:
                    partition_fields.append(field)
                    partition_kinds.add('string')
            if values is None and field in inputs and current_presence(field)=='optional':
                representatives=_independent_integer_cells(domains[field],field,clauses,allow_presence=True)
                kind='optional_integer'
                if representatives is None:
                    representatives=_independent_string_cells(domains[field],field,clauses,allow_presence=True)
                    kind='optional_string'
                if representatives is not None:
                    values=[types.MISSING,*representatives]
                    partition_fields.append(field)
                    partition_kinds.add(kind)
            if values is None and field in integer_pair:
                values=integer_pair[field]
                partition_fields.append(field)
                partition_kinds.add((
                    'integer_ref_multi_order' if any(
                        _independent_has_order_comparison(clause) for clause in clauses)
                    else 'integer_ref_multi_equality') if len(integer_pair)>=3 else (
                    'integer_ref_order' if any(
                        _independent_has_order_comparison(clause) for clause in clauses)
                    else 'integer_ref_pair'))
            if values is None:
                possible=False;break
            dimensions.append(values)
        if not possible or math.prod(map(len,dimensions))>LIMIT:
            result[ident]={'result':'unproven','unreachable_rules':sorted(r['id'] for r in applicable)}
            continue
        gaps=overlaps=0;visited=set();unknown=False
        admissible=0
        uncovered_examples=[];overlap_examples=[]
        def snapshot(env):
            return {name:({'$cat_presence':'missing'} if value is types.MISSING else
                          {'$cat_presence':'undefined'} if value is types.UNDEFINED else
                          {'$cat_presence':'present'} if value is _PRESENT_CLASS else value)
                    for name,value in env.items()}
        for items in itertools.product(*dimensions):
            env=dict(zip(sorted(names),items))
            try:
                if not all(eval_expr(c,env,definitions) for c in constraints):continue
                admissible+=1
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
        if not unknown and not admissible:
            # Never certify the empty set as a closed, executable Trigger.
            # This is recomputed from Source constraints, not Compiler receipts.
            result[ident]={'result':'unproven',
                           'reason':'no admissible Source-constrained Guard state',
                           'guard_refs':sorted(names),
                           'unreachable_rules':unvisited,
                           'excluded_by_pi_constraints':bool(constraints)}
            continue
        receipt={'result':'unproven' if unknown else 'conflict' if overlaps else 'uncovered' if gaps else 'proved',
                 'guard_refs':sorted(names),'unreachable_rules':unvisited,
                 'uncovered_count':gaps if not partition_fields else None,
                 'overlap_count':overlaps if not partition_fields else None,
                 'uncovered':uncovered_examples,'overlaps':overlap_examples,
                 'excluded_by_pi_constraints':bool(constraints)}
        if partition_fields:
            method=('integer-literal-partition/v1' if partition_kinds=={'integer'}
                    else 'string-literal-equality-partition/v1' if partition_kinds=={'string'}
                    else 'optional-string-literal-equality-partition/v1' if partition_kinds=={'optional_string'}
                    else 'optional-integer-literal-partition/v1' if partition_kinds=={'optional_integer'}
                    else 'integer-reference-equality-partition/v1' if partition_kinds=={'integer_ref_pair'}
                    else 'integer-reference-order-partition/v1' if partition_kinds=={'integer_ref_order'}
                    else 'integer-reference-equality-partition/v2' if partition_kinds=={'integer_ref_multi_equality'}
                    else 'integer-reference-order-partition/v2' if partition_kinds=={'integer_ref_multi_order'}
                    else 'integer-reference-range-order-partition/v1' if partition_kinds=={'integer_ref_range'}
                    else 'mixed-exact-predicate-partition/v1')
            receipt.update(proof_method=method,
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
