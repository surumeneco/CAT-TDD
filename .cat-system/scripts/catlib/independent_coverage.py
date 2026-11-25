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
from catlib import semantic_json_instant as json_time
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


def _independent_sequence_lengths(domain, field, clauses):
    if domain.get('type')!='sequence':return None
    constants=set()
    def legal(node):
        if node.get('op')=='call':return False
        if field not in used_refs(node,{}):return True
        op=node.get('op');args=node.get('args',[])
        if op in ('and','or','not'):return all(legal(x) for x in args)
        if op not in ('eq','ne','lt','le','gt','ge') or len(args)!=2:return False
        for a,b in (args,args[::-1]):
            if a=={'op':'length','args':[{'ref':field}]} and set(b)=={'literal'} and type(b['literal']) is int:
                constants.add(b['literal']);return True
        return False
    if not all(legal(x) for x in clauses) or not constants:return None
    lengths={0}
    for n in constants:lengths.update(x for x in (n-1,n,n+1) if x>=0)
    if max(lengths)>4096 or sum(lengths)>16384:return None
    from catlib.semantic_structural_copy import _example
    try:
        value=_example(domain['element'])
        if not types.contains(domain['element'],value):return None
        return [[value]*n for n in sorted(lengths)]
    except (ValueError,TypeError,KeyError,IndexError,RecursionError):return None

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


def independent_reference_palette(names,clauses,extra_literals=(),require_pair=True):
    """Derive literal-fixed equality classes independently of Compiler cells."""
    group=set(names)
    if not 1<=len(group)<=5:return None
    fixed=set(extra_literals);pairs=set()
    def atoms(n):
        op=n.get('op');args=n.get('args',[])
        if op=='call':raise ValueError('opaque call')
        if op in ('and','or','not'):
            for child in args:yield from atoms(child)
        else:yield n
    def has_call(n):return n.get('op')=='call' or any(has_call(a) for a in n.get('args',[]))
    try:
        for clause in clauses:
            if has_call(clause):return None
            for atom in atoms(clause):
                if not used_refs(atom,{})&group:continue
                args=atom.get('args',[])
                if atom.get('op') not in ('eq','ne') or len(args)!=2:return None
                terms=[]
                for term in args:
                    if set(term)=={'ref'} and term['ref'] in group:terms.append(('ref',term['ref']))
                    elif set(term)=={'literal'} and type(term['literal']) is str:terms.append(('literal',term['literal']))
                    else:return None
                if terms[0][0]==terms[1][0]=='ref' and terms[0][1]!=terms[1][1]:pairs.add(tuple(terms))
                fixed.update(v for kind,v in terms if kind=='literal')
        if require_pair and not pairs:return None
        fresh=[];index=0
        while len(fresh)<len(group):
            candidate='\x00'*index;index+=1
            if candidate not in fixed:fresh.append(candidate)
        return sorted(fixed)+fresh
    except (ValueError,KeyError,TypeError):return None


