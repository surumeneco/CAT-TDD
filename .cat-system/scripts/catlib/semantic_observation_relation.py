"""Explicit finite, Trigger-local observation domains; not observer authentication."""
from itertools import product
from math import prod
from catlib import semantic_types as typed

TOKEN='@cat:trigger-observation-relation/v1'
PREFIX='observation-relation '
LIMIT=4096


def candidates(documents,process,fields,triggers,confirmed):
    from cat_compile_v2 import Blocked,parse_expr_text,inspect_expr,used_refs
    result={}
    if not confirmed:return result
    for doc in documents:
        if doc['kind']!='domain-spec' or doc['process']!=process or not doc['scope_verified']:continue
        for rule in doc['rules']:
            scope=rule.get('condition','')
            if rule.get('requirement')!=TOKEN or rule.get('verification_contract')!='cat:intrinsic-model/v1' or not scope.startswith(PREFIX):continue
            try:
                trigger,text=scope[len(PREFIX):].split(' ',1)
                if trigger not in triggers:continue
                expr=parse_expr_text(text);refs=used_refs(expr,{})
                if inspect_expr(expr,fields,{})!='boolean':continue
                obs=[k for k in refs if fields[k]['role']=='observation']
                if not obs or any(fields[k]['role'] not in ('state','observation') for k in refs):continue
                if any(trigger not in fields[k].get('available_on',[]) for k in obs):continue
                result.setdefault(trigger,{})[rule['id']]=expr
            except (Blocked,ValueError,TypeError,KeyError):continue
    return result


def dimensions(expressions,fields):
    from cat_compile_v2 import used_refs
    refs=set().union(*(used_refs(e,{}) for e in expressions))
    state=sorted(k for k in refs if fields[k]['role']=='state')
    obs=sorted(refs-set(state))
    sd=[typed.finite_values(fields[k]['domain'],max_values=LIMIT) for k in state]
    od=[typed.finite_values(fields[k]['domain'],max_values=LIMIT) for k in obs]
    if any(not d for d in sd+od) or prod(map(len,sd+od))>LIMIT:return None
    return state,sd,obs,od


def prove(documents,process,fields,triggers,confirmed):
    from cat_compile_v2 import Blocked,eval_expr
    result={}
    for trigger,rows in candidates(documents,process,fields,triggers,confirmed).items():
        try:
            dims=dimensions(rows.values(),fields)
            if dims is None:continue
            state,sd,obs,od=dims
            if all(any(all(eval_expr(expr,dict(zip(state+obs,a+b)),{}) is True for expr in rows.values())
                       for b in product(*od)) for a in product(*sd)):
                result[trigger]=rows
        except (Blocked,ValueError,TypeError,KeyError,ArithmeticError):continue
    return result


def independent_prove(documents,process,fields,triggers,confirmed):
    """Reconstruct the joint relation's projection, not Compiler's receipt."""
    from cat_compile_v2 import Blocked,eval_expr
    result={}
    for trigger,rows in candidates(documents,process,fields,triggers,confirmed).items():
        try:
            dims=dimensions(rows.values(),fields)
            if dims is None:continue
            state,sd,obs,od=dims
            allowed=list(product(*sd));covered=set()
            for cell in product(*(sd+od)):
                env=dict(zip(state+obs,cell))
                if all(eval_expr(expr,env,{}) is True for expr in rows.values()):
                    covered.update(i for i,values in enumerate(allowed) if typed.same(list(values),list(cell[:len(state)])))
            if len(covered)==len(allowed):result[trigger]=rows
        except (Blocked,ValueError,TypeError,KeyError,ArithmeticError):continue
    return result
