"""Independent positive Effect-Domain audit over original Source expressions.

This is a second, conservative proof path, not a general Effect solver.
It never calls the Compiler's Effect proof or symbolic containment helpers.
The common expression evaluator and Domain semantics define the notation;
proof selection and the accepted algebraic fragments are separate here.
"""
from __future__ import annotations

import itertools
import math
from catlib import semantic_types as types
from catlib import semantic_subtyping as subtyping
from catlib.independent_coverage import _implies_value
from cat_compile_v2 import Blocked, eval_expr, used_refs


def _symbolic(expr, target, fields):
    """An independent sufficient condition for exact integer/Set closure."""
    op=expr.get('op')
    args=expr.get('args',[])
    if op=='add' and isinstance(args,list) and len(args)>=2:
        bounds=[]
        for arg in args:
            if not isinstance(arg,dict):return False
            if set(arg)=={'literal'} and type(arg['literal']) is int:
                value=arg['literal'];bounds.append((value,value))
            elif set(arg)=={'ref'} and arg['ref'] in fields:
                field=fields[arg['ref']]
                domain=field['domain']
                if field['role'] not in ('input','state','observation') or domain.get('type')!='integer':
                    return False
                bounds.append((domain.get('min'),domain.get('max')))
            else:return False
        derived={'type':'integer'}
        for position,key in ((0,'min'),(1,'max')):
            endpoints=[pair[position] for pair in bounds]
            if all(type(x) is int for x in endpoints):
                derived[key]=sum(endpoints)
        return subtyping.subset(derived,target) is True
    if op in ('set-add','set-remove') and isinstance(args,list) and len(args)==2:
        if not all(isinstance(x,dict) and set(x)=={'ref'} and x['ref'] in fields for x in args):
            return False
        owner=fields[args[0]['ref']];item=fields[args[1]['ref']]
        if (owner['role'] not in ('input','state','observation')
                or item['role'] not in ('input','state','observation')):
            return False
        collection=owner['domain']
        if collection.get('type')!='set' or target.get('type')!='set':
            return False
        item_target=(target['element'] if op=='set-add' else collection['element'])
        return (subtyping.subset(collection,target) is True
                and subtyping.subset(item['domain'],item_target) is True)
    return False


def _certifies(rule,write,fields,definitions,limit=4096):
    target=fields.get(write.get('target'))
    expr=write.get('expr')
    if not isinstance(target,dict) or not isinstance(expr,dict):return False
    domain=target.get('domain')
    if not isinstance(domain,dict):return False
    try:
        refs=sorted(used_refs(expr,definitions))
        for ref in refs:
            field=fields.get(ref)
            if field is None or field.get('role') not in ('input','state','observation'):
                return False
            if (field['role']=='input' and field.get('presence','required')!='required'
                    and not _implies_value(rule['when'],ref)):
                return False
        if 'literal' in expr:
            return types.contains(domain,expr['literal'])
        if set(expr)=={'ref'}:
            return subtyping.subset(fields[expr['ref']]['domain'],domain) is True
        if _symbolic(expr,domain,fields):return True
        dimensions=[]
        for ref in refs:
            values=types.finite_values(fields[ref]['domain'],max_values=limit)
            if values is None or not values:return False
            dimensions.append(values)
        if math.prod(map(len,dimensions))>limit:return False
        for values in itertools.product(*dimensions):
            env=dict(zip(refs,values))
            if not types.contains(domain,eval_expr(expr,env,definitions)):
                return False
        return True
    except (Blocked,types.DomainError,ValueError,TypeError,KeyError,IndexError,OverflowError):
        return False


def unjustified_positive(rules,fields,definitions,compiler_checks):
    """Return Source Effect IDs that lack a separate positive proof."""
    rejected=[]
    for rule in rules:
        for n,outcome in enumerate(rule['allowed'],1):
            for k,write in enumerate(outcome['write'],1):
                ident=f"{rule['source_artifact']}#{rule['id']}:{n}:{k}:{write['target']}"
                if compiler_checks.get(ident,{}).get('result')=='proved':
                    if not _certifies(rule,write,fields,definitions):
                        rejected.append(ident)
    return sorted(rejected)