def _independent_nullable_reference_cells(names,domains,inputs,current_presence,clauses):
    """Independently reconstruct connected components and fixed equality classes."""
    eligible={}
    for n in names:
        domain=domains.get(n,{})
        d=domain.get('of',{}) if domain.get('type')=='nullable' else domain
        if (n not in inputs or current_presence(n)=='required') and (d=={'type':'string'} or d.get('type')=='integer' and set(d)<={'type','min','max'}):
            eligible[n]=d
    groups=[{n} for n in sorted(eligible)];bad=set();literals={n:set() for n in eligible}
    def atoms(node):
        if node.get('op')=='call':raise ValueError('opaque call')
        if node.get('op') in ('and','or','not'):
            for child in node.get('args',[]):yield from atoms(child)
        else:yield node
    def call_present(n):return n.get('op')=='call' or any(call_present(a) for a in n.get('args',[]))
    if any(call_present(c) for c in clauses):return {}
    for clause in clauses:
        for atom in atoms(clause):
            refs=used_refs(atom,{})&eligible.keys()
            if not refs:continue
            args=atom.get('args',[])
            if atom.get('op') not in ('eq','ne') or len(args)!=2:
                bad.update(refs);continue
            if all(set(a)=={'ref'} and a['ref'] in eligible for a in args) and eligible[args[0]['ref']]==eligible[args[1]['ref']]:
                merged=set().union(*(g for g in groups if g&refs))
                groups=[g for g in groups if not g&refs]+[merged];continue
            found=False
            for term,constant in (args,args[::-1]):
                if set(term)=={'ref'} and term['ref'] in eligible and set(constant)=={'literal'}:
                    n=term['ref'];val=constant['literal'];d=eligible[n]
                    if val is None:found=True;break
                    if type(val) is (str if d['type']=='string' else int):
                        literals[n].add(val);found=True;break
            if not found:bad.update(refs)
    cells={}
    for group in groups:
        if not 1<=len(group)<=5 or bad&group or not any(domains[n]['type']=='nullable' for n in group):continue
        if len(group)==1 and not literals[next(iter(group))]:continue
        d=eligible[min(group)];fixed=set().union(*(literals[n] for n in group));fresh=[]
        if d['type']=='string':
            i=0
            while len(fresh)<len(group):
                v='\x00'*i;i+=1
                if v not in fixed:fresh.append(v)
        else:
            fixed={v for v in fixed if types.contains(d,v)}
            lower,upper=d.get('min'),d.get('max')
            start=lower if lower is not None else upper if upper is not None else 0
            step=-1 if lower is None and upper is not None else 1
            for i in itertools.count():
                v=start+i*step
                if not types.contains(d,v) or len(fresh)==len(group):break
                if v not in fixed:fresh.append(v)
        values=sorted(fixed)+fresh
        if not values or len(values)>LIMIT:continue
        for n in group:cells[n]=([None]+values if domains[n]['type']=='nullable' else list(values))
    return cells


def _finite_truth_tables(names,dimensions,clauses,definitions):
    """Recompute bounded predicate truth tables from independent Source ASTs.

    Table entries can be undefined. An undefined entry is relevant only when
    reached by the normal ordered constraint and Guard evaluation, not merely
    because it exists in a projected subspace excluded by prior constraints.
    """
    from operator import itemgetter
    n=math.prod(map(len,dimensions))
    if n>2_000_000 or n*len(clauses)>64_000_000:return None
    if any(any(x is _PRESENT_CLASS for x in dim) for dim in dimensions):return None
    total=0;leaves=0
    def describe(expr):
        nonlocal total,leaves
        deps=used_refs(expr,definitions)
        if not deps<=set(names):raise ValueError('unknown Source dependency')
        pos=tuple(i for i,name in enumerate(names) if name in deps)
        axes=[range(len(dimensions[i])) for i in pos]
        size=math.prod(map(len,axes))
        if size>LIMIT:
            op=expr.get('op')
            if op not in ('and','or','not'):raise ValueError('large atomic Source predicate')
            return (op,[describe(child) for child in expr['args']])
        total+=size;leaves+=1
        if total>1_000_000 or n*leaves>64_000_000:raise ValueError('Source proof budget exceeded')
        return ('table',(expr,pos,axes))
    try:plans=[describe(expr) for expr in clauses]
    except ValueError:return None
    def table(expr,pos,axes):
        values={}
        for key in itertools.product(*axes):
            env={names[i]:dimensions[i][j] for i,j in zip(pos,key)}
            try:
                value=eval_expr(expr,env,definitions)
                values[key]=value if type(value) is bool else None
            except (Blocked,TypeError,ValueError,KeyError):values[key]=None
        pick=itemgetter(*pos) if len(pos)>1 else (lambda row:(row[pos[0]],)) if pos else (lambda row:())
        def evaluate(row):
            value=values[pick(row)]
            if value is None:raise Blocked('undefined Source predicate')
            return value
        return evaluate
    def compile_plan(plan):
        op,body=plan
        if op=='table':return table(*body)
        children=[compile_plan(child) for child in body]
        if op=='and':return lambda row:all(child(row) for child in children)
        if op=='or':return lambda row:any(child(row) for child in children)
        return lambda row:not children[0](row)
    return [compile_plan(plan) for plan in plans]


