"""Exact equality of required structural values; never a finite sample proof.

The initial profile accepts an unconditional direct before/after projection
on one statically bound PI; also a Boolean-controlled optional output, and
explicit same-execution trigger-entry observations. Recursive structural domains
retain typed equality; external execution evidence is not asserted.
"""
from __future__ import annotations
import json
from catlib import peer_binding, semantic_types as typed

TOKEN = '@cat:structural-copy-relation/v1'
PREFIX = 'structural-copy-relation '


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate relation key')
        result[key] = value
    return result


def _supported(domain):
    kind = domain.get('type')
    if kind == 'reference':
        return domain.get('resolved') is True and _supported(domain['of'])
    if kind == 'record':
        return (domain.get('resolved') is True and all(
            f['presence'] in ('required', 'optional', 'absent') and _supported(f['domain'])
            for f in domain['fields']))
    if kind == 'sequence':
        return _supported(domain['element'])
    if kind == 'nullable':
        return _supported(domain['of'])
    if kind == 'enum':
        return bool(domain['values']) and all(type(v) in (bool, int, str, type(None)) for v in domain['values'])
    return kind in ('boolean', 'integer', 'string', 'null')


def _supported_value(domain):
    if domain.get('type') == 'reference':
        return domain.get('resolved') is True and _supported_value(domain['of'])
    if domain.get('type') in ('set','sequence'):
        return _supported_value(domain['element'])
    if domain.get('type')=='nullable':return _supported_value(domain['of'])
    if domain.get('type')=='record':return domain.get('resolved') is True and all(
        f['presence'] in ('required','optional','absent') and _supported_value(f['domain']) for f in domain['fields'])
    return domain.get('type') in ('json', 'instant') or _supported(domain)

def _structural(domain):
    kind = domain.get('type')
    if kind == 'reference':
        return domain.get('resolved') is True and _structural(domain['of'])
    return kind in ('sequence', 'record', 'set', 'json', 'instant')


def resolve(scope, fields, pi_docs, invariants=()):
    """Resolve syntax, exact static Scope, and a total typed equality tuple."""
    from cat_compile_v2 import parse_expr_text, Blocked
    if not isinstance(scope, str) or not scope.startswith(PREFIX) or invariants or any(p.get('constraints') for _,_,p in pi_docs):
        return None
    try:
        spec = json.loads(scope[len(PREFIX):], object_pairs_hook=_unique)
        keys = {'trigger','pi','operation','peer','when','fields','relation'}
        if not isinstance(spec, dict) or set(spec) not in (keys, keys|{'provide'}):
            return None
        if any(type(spec[k]) is not str or not spec[k] for k in spec if k != 'fields'):
            return None
        subjects = spec['fields']
        if (not isinstance(subjects,list) or not subjects or
                any(type(k) is not str or k not in fields for k in subjects) or
                len(set(subjects)) != len(subjects) or
                any(k.startswith('after.') for k in fields)):
            return None
        condition=parse_expr_text(spec['when'])
        trigger = spec['trigger']
        accepts = [(fm['id'], pi, op) for _,fm,pi in pi_docs for op in pi['operations']
                   if op['direction']=='accept' and op.get('trigger')==trigger]
        if len(accepts)!=1:
            return None
        owner, pi, accepted = accepts[0]
        if owner!=spec['pi'] or accepted['id']!=spec['operation'] or pi.get('constraints'):
            return None
        peers=pi['boundary'].get('peers',[pi['boundary']['peer']])
        if peer_binding.match_operation(peers,accepted.get('peer'),spec['peer'])!='static':
            return None
        def presence(op, name):
            override=[r['presence'] for r in pi.get('operation_presence',[])
                      if r['operation']==op and r['field']==name]
            return override[0] if len(override)==1 else fields[name].get('presence','required') if not override else None
        def required(op,name):return presence(op,name)=='required'
        optional=condition!={'literal':True}
        if optional:
            if set(condition)!={'ref'}:return None
            guard=fields.get(condition['ref'],{})
            if guard.get('domain')!={'type':'boolean'} or guard.get('role') not in ('input','state'):return None
            if guard['role']=='input' and (guard.get('source_pi')!=owner or not required(accepted['id'],condition['ref'])):return None
        outputs=[k for k in subjects if fields[k]['role']=='output']
        provided=None
        if outputs:
            # Existing profiles require a static output operation for the whole cut.
            if pi.get('output_frames'):return None
            providers=[(fm['id'],op) for _,fm,p in pi_docs for op in p['operations']
                       if op['direction']=='provide' and op.get('trigger') in (None,trigger)]
            if len(providers)!=1:
                return None
            po,provided=providers[0]
            if (po!=owner or provided['id']!=spec.get('provide') or provided.get('trigger')!=trigger or
                    peer_binding.match_operation(peers,provided.get('peer'),spec['peer'])!='static'):
                return None
        elif 'provide' in spec:
            return None
        for k in subjects:
            field=fields[k]
            if field['role']=='output':
                if field.get('source_pi')!=owner or presence(provided['id'],k)!=('optional' if optional else 'required'):return None
            elif field['role']!='state' or optional:return None
            if not _supported_value(field['domain']):return None
        if not any(_structural(fields[k]['domain']) for k in subjects):return None
        relation=parse_expr_text(spec['relation'])
        atoms=relation['args'] if relation.get('op')=='and' else [relation]
        mapping={}
        for atom in atoms:
            args=atom.get('args',[])
            if atom.get('op')!='eq' or len(args)!=2 or any(set(a)!={'ref'} for a in args):return None
            a,b=[x['ref'] for x in args]
            if b.startswith('after.'):a,b=b,a
            if not a.startswith('after.') or b not in fields:return None
            target=a[len('after.'):]
            if target not in subjects or target in mapping:return None
            source=fields[b]
            if source['role']=='input':
                if source.get('source_pi')!=owner or not required(accepted['id'],b):return None
            elif source['role']=='observation':
                if source.get('available_on')!=[trigger]:return None
                prefix='same-execution-observation '
                origin=source.get('source','')
                if not origin.startswith(prefix):return None
                binding=json.loads(origin[len(prefix):],object_pairs_hook=_unique)
                if set(binding)!={'trigger','pi','operation','peer','cut','source'} or any(binding[k]!=spec[k] for k in ('trigger','pi','operation','peer')) or binding['cut']!='trigger-entry' or not isinstance(binding['source'],str) or not binding['source'].strip():return None
            elif source['role']!='state':return None
            if not typed.same(source['domain'],fields[target]['domain']):return None
            mapping[target]=b
        if set(mapping)!=set(subjects):return None
        return trigger,mapping,condition
    except (Blocked,ValueError,TypeError,KeyError,AttributeError,ArithmeticError):
        return None


