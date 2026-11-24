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


def _independent_real_cells(domain, field, clauses):
    """Reconstruct ordered real cells from Source, not compiler receipts."""
    from fractions import Fraction
    if domain.get('type')!='real':return None
    lo,hi=domain.get('min'),domain.get('max')
    def numeric(v):return type(v) is int or type(v) is float and math.isfinite(v)
    constants=set()
    def mentions(n):return isinstance(n,dict) and (n.get('ref')==field or any(mentions(x) for x in n.get('args',[])))
    def legal(n):
        if not isinstance(n,dict) or n.get('op')=='call':return False
        if not mentions(n):return True
        op=n.get('op');args=n.get('args',[])
        if op in ('and','or','not'):return all(legal(a) for a in args)
        if op not in ('lt','le','gt','ge') or len(args)!=2:return False
        for a,b in (args,args[::-1]):
            if a=={'ref':field} and set(b)=={'literal'} and numeric(b['literal']):
                constants.add(Fraction(b['literal']));return True
        return False
    if not all(legal(c) for c in clauses) or not constants:return None
    if any(x is not None and not numeric(x) for x in (lo,hi)):return None
    lower=Fraction(lo) if lo is not None else None
    upper=Fraction(hi) if hi is not None else None
    if lower is not None and upper is not None and lower>upper:return None
    boundaries=sorted({x for x in constants|{lower,upper} if x is not None
                      and (lower is None or lower<=x) and (upper is None or x<=upper)})
    if not boundaries:return None
    values=[]
    if lower is None:values.append(boundaries[0]//1-1)
    for i,boundary in enumerate(boundaries):
        values.append(int(boundary) if boundary.denominator==1 else float(boundary))
        if i+1==len(boundaries):break
        right=boundaries[i+1]
        whole=boundary//1+1
        if whole<right:values.append(whole)
        else:
            try:rep=float(boundary+(right-boundary)/2)
            except OverflowError:return None
            if not math.isfinite(rep) or not boundary<Fraction(rep)<right:return None
            values.append(rep)
    if upper is None:values.append(-((-boundaries[-1])//1)+1)
    return values if values and len(values)<=LIMIT else None


def _independent_real_reference_cells(names, domains, inputs, current_presence, clauses, definitions):
    """Independently reconstruct exact coupled real-order representatives."""
    from fractions import Fraction
    fields=sorted(x for x in names if domains.get(x,{}).get('type')=='real'
                  and (x not in inputs or current_presence(x)=='required'))
    if not 2<=len(fields)<=3:return {}
    group=set(fields);boundaries=set();pairs=set()
    def numeric(x):return type(x) is int or type(x) is float and math.isfinite(x)
    def legal(expr):
        if not isinstance(expr,dict) or expr.get('op')=='call':return False
        if not (used_refs(expr,definitions)&group):return True
        op,args=expr.get('op'),expr.get('args',[])
        if op in ('and','or','not'):return all(legal(child) for child in args)
        if op not in ('lt','le','gt','ge') or len(args)!=2:return False
        a,b=args
        if set(a)==set(b)=={'ref'} and {a['ref'],b['ref']}<=group:
            if a['ref']!=b['ref']:pairs.add((a['ref'],b['ref']))
            return True
        if set(b)=={'ref'}:a,b=b,a
        if set(a)=={'ref'} and a['ref'] in group and set(b)=={'literal'} and numeric(b['literal']):
            boundaries.add(Fraction(b['literal']));return True
        return False
    if not all(legal(c) for c in clauses) or not pairs:return {}
    limits={}
    for field in fields:
        lo,hi=domains[field].get('min'),domains[field].get('max')
        if any(v is not None and not numeric(v) for v in (lo,hi)):return {}
        limits[field]=tuple(Fraction(v) if v is not None else None for v in (lo,hi))
        boundaries.update(v for v in limits[field] if v is not None)
    cuts=sorted(boundaries);n=len(fields);representatives=[]
    if not cuts:representatives=list(range(n))
    else:
        if any(lo is None for lo,hi in limits.values()):
            representatives.extend(cuts[0]//1-i for i in range(n,0,-1))
        for left,right in zip(cuts,cuts[1:]+[None]):
            representatives.append(int(left) if left.denominator==1 else float(left))
            if right is None:break
            if all((lo is not None and lo>left) or (hi is not None and hi<right)
                   for lo,hi in limits.values()):continue
            low_int=left//1+1
            if low_int+n-1<right:interior=list(range(low_int,low_int+n))
            else:
                try:interior=[float(left+(right-left)*Fraction(i,n+1)) for i in range(1,n+1)]
                except OverflowError:return {}
                if any(not math.isfinite(v) for v in interior):return {}
                if any(not left<Fraction(v)<right for v in interior) or len(set(interior))!=n:return {}
            representatives.extend(interior)
        if any(hi is None for lo,hi in limits.values()):
            top=-((-cuts[-1])//1);representatives.extend(top+i for i in range(1,n+1))
    out={field:[v for v in representatives if (lo is None or Fraction(v)>=lo) and (hi is None or Fraction(v)<=hi)]
         for field,(lo,hi) in limits.items()}
    return out if all(out.values()) else {}


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


def _independent_record_cells(names,domains,roles,inputs,current_presence,clauses,definitions):
    """Independent exact scalar relation projection from normative ASTs."""
    pairs=set()
    def collect(node):
        if node.get('op')=='member':
            pairs.add((node['args'][0]['ref'],node['args'][1]['literal']))
        else:
            for child in node.get('args',[]):collect(child)
    for clause in clauses:collect(clause)
    if not pairs:return {}
    parents={p for p,_ in pairs}
    if not parents<=names:return {}
    scalar_domains={n:domains[n] for n in names-parents}
    scalar_inputs={n:inputs[n] for n in scalar_domains if n in inputs}
    statuses={n:current_presence(n) for n in scalar_inputs}
    mapping={};records={}
    for p in sorted(parents):
        if roles.get(p)!='input' or current_presence(p)!='required':return {}
        shape=domains[p]
        while shape.get('type')=='reference' and shape.get('resolved'):shape=shape['of']
        if shape.get('type')!='record' or not shape.get('resolved'):return {}
        record=[]
        for m in shape['fields']:
            member=m['id']
            if m['presence'] in ('absent','optional'):
                if (p,member) in pairs:return {}
                continue
            if m['presence']!='required':return {}
            domain=m['domain']
            while domain.get('type')=='reference' and domain.get('resolved'):domain=domain['of']
            if domain.get('type') not in ('boolean','integer','real','string','enum'):return {}
            ident='@member:'+p+':'+member
            if ident in domains or ident in scalar_domains:return {}
            mapping[p,member]=ident;record.append((member,ident));scalar_domains[ident]=domain
            scalar_inputs[ident]={};statuses[ident]='required'
        records[p]=record
    if not pairs<=mapping.keys():return {}
    def normalize(node):
        if node.get('op')=='member':return {'ref':mapping[node['args'][0]['ref'],node['args'][1]['literal']]}
        if node.get('ref') in parents or node.get('op')=='call':raise ValueError('opaque record relation')
        if 'args' in node:return dict(node,args=[normalize(x) for x in node['args']])
        return node
    try:predicates=[normalize(c) for c in clauses]
    except (ValueError,KeyError):return {}
    referenced=set().union(*(used_refs(c,definitions) for c in predicates))
    if not referenced<=scalar_domains.keys():return {}
    status=lambda n:statuses[n]
    pair=_independent_integer_pair_values(referenced,scalar_domains,scalar_inputs,status,predicates,definitions)
    ranges={} if pair else _independent_integer_range_values(referenced,scalar_domains,scalar_inputs,status,predicates,definitions)
    strings={n for n in referenced if scalar_domains[n]=={'type':'string'} and statuses.get(n,'required')=='required'}
    eq_values={}
    if 2<=len(strings)<=5:
        literals=set();saw_pair=False
        def allowed_atom(node):
            nonlocal saw_pair
            if not used_refs(node,definitions)&strings:return True
            op=node.get('op');args=node.get('args',[])
            if op in ('and','or','not'):return all(allowed_atom(a) for a in args)
            if op not in ('eq','ne') or len(args)!=2:return False
            if all(set(a)=={'ref'} and a['ref'] in strings for a in args):saw_pair=True;return True
            for ref,value in (args,args[::-1]):
                if set(ref)=={'ref'} and ref['ref'] in strings and set(value)=={'literal'} and isinstance(value['literal'],str):
                    literals.add(value['literal']);return True
            return False
        if all(allowed_atom(p) for p in predicates) and saw_pair:
            cells=[];i=0
            while len(cells)<len(strings):
                token='\x00'*i;i+=1
                if token not in literals:cells.append(token)
            eq_values={n:sorted(literals)+cells for n in strings}
    representatives={}
    for n,d in scalar_domains.items():
        pr=statuses.get(n,'required');v=ranges.get(n) or pair.get(n) or eq_values.get(n)
        if v is None:
            if pr=='absent':v=[types.MISSING]
            elif pr=='undefined':v=[types.UNDEFINED]
            else:
                v=types.finite_values(d)
                if v is not None and pr=='optional':v=[types.MISSING,*v]
        if v is None and n not in referenced:
            if pr=='optional':v=[types.MISSING]
            elif pr=='required':
                if d.get('type')=='integer':v=[min(d.get('max',max(0,d.get('min',0))),max(0,d.get('min',0)))]
                elif d=={'type':'string'}:v=['']
                elif d.get('type')=='real':v=[d.get('min',d.get('max',0))]
        if v is None and pr=='required':
            for derive in (_independent_integer_cells,_independent_string_cells,_independent_real_cells):
                v=derive(d,n,predicates)
                if v is not None:break
        if not v:return {}
        representatives[n]=v if n in referenced else v[:1]
    result={n:representatives[n] for n in names-parents}
    for parent,members in records.items():
        axes=[representatives[i] for _,i in members]
        if math.prod(map(len,axes))>LIMIT:return {}
        concrete=[{m:v for (m,_),v in zip(members,combo)} for combo in itertools.product(*axes)]
        if not all(types.contains(domains[parent],x) for x in concrete):return {}
        result[parent]=concrete
    return result


def _independent_linear_cells(names,domains,inputs,current_presence,clauses,definitions):
    """Derive the complete scalar image and legal preimages from Source.

    Deliberately does not invoke the Compiler partition helper or read its
    receipts. Only the canonical numeric evaluation semantics are shared.
    """
    from fractions import Fraction
    atoms=[]
    def read(node):
        if node.get('op') in ('and','or','not'):
            for arg in node['args']:read(arg)
            return
        if node.get('op') not in ('lt','le','gt','ge'):return
        for term,limit in (node['args'],node['args'][::-1]):
            if (set(limit)=={'literal'} and type(limit['literal']) is int and term.get('op') in ('add','sub')
                    and len(term.get('args',[]))==2 and all(set(v)=={'ref'} for v in term['args'])):
                left,right=(v['ref'] for v in term['args'])
                if left!=right:atoms.append((node,(term['op'],left,right),limit['literal']))
    for c in clauses:read(c)
    if not atoms:return {}
    op,a,b=atoms[0][1];group={a,b}
    if not group<=set(names):return {}
    recognized=[n for n,key,_ in atoms if key==(op,a,b)]
    def allowed(node):
        if node.get('op')=='call':return False
        if not (used_refs(node,definitions)&group):return True
        if node.get('op') in ('and','or','not'):return all(allowed(arg) for arg in node['args'])
        return node in recognized
    if not all(allowed(c) for c in clauses):return {}
    da,db=domains[a],domains[b];kind=da.get('type')
    if kind not in ('real','integer') or db.get('type')!=kind:return {}
    if any(x in inputs and current_presence(x)!='required' for x in group):return {}
    a0,a1=da.get('min'),da.get('max');b0,b1=db.get('min'),db.get('max')
    if any(v is not None and type(v) is not int for v in (a0,a1,b0,b1)):return {}
    if op=='sub':b0,b1=((-b1 if b1 is not None else None),(-b0 if b0 is not None else None))
    low=None if None in (a0,b0) else a0+b0;high=None if None in (a1,b1) else a1+b1
    boundaries={value for _,key,value in atoms if key==(op,a,b)}|{low,high}
    points=sorted(v for v in boundaries if v is not None and (low is None or v>=low) and (high is None or v<=high))
    if points:
        representatives=list(points)
        for l,r in zip(points,points[1:]):
            if r-l>=2:representatives.append(l+1)
            elif kind=='real':representatives.append(Fraction(l+r,2))
        if low is None:representatives.append(points[0]-1)
        if high is None:representatives.append(points[-1]+1)
    else:representatives=[0]
    out={a:set(),b:set()}
    for value in representatives:
        # Intersect x's original interval with the reflected y interval
        # at the selected total. Choose its lower endpoint when it exists.
        x=a0
        if b1 is not None and (x is None or value-b1>x):x=value-b1
        ceiling=a1
        if b0 is not None and (ceiling is None or value-b0<ceiling):ceiling=value-b0
        if x is None:x=0 if ceiling is None or ceiling>=0 else ceiling
        if ceiling is not None and x>ceiling:return {}
        y=value-x if op=='add' else x-value
        for field,v in ((a,x),(b,y)):
            exact=Fraction(v)
            try:representative=int(exact) if exact.denominator==1 else float(exact)
            except OverflowError:return {}
            if Fraction(representative)!=exact or not types.contains(domains[field],representative):return {}
            out[field].add(representative)
    return {field:sorted(vals) for field,vals in out.items()} if all(out.values()) else {}


def audit(process,pi_docs,tces,roles,domains,domain_rule=None,state_invariants=None):
    state_invariants=state_invariants or {}
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
        has_pi_constraints=bool(constraints)
        constraints.extend(state_invariants.values())
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
        projected=_independent_record_cells(names,domains,roles,inputs,current_presence,clauses,definitions)
        integer_pair=_independent_integer_pair_values(names,domains,inputs,current_presence,clauses,definitions)
        integer_range=({} if integer_pair else _independent_integer_range_values(
            names,domains,inputs,current_presence,clauses,definitions))
        real_range=_independent_real_reference_cells(names,domains,inputs,current_presence,clauses,definitions)
        linear_range=_independent_linear_cells(names,domains,inputs,current_presence,clauses,definitions)
        for field in sorted(names):
            if projected:
                dimensions.append(projected[field]);partition_fields.append(field);partition_kinds.add('record_member');continue
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
            if field in linear_range:
                values=linear_range[field]
                partition_fields.append(field)
                partition_kinds.add('linear_order')
            if field in real_range:
                values=real_range[field]
                partition_fields.append(field)
                partition_kinds.add('real_ref_range')
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
            if values is None and (field not in inputs or current_presence(field)=='required'):
                values=_independent_real_cells(domains[field],field,clauses)
                if values is not None:
                    partition_fields.append(field)
                    partition_kinds.add('real')
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
                           'excluded_by_pi_constraints':has_pi_constraints}
            continue
        receipt={'result':'unproven' if unknown else 'conflict' if overlaps else 'uncovered' if gaps else 'proved',
                 'guard_refs':sorted(names),'unreachable_rules':unvisited,
                 'uncovered_count':gaps if not partition_fields else None,
                 'overlap_count':overlaps if not partition_fields else None,
                 'uncovered':uncovered_examples,'overlaps':overlap_examples,
                 'excluded_by_pi_constraints':has_pi_constraints}
        if state_invariants:receipt['guard_invariant_rule_ids']=sorted(state_invariants)
        if partition_fields:
            method=('integer-literal-partition/v1' if partition_kinds=={'integer'}
                    else 'string-literal-equality-partition/v1' if partition_kinds=={'string'}
                    else 'real-literal-order-partition/v1' if partition_kinds=={'real'}
                    else 'real-reference-order-partition/v1' if partition_kinds=={'real_ref_range'}
                    else 'two-reference-linear-order-partition/v1' if partition_kinds=={'linear_order'}
                    else 'required-record-member-partition/v1' if partition_kinds=={'record_member'}
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