def _independent_null_cells(domain,field,clauses):
    if domain!={'type':'nullable','of':{'type':'string'}}:return None
    found=False
    def audit(node):
        nonlocal found
        if node.get('op')=='call':return False
        args=node.get('args',[])
        if node.get('op') in ('eq','ne') and len(args)==2:
            for a,b in ((args[0],args[1]),(args[1],args[0])):
                if a=={'ref':field} and b=={'literal':None}:
                    found=True;return True
        if node.get('ref')==field:return False
        # A reference below any other non-Boolean operation is outside
        # this exact fragment, even when an inner null comparison exists.
        if node.get('op') not in ('and','or','not'):
            if field in used_refs(node,{}):return False
        return all(audit(arg) for arg in args)
    def opaque(node):return node.get('op')=='call' or any(opaque(a) for a in node.get('args',[]))
    if any(opaque(c) for c in clauses):return None
    return [None,''] if all(audit(c) for c in clauses) and found else None


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
            if domain.get('type') not in ('boolean','integer','real','string','enum') and not (domain.get('type') in ('json','instant') and (p,member) not in pairs):return {}
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
                elif d.get('type')=='json':v=[{} if d['root']=='object' else None]
                elif d.get('type')=='instant':v=[json_time.decode_offset_datetime('1970-01-01T00:00:00Z')]
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


