"""Exact collection result relations, not implementation algorithms.

A limited profile for a required, same-cut sequence/set of resolved records.
Selection is equality of a declared required scalar member; ordering is a
stable permutation by a declared required integer key. The length is unbounded
in the symbolic proof. No external observation or business predicate is guessed.
"""
from __future__ import annotations
import json
from catlib import semantic_types as typed, semantic_structural_copy as copy_relation

TOKEN='@cat:collection-relation/v1'
PREFIX='collection-relation '
OPERATORS=('filter-by','stable-sort-by')


def _unwrap(domain):
    while domain.get('type')=='reference' and domain.get('resolved'):
        domain=domain['of']
    return domain


def operator_domain(expr,fields):
    """Return the exact result Domain for this total pure expression, or None."""
    try:
        op=expr['op'];args=expr['args']
        if op not in OPERATORS or set(expr)!={'op','args'} or len(args)!=3:return None
        if set(args[0])!={'ref'} or any(set(x)!={'literal'} for x in args[1:]):return None
        f=fields[args[0]['ref']]
        if f['role'] not in ('input','state') or not copy_relation._supported_value(f['domain']):return None
        collection=_unwrap(f['domain'])
        if collection['type'] not in ('sequence','set') or (op=='stable-sort-by' and collection['type']!='sequence'):return None
        record=_unwrap(collection['element'])
        if record['type']!='record' or not record.get('resolved'):return None
        key=args[1]['literal'];value=args[2]['literal']
        if type(key) is not str:return None
        members=[m for m in record['fields'] if m['id']==key and m['presence']=='required']
        if len(members)!=1:return None
        domain=_unwrap(members[0]['domain'])
        if op=='filter-by':
            if domain['type'] not in ('boolean','integer','string','enum','null') or not typed.contains(domain,value):return None
        elif domain['type']!='integer' or value not in ('asc','desc'):return None
        return f['domain']
    except (KeyError,TypeError,ValueError,AttributeError):return None


def evaluate(op,values):
    collection,key,value=values
    if type(collection) is not list or type(key) is not str or any(type(x) is not dict or key not in x for x in collection):
        raise ValueError('invalid collection relation operands')
    if op=='filter-by':return [x for x in collection if typed.same(x[key],value)]
    if value not in ('asc','desc') or any(type(x[key]) is not int for x in collection):
        raise ValueError('stable sort requires an integer key and explicit direction')
    return sorted(collection,key=lambda x:x[key],reverse=value=='desc')


def resolve(scope,fields,pi_docs,invariants=()):
    from cat_compile_v2 import parse_expr_text, Blocked
    try:
        if not isinstance(scope,str) or not scope.startswith(PREFIX):return None
        spec=json.loads(scope[len(PREFIX):],object_pairs_hook=copy_relation._unique)
        relation=parse_expr_text(spec['relation'])
        if relation.get('op')!='eq' or len(relation['args'])!=2:return None
        post,expression=relation['args']
        if set(expression)=={'ref'}:post,expression=expression,post
        if set(post)!={'ref'} or not post['ref'].startswith('after.'):return None
        target=post['ref'][6:]
        if spec['fields']!=[target] or operator_domain(expression,fields) is None:return None
        source=expression['args'][0]['ref']
        # Reuse only static Scope/type resolution, never a copy certificate.
        same_scope={**spec,'relation':f'after.{target} == {source}'}
        bound=copy_relation.resolve(copy_relation.PREFIX+json.dumps(same_scope),fields,pi_docs,invariants)
        if bound is None or bound[1]!={target:source}:return None
        return bound[0],target,expression
    except (Blocked,ValueError,TypeError,KeyError,AttributeError):return None


def prove(scope,fields,pi_docs,rules,checks,invariants=()):
    binding=resolve(scope,fields,pi_docs,invariants)
    if binding is None:return False
    trigger,target,expected=binding
    rows=[r for r in rules if r['trigger']==trigger]
    if len(rows)!=1 or rows[0]['when']!={'literal':True} or not rows[0]['allowed']:return False
    row=rows[0]
    for n,out in enumerate(row['allowed'],1):
        writes=[(i,w) for i,w in enumerate(out['write'],1) if w['target']==target]
        if len(writes)!=1:return False
        i,w=writes[0];key=f"{row['source_artifact']}#{row['id']}:{n}:{i}:{target}"
        if w['expr']!=expected or checks.get(key,{}).get('result')!='proved':return False
    return True


def verify(scope,fields,pi_docs,tces,checks,rejected,invariants=()):
    binding=resolve(scope,fields,pi_docs,invariants)
    if binding is None:return False
    trigger,target,expected=binding
    rows=[(fm['id'],row) for _,fm,tce in tces for row in tce['rules'] if row['trigger']==trigger]
    if len(rows)!=1:return False
    source,row=rows[0]
    if row['when']!={'literal':True} or not row['allowed']:return False
    for n,out in enumerate(row['allowed'],1):
        projection={}
        for i,w in enumerate(out['write'],1):
            if w['target']!=target:continue
            key=f"{source}#{row['id']}:{n}:{i}:{target}"
            if target in projection or key in rejected or checks.get(key,{}).get('result')!='proved':return False
            projection[target]=w['expr']
        if projection!={target:expected}:return False
    return True


def example(domain,expr):
    """Discriminating finite test witness; never the proof of all lengths."""
    from copy import deepcopy
    collection=_unwrap(domain);element=collection['element'];record=_unwrap(element)
    key=expr['args'][1]['literal'];value=expr['args'][2]['literal']
    a,b=copy_relation._example(element,0),copy_relation._example(element,1)
    if expr['op']=='filter-by':
        # Include a selected row, a contrasting row when possible, and a
        # second selected row. Duplicates are meaningful for sequences.
        a[key]=value
        member=next(m['domain'] for m in record['fields'] if m['id']==key)
        options=[copy_relation._example(member,i) for i in (0,1)]
        different=next((v for v in options if not typed.same(v,value)),value)
        b[key]=different;c=copy_relation._example(element,1);c[key]=value
        items=[a,b,c,deepcopy(a)] if collection['type']=='sequence' else [a,b,c]
    else:
        if a[key]==b[key]:items=[a,b,deepcopy(a)]
        else:
            low,high=(a,b) if a[key]<b[key] else (b,a)
            tie=deepcopy(high);tie[key]=low[key]
            items=[high,low,tie,deepcopy(low)] if value=='asc' else [low,high,tie,deepcopy(high)]
    if collection['type']=='set':
        unique=[]
        for x in items:
            if not any(typed.same(x,y) for y in unique):unique.append(x)
        items=unique
    if not typed.contains(domain,items):raise ValueError('invalid collection witness')
    return items
