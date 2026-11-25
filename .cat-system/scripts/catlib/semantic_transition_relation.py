"""Bounded, exact projection of a Source-declared transition relation.

The contract is over model values, not execution traces or provider receipts.
The checker enumerates complete finite domains; it never samples a relation.
"""
from __future__ import annotations

import itertools
import json
import math

from catlib import peer_binding, semantic_types as typed, semantic_structural_copy as copy_relation

TOKEN='@cat:finite-transition-relation/v1'
PREFIX='transition-relation '
OBS_PREFIX='observed-transition-relation '
STRUCT_PREFIX='finite-structural-transition-relation '
OBS_TOKEN='@cat:observed-transition-relation/v1'
STRUCT_TOKEN='@cat:finite-structural-transition-relation/v1'
PROFILES={TOKEN:PREFIX, OBS_TOKEN:OBS_PREFIX, STRUCT_TOKEN:STRUCT_PREFIX, copy_relation.TOKEN:copy_relation.PREFIX}
LIMIT=65536


def matches(token,scope):
    return token in PROFILES and isinstance(scope,str) and scope.startswith(PROFILES[token])


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate relation key')
        result[key]=value
    return result


def prepare(scope,fields,pi_docs,rules,checks,rejected=(),invariants=(),independent=False,observation_relations=None):
    """Decode syntax and resolve exact owner, operation, peer and finite domains.

    Shared syntax/type resolution only: no preservation or equivalence verdict.
    The independent validator supplies its own Source-derived fields and rules.
    """
    from cat_compile_v2 import parse_expr_text, inspect_expr, used_refs, Blocked, _bind_member_refs
    prefix=next((p for p in (PREFIX,OBS_PREFIX,STRUCT_PREFIX) if isinstance(scope,str) and scope.startswith(p)),None)
    if prefix is None:return None
    try:
        spec=json.loads(scope[len(prefix):],object_pairs_hook=_unique_object)
        keys={'trigger','pi','operation','peer','when','fields','relation'}
        if prefix==OBS_PREFIX:keys.add('observations')
        if not isinstance(spec,dict) or set(spec) not in (keys,keys|{'provide'}):return None
        if any(not isinstance(spec[k],str) or not spec[k] for k in spec if k not in ('fields','observations')):return None
        declared=spec.get('observations',[])
        if not isinstance(declared,list) or any(type(x) is not str for x in declared) or len(declared)!=len(set(declared)):return None
        if prefix==OBS_PREFIX and not declared:return None
        subjects=spec['fields']
        if not isinstance(subjects,list) or not subjects or any(not isinstance(k,str) for k in subjects) or len(set(subjects))!=len(subjects):return None
        if any(k.startswith('after.') for k in fields):return None
        trigger=spec['trigger']
        accepts=[(fm['id'],pi,op) for _,fm,pi in pi_docs for op in pi['operations'] if op['direction']=='accept' and op.get('trigger')==trigger]
        if len(accepts)!=1:return None
        owner,pi,op=accepts[0]
        if owner!=spec['pi'] or op['id']!=spec['operation']:return None
        peers=pi['boundary'].get('peers',[pi['boundary']['peer']])
        if peer_binding.match_operation(peers,op.get('peer'),spec['peer'])!='static':return None
        def presence(operation,key):
            matches=[r['presence'] for r in pi.get('operation_presence',[]) if r['operation']==operation and r['field']==key]
            if len(matches)>1:raise ValueError('ambiguous Presence')
            return matches[0] if matches else fields[key].get('presence','required')
        outputs=[]
        for key in subjects:
            if key not in fields or fields[key]['role'] not in ('state','output'):return None
            if fields[key]['role']=='output':outputs.append(key)
        if outputs:
            # Existing profiles require a static output operation for the whole cut.
            if pi.get('output_frames'):return None
            provides=[(fm['id'],other,op) for _,fm,other in pi_docs for op in other['operations'] if op['direction']=='provide' and op.get('trigger')==trigger]
            if len(provides)!=1:return None
            po,ppi,pop=provides[0]
            if po!=owner or pop['id']!=spec.get('provide') or peer_binding.match_operation(peers,pop.get('peer'),spec['peer'])!='static':return None
            if any(fields[k].get('source_pi')!=owner or presence(pop['id'],k)!='required' for k in outputs):return None
        elif 'provide' in spec:return None
        when=parse_expr_text(spec['when']);relation=parse_expr_text(spec['relation'])
        # After values are supplied to the relation as required, local
        # predicate arguments. This enables the same typed member notation
        # for before and after records without adding PI inputs or requiring
        # any particular representation in product implementation.
        post={f'after.{k}':{**fields[k],'role':'input','presence':'required'}
              if prefix==STRUCT_PREFIX else {**fields[k],'role':'state'} for k in subjects}
        if prefix!=PREFIX:
            _bind_member_refs(when,fields)
            _bind_member_refs(relation,{**fields,**post})
        if inspect_expr(when,fields,{})!='boolean' or inspect_expr(relation,{**fields,**post},{})!='boolean':return None
        if used_refs(when,{}) & post.keys():return None
        constraints=[*pi.get('constraints',[]),*invariants]
        if prefix==OBS_PREFIX:
            constraints.extend((observation_relations or {}).get(trigger,{}).values())
        applicable=[r for r in rules if r['trigger']==trigger]
        if not applicable:return None
        predicates=[when,relation,*constraints,*(r['when'] for r in applicable)]
        refs=set().union(*(used_refs(e,{}) for e in predicates))-post.keys()
        string_writes=[]
        refs.update(k for k in subjects if fields[k]['role']=='state')
        for row in applicable:
            for n,out in enumerate(row['allowed'],1):
                targets=set()
                for i,w in enumerate(out['write'],1):
                    k=w['target']
                    if k not in subjects:continue
                    if k in targets:return None
                    targets.add(k)
                    key=f"{row['source_artifact']}#{row['id']}:{n}:{i}:{k}"
                    if key in rejected or checks.get(key,{}).get('result')!='proved':return None
                    refs.update(used_refs(w['expr'],{}))
                    if fields[k]['domain']=={'type':'string'}:string_writes.append(w['expr'])
                    else:predicates.append(w['expr'])
                if not set(outputs)<=targets:return None
        for r in refs:
            if r not in fields:return None
            field=fields[r]
            if field['role']=='state':continue
            if prefix==OBS_PREFIX and field['role']=='observation':
                if r not in declared or field.get('available_on')!=[trigger] or field['domain']['type'] not in ('boolean','enum'):return None
                source=field.get('source','')
                if not isinstance(source,str) or not source.startswith('same-execution-observation '):return None
                binding=json.loads(source[len('same-execution-observation '):],object_pairs_hook=_unique_object)
                if not isinstance(binding,dict) or set(binding)!={'trigger','pi','operation','peer','cut','source'}:return None
                if any(binding[k]!=spec[k] for k in ('trigger','pi','operation','peer')) or binding['cut']!='trigger-entry' or not isinstance(binding['source'],str) or not binding['source'].strip():return None
                continue
            if field['role']!='input' or field.get('source_pi')!=owner or presence(op['id'],r)!='required':return None
        if prefix==OBS_PREFIX and set(declared)!={r for r in refs if fields[r]['role']=='observation'}:return None
        before=sorted(refs)
        # Unrestricted strings have a complete finite *equality quotient*
        # for these expressions. Include every before and after variable and
        # every literal assignment, not just one sampled request identifier.
        string_group={k for k in before if fields[k]['domain']=={'type':'string'}} | {
            'after.'+k for k in subjects if fields[k]['domain']=={'type':'string'}}
        palette=None
        if string_group:
            if prefix!=PREFIX:return None
            constants=[]
            for expr in string_writes:
                if set(expr)=={'literal'} and type(expr['literal']) is str:constants.append(expr['literal'])
                elif set(expr)=={'ref'} and expr['ref'] in string_group and not expr['ref'].startswith('after.'):pass
                else:return None
            if independent:
                from catlib.independent_coverage import independent_reference_palette as make_palette
            else:
                from catlib.semantic_string_partition import reference_palette as make_palette
            palette=make_palette(string_group,predicates,constants,require_pair=False)
            if palette is None:return None
        def dimensions(keys):
            return [palette if fields[k]['domain']=={'type':'string'} else
                    typed.finite_values(fields[k]['domain'],max_values=LIMIT)
                    if fields[k]['domain']['type'] in ('boolean','enum','integer') or (prefix==STRUCT_PREFIX and fields[k]['domain']['type'] in ('record','nullable','union','reference','null')) else None for k in keys]
        before_dims=dimensions(before);after_dims=dimensions(subjects)
        if any(not d for d in before_dims+after_dims) or math.prod(map(len,before_dims+after_dims))>LIMIT:return None
        return before,before_dims,subjects,after_dims,when,relation,constraints,applicable
    except (Blocked,ValueError,KeyError,TypeError,ArithmeticError):return None