def audit(process,pi_docs,tces,roles,domains,domain_rule=None,state_invariants=None,observation_relations=None):
    state_invariants=state_invariants or {}
    observation_relations=observation_relations or {}
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

    # Independently reconstruct explicit output-cut semantics from PI/TCE
    # Source. The Compiler's derived frame and receipt are not consulted.
    from catlib.output_frame_contract import declarations, validate_declarations
    explicit=declarations(pi_docs)
    source_fields={k:{'role':'output','source_pi':v['owner']} for k,v in outputs.items()}
    source_fields.update({k:{'role':'input','source_pi':v['owner']} for k,v in inputs.items()})
    try:validate_declarations(explicit,source_fields,operations,overrides,rules,process['triggers'])
    except ValueError as exc:raise Blocked(str(exc)) from exc
    explicit_owners={row['source_pi'] for row in explicit}
    explicit_outputs={k:v for k,v in outputs.items() if v['owner'] in explicit_owners}
    outputs={k:v for k,v in outputs.items() if v['owner'] not in explicit_owners}
    legacy_operations=[op for op in operations if op['source_pi'] not in explicit_owners]
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
        trigger_observations=observation_relations.get(ident,{})
        constraints.extend(trigger_observations.values())
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
        raw_count=1
        if integer_pair:
            for field in names:
                pr=current_presence(field) if field in inputs else 'required'
                if pr in ('absent','undefined'):continue
                vals=types.finite_values(domains[field])
                if vals is not None:raw_count*=len(vals)+(1 if pr=='optional' else 0)
        real_range=_independent_real_reference_cells(names,domains,inputs,current_presence,clauses,definitions)
        linear_range=_independent_linear_cells(names,domains,inputs,current_presence,clauses,definitions)
        string_group={k for k in names if domains.get(k)=={'type':'string'}
                      and (k not in inputs or current_presence(k)=='required')}
        string_palette=independent_reference_palette(string_group,clauses) if len(string_group)>=2 else None
        nullable_cells=_independent_nullable_reference_cells(names,domains,inputs,current_presence,clauses)
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
            if string_palette is not None and field in string_group:
                values=string_palette;partition_fields.append(field);partition_kinds.add('string_ref')
            if field in nullable_cells:
                values=nullable_cells[field]
                if field not in partition_fields:partition_fields.append(field)
                partition_kinds.add('nullable_ref_equality')
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
                values=_independent_null_cells(domains[field],field,clauses)
                if values is not None:
                    partition_fields.append(field)
                    partition_kinds.add('nullable_string_null')
            if values is None and (field not in inputs or current_presence(field)=='required'):
                values=_independent_real_cells(domains[field],field,clauses)
                if values is not None:
                    partition_fields.append(field)
                    partition_kinds.add('real')
            if values is None and (field not in inputs or current_presence(field)=='required'):
                values=_independent_sequence_lengths(domains[field],field,clauses)
                if values is not None:
                    partition_fields.append(field)
                    partition_kinds.add('sequence_length')
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
            if field in integer_pair and (values is None or raw_count>LIMIT):
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
        size=math.prod(map(len,dimensions))
        table=(_finite_truth_tables(sorted(names),dimensions,clauses,definitions)
               if possible and size>LIMIT else None)
        masks=None
        if possible and size>LIMIT and table is None and not any(
                any(v is _PRESENT_CLASS for v in dim) for dim in dimensions):
            # Use the same pure expression primitive on independently rebuilt
            # Source partitions, not the Compiler's masks, outcomes or receipts.
            from catlib.finite_truth_masks import truth_masks
            masks=truth_masks(sorted(names),dimensions,constraints,[r['when'] for r in applicable],
                              definitions,eval_expr,used_refs,Blocked)
        if not possible or (size>LIMIT and table is None and masks is None):
            result[ident]={'result':'unproven','unreachable_rules':sorted(r['id'] for r in applicable)}
            continue
        gaps=overlaps=0;visited=set();unknown=False
        admissible=0
        uncovered_examples=[];overlap_examples=[]
        def snapshot(env):
            def transport(value):
                if type(value) is json_time.InstantValue:return json_time.encode_instant_transport(value)
                if isinstance(value,dict):return {k:transport(v) for k,v in value.items()}
                if isinstance(value,list):return [transport(v) for v in value]
                return value
            return {name:({'$cat_presence':'missing'} if value is types.MISSING else
                          {'$cat_presence':'undefined'} if value is types.UNDEFINED else
                          {'$cat_presence':'present'} if value is _PRESENT_CLASS else transport(value))
                    for name,value in env.items()}
        ordered=sorted(names)
        if masks is not None:
            from catlib.finite_truth_masks import row_indices, first_indices
            accepted,regions=masks
            admissible=accepted.bit_count();covered=overlap=0
            for rule,region in zip(applicable,regions):
                if region:visited.add(rule['id'])
                overlap|=covered&region;covered|=region
            uncovered=accepted&~covered
            gaps=uncovered.bit_count();overlaps=overlap.bit_count()
            def env_at(i):return {k:d[j] for k,d,j in zip(ordered,dimensions,row_indices(i,dimensions))}
            uncovered_examples=[snapshot(env_at(i)) for i in first_indices(uncovered,64)]
            overlap_examples=[{'state':snapshot(env_at(i)),
                               'rules':[r['id'] for r,region in zip(applicable,regions) if (region>>i)&1]}
                              for i in first_indices(overlap,16)]
        rows=(() if masks is not None else
              itertools.product(*(range(len(d)) for d in dimensions)) if table is not None
              else itertools.product(*dimensions))
        for items in rows:
            env=None if table is not None else dict(zip(ordered,items))
            try:
                if table is not None:
                    if not all(fn(items) for fn in table[:len(constraints)]):continue
                    admissible+=1
                    hit=[r['id'] for r,fn in zip(applicable,table[len(constraints):]) if fn(items)]
                else:
                    if not all(eval_expr(c,env,definitions) for c in constraints):continue
                    admissible+=1
                    hit=[r['id'] for r in applicable if eval_expr(r['when'],env,definitions)]
            except (Blocked,TypeError,ValueError,KeyError):
                unknown=True;break
            if (not hit or len(hit)>1) and env is None:
                env={k:d[i] for k,d,i in zip(ordered,dimensions,items)}
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
        if trigger_observations:receipt['observation_relation_rule_ids']=sorted(trigger_observations)
        if partition_fields:
            method=('integer-literal-partition/v1' if partition_kinds=={'integer'}
                    else 'string-literal-equality-partition/v1' if partition_kinds=={'string'}
                    else 'string-reference-equality-partition/v1' if partition_kinds=={'string_ref'}
                    else 'nullable-string-null-partition/v1' if partition_kinds=={'nullable_string_null'}
                    else 'nullable-reference-equality-partition/v1' if partition_kinds=={'nullable_ref_equality'}
                    else 'sequence-length-literal-partition/v1' if partition_kinds=={'sequence_length'}
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
            providers=[op for op in legacy_operations if op['direction']=='provide'
                       and (op.get('trigger') is None or op['trigger']==ident)]
            # Derive each owning PI's result frame from Source. Legacy direct
            # output semantics are retained if no scoped Presence is declared.
            needs_provider=(bool(output_special) or any(ov['field'] in outputs for ov in overrides))
            grouped={op['source_pi']:op for op in providers}
            valid=(needs_provider and bool(providers) and len(grouped)==len(providers)
                   and (len(providers)==1 or all(op.get('trigger')==ident for op in providers)))
            if valid:
                for ov in overrides:
                    info=outputs.get(ov['field'])
                    op=grouped.get(info['owner']) if info is not None else None
                    if op is None or ov['operation']==op['id']:
                        continue
                    matches=[item for item in operations if item['id']==ov['operation']
                             and item['source_pi']==op['source_pi']]
                    if (len(matches)!=1 or matches[0]['direction']!='provide'
                            or matches[0].get('trigger') in (None,ident)):
                        valid=False
            # A Trigger without a provider is an empty frame only when all
            # output owners have explicitly Trigger-bound provider inventory.
            owners={info['owner'] for info in outputs.values()}
            scoped={op['source_pi'] for op in legacy_operations if op['direction']=='provide'
                    and op.get('trigger') is not None}
            inactive=needs_provider and not providers and owners<=scoped
            frames=grouped if valid or inactive else None
            if frames is not None:
                covered_owners.update(frames)
            scoped_outputs=(outputs if frames is None else {
                field:info for field,info in outputs.items() if info['owner'] in frames})
            if output_special and frames is None:
                output_ok=False
                output_unproved.update(output_special)
            for rule in applicable:
                for outcome in rule['allowed']:
                    emitted={x['target'] for x in outcome['write']}
                    if frames is not None:
                        unowned=emitted & (outputs.keys()-scoped_outputs.keys())
                        if unowned:
                            output_ok=False
                            output_unproved.update(unowned)
                    for field,info in scoped_outputs.items():
                        ps=([ov['presence'] for ov in overrides
                             if ov['field']==field and ov['operation']==frames[info['owner']]['id']]
                            if frames is not None else [])
                        presence=ps[0] if ps else info['presence']
                        if (presence=='undefined' or (presence=='required' and field not in emitted)
                                or (presence=='absent' and field in emitted)):
                            output_ok=False
                            output_unproved.add(field)
    for rule in rules:
        for n,outcome in enumerate(rule['allowed'],1):
            selected={row['source_pi']:row['operation'] for row in explicit
                      if (row['trigger'],row['rule'],row['outcome'])==(rule['trigger'],rule['id'],n)}
            writes={w['target'] for w in outcome['write']}
            for field,info in explicit_outputs.items():
                operation=selected.get(info['owner'])
                presence='absent'
                if operation is not None:
                    matched=[ov['presence'] for ov in overrides if ov['field']==field and ov['operation']==operation and ov['source_pi']==info['owner']]
                    presence=matched[0] if len(matched)==1 else info['presence'] if not matched else 'undefined'
                if presence=='undefined' or (presence=='required' and field not in writes) or (presence=='absent' and field in writes):
                    output_ok=False
                    output_unproved.add(field)
    orphaned={field for field in output_special
              if outputs[field]['owner'] not in covered_owners}
    if orphaned:
        output_ok=False
        output_unproved.update(orphaned)
    return {'triggers':result,'output_presence_proved':output_ok,
            'unproved_output_fields':sorted(output_unproved)}