def prove(scope, fields, pi_docs, rules, checks, invariants=()):
    resolved=resolve(scope,fields,pi_docs,invariants)
    if resolved is None:return False
    trigger,mapping,condition=resolved
    rows=[r for r in rules if r['trigger']==trigger]
    expected_guards=[condition] if condition=={'literal':True} else [condition,{'op':'not','args':[condition]}]
    if len(rows)!=len(expected_guards) or any(sum(r['when']==g for r in rows)!=1 for g in expected_guards):return False
    for row in rows:
        active=row['when']==condition
        if not row['allowed']:return False
        for n,outcome in enumerate(row['allowed'],1):
            for target,source in mapping.items():
                matches=[(i,w) for i,w in enumerate(outcome['write'],1) if w['target']==target]
                if not active:
                    if matches:return False
                elif not matches:
                    if fields[target]['role']!='state' or target!=source or target not in outcome['unchanged']:return False
                elif len(matches)==1:
                    i,write=matches[0]
                    key=f"{row['source_artifact']}#{row['id']}:{n}:{i}:{target}"
                    if checks.get(key,{}).get('result')!='proved' or write['expr']!={'ref':source}:return False
                else:return False
    return True


def verify(scope, fields, pi_docs, tces, checks, rejected, invariants=()):
    """Independently reconstruct the symbolic projection from original TCE."""
    resolved=resolve(scope,fields,pi_docs,invariants)
    if resolved is None:return False
    trigger,expected,condition=resolved
    candidates=[(fm['id'],r) for _,fm,tce in tces for r in tce['rules'] if r['trigger']==trigger]
    guards=[condition] if condition=={'literal':True} else [condition,{'op':'not','args':[condition]}]
    if len(candidates)!=len(guards) or any(sum(r['when']==g for _,r in candidates)!=1 for g in guards):return False
    for source_id,row in candidates:
        if not row['allowed']:return False
        for n,out in enumerate(row['allowed'],1):
            projection={k:k for k in expected if fields[k]['role']=='state'}
            seen=set()
            for i,write in enumerate(out['write'],1):
                k=write['target']
                if k not in expected:continue
                key=f"{source_id}#{row['id']}:{n}:{i}:{k}"
                expr=write['expr']
                if (k in seen or key in rejected or checks.get(key,{}).get('result')!='proved'
                        or set(expr)!={'ref'}):return False
                seen.add(k);projection[k]=expr['ref']
            if projection!=(expected if row['when']==condition else {}):return False
    return True