def prove(scope,fields,pi_docs,rules,checks,invariants=(),observation_relations=None):
    from cat_compile_v2 import eval_expr, Blocked
    if scope.startswith(copy_relation.PREFIX):
        return copy_relation.prove(scope,fields,pi_docs,rules,checks,invariants)
    prepared=prepare(scope,fields,pi_docs,rules,checks,invariants=invariants,observation_relations=observation_relations)
    if prepared is None:return False
    before,bd,subjects,ad,when,relation,constraints,applicable=prepared
    witnessed=False
    try:
        for values in itertools.product(*bd):
            env=dict(zip(before,values))
            if not all(eval_expr(x,env,{}) is True for x in [*constraints,when]):continue
            witnessed=True
            hits=[r for r in applicable if eval_expr(r['when'],env,{}) is True]
            if len(hits)!=1:return False
            actual=[]
            for out in hits[0]['allowed']:
                writes={w['target']:eval_expr(w['expr'],env,{}) for w in out['write'] if w['target'] in subjects}
                projection=[writes[k] if k in writes else env[k] for k in subjects]
                if not all(typed.contains(fields[k]['domain'],v) for k,v in zip(subjects,projection)):return False
                actual.append(projection)
            expected=[]
            for candidate in itertools.product(*ad):
                if eval_expr(relation,{**env,**{'after.'+k:v for k,v in zip(subjects,candidate)}},{}) is True:expected.append(list(candidate))
            if not actual or not expected:return False
            if any(not any(typed.same(a,e) for e in expected) for a in actual):return False
            if any(not any(typed.same(a,e) for a in actual) for e in expected):return False
        return witnessed
    except (Blocked,ValueError,KeyError,TypeError,ArithmeticError):return False