def _example(domain, variant=0, empty=False):
    """One concrete test witness, not an abstraction of the value domain."""
    kind=domain['type']
    if kind=='reference':return _example(domain['of'],variant,empty)
    if kind=='record':return {f['id']:_example(f['domain'],variant,empty)
                              for f in domain['fields'] if f['presence']=='required'}
    if kind=='sequence':
        return [] if empty else [_example(domain['element'],0),_example(domain['element'],1)]
    if kind=='set':
        if empty:return []
        a,b=(_example(domain['element'],i) for i in (0,1))
        return [a] if typed.same_in_domain(domain['element'],a,b) else [a,b]
    if kind=='nullable':return None if variant==0 else _example(domain['of'],variant,empty)
    if kind=='json':
        from decimal import Decimal
        return {} if empty else {'amount': Decimal('9007199254740993.125'), 'example':[1,True,None,1]}
    if kind=='instant':
        from catlib.semantic_json_instant import decode_offset_datetime
        return decode_offset_datetime('1970-01-01T00:00:00Z' if empty else '1970-01-02T00:00:00.000000123Z')
    if kind=='null':return None
    if kind=='boolean':return bool(variant)
    if kind=='integer':
        lo,hi=domain.get('min'),domain.get('max')
        base=lo if lo is not None else min(0,hi) if hi is not None else 0
        return base+variant if hi is None else min(base+variant,hi)
    if kind=='string':return str(variant) if domain.get('format','any')!='any' else ('','a')[bool(variant)]
    if kind=='enum':return domain['values'][min(variant,len(domain['values'])-1)]
    raise ValueError('unsupported concrete witness domain')


def witness_values(model,trigger,fields,guard_names,observed,presence):
    """Only select guard-independent concrete values for a proved copy scope.

    The canonical CLI independently checks the Model before selecting vectors.
    This does not claim coverage of lengths or contents; the symbolic theorem
    (not the selected concrete test) establishes the Source relation.
    """
    from cat_compile_v2 import parse_expr_text, used_refs, Blocked
    from catlib import semantic_collection_relation as collection_relation
    copied=set(); operations={}
    try:
        for p in model.get('intrinsic_rule_proofs',[]):
            token=p.get('requirement')
            if token not in (TOKEN,collection_relation.TOKEN) or p.get('status')!='passed':continue
            if p.get('proof_method')!='cat:intrinsic-model/v1' or p.get('verification_contract')!='cat:intrinsic-model/v1':continue
            scope=p['scope']
            prefix=PREFIX if token==TOKEN else collection_relation.PREFIX
            if not scope.startswith(prefix):continue
            spec=json.loads(scope[len(prefix):],object_pairs_hook=_unique)
            if spec['trigger']!=trigger:continue
            if not any(x.get('id')==p['source_artifact'] and x.get('kind')=='domain-spec' and
                       x.get('sha256')==p['source_sha256'] and x.get('process')==model['process']
                       for x in model.get('normative_rule_inputs',[])):continue
            if not any(x.get('id')==p['rule_id'] and x.get('source_artifact')==p['source_artifact'] and
                       x.get('source_sha256')==p['source_sha256'] and x.get('condition')==scope and
                       x.get('requirement')==token and x.get('verification_status')=='intrinsic-proved'
                       for x in model.get('rule_obligations',[])):continue
            expr=parse_expr_text(spec['relation'])
            copied.update(k for k in used_refs(expr,{}) if k in fields)
            if token==collection_relation.TOKEN:
                op=next((x for x in expr['args'] if x.get('op') in collection_relation.OPERATORS),None)
                if op is not None and collection_relation.operator_domain(op,fields) is not None:
                    operations[op['args'][0]['ref']]=op
        if not copied:return {}
        values={}
        for k,f in fields.items():
            if (f['role'] not in ('input','state','observation') or k in guard_names or
                    presence.get(k,'required')!='required' or not _structural(f['domain']) or
                    not _supported_value(f['domain']) or (f['role']=='observation' and (k not in observed or k not in copied))):continue
            sample=(collection_relation.example(f['domain'],operations[k]) if k in operations else
                    _example(f['domain'],0,empty=k not in copied))
            if typed.contains(f['domain'],sample):values[k]=[sample]
        return values
    except (Blocked,ValueError,TypeError,KeyError,AttributeError,ArithmeticError):return {}
