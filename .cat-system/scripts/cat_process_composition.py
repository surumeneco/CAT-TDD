#!/usr/bin/env python3
"""Cross-Process typed composition check, independent from local Process closure.

Bindings are explicit. No edge, operation, field or effect is invented from
similar names. Unmapped external peers and unproved effects stay inconclusive.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from catlib import semantic_types

class CompositionError(ValueError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def _load(path):
    return json.loads(Path(path).read_bytes())

def _bounds(model):
    out=[]
    for bound in model.get('pi_boundaries',[]):
        peers=bound.get('peers',[bound.get('peer')])
        if not isinstance(peers,list) or any(not isinstance(x,str) or not x for x in peers):
            raise CompositionError('invalid PI peer specification')
        for peer in peers:
            directions=('send','receive') if bound['direction']=='bidirectional' else (bound['direction'],)
            for direction in directions:
                out.append({'source_process':model['process'],'source_pi':bound['artifact'],
                            'target_process':peer,'direction':direction})
    return out

def _bound(model,pi,peer,direction):
    return any(x['source_pi']==pi and x['target_process']==peer and
               x['direction']==direction for x in _bounds(model))

def _field(model,id_,role,pi):
    entries=[f for f in model.get('fields',[])
             if f.get('id')==id_ and f.get('role')==role and f.get('source_pi')==pi]
    if len(entries)!=1:
        raise CompositionError('missing/ambiguous '+role+' field '+id_+
                               ' owned by PI '+pi+' in '+model['process'])
    return entries[0]

def _operation(model,id_,source_pi,role):
    return any(x['id']==id_ and x.get('source_pi')==source_pi and x['direction']==role
               for x in model.get('pi_operations',[]))

def _unresolved_domain(domain):
    if not isinstance(domain,dict):
        return False  # Legacy scalar collection element names.
    kind=domain.get('type')
    if kind in (None,'unknown'):
        return True
    if kind=='reference':
        return not domain.get('resolved') or _unresolved_domain(domain.get('of'))
    if kind=='record':
        return domain.get('resolved') is not True or any(
            _unresolved_domain(f.get('domain')) for f in domain.get('fields',[]))
    if kind in ('set','sequence'):
        return _unresolved_domain(domain.get('element'))
    if kind=='nullable':
        return _unresolved_domain(domain.get('of'))
    if kind=='union':
        return any(_unresolved_domain(x) for x in domain.get('variants',[]))
    return False


def _type_subset(source,target):
    """True only for proved inclusion; False for a counterexample; None if unknown."""
    if _unresolved_domain(source) or _unresolved_domain(target):
        return None
    if source==target:
        return True
    if isinstance(source,dict) and source.get('type')=='reference':
        return _type_subset(source['of'],target)
    if isinstance(target,dict) and target.get('type')=='reference':
        return _type_subset(source,target['of'])
    if isinstance(source,str):
        source={'type':source}
    if isinstance(target,str):
        target={'type':target}
    a=source.get('type');b=target.get('type')
    if a=='union':
        results=[_type_subset(x,target) for x in source['variants']]
        return False if False in results else (True if all(x is True for x in results) else None)
    if b=='union':
        results=[_type_subset(source,x) for x in target['variants']]
        if True in results:return True
        # A source can be covered by a union without fitting any one branch.
        # Only exhaustive finite evidence may establish that relation.
        values=semantic_types.finite_values(source,max_values=4096)
        if values is None:return None
        try:return all(semantic_types.contains(target,value) for value in values)
        except semantic_types.DomainError:return None
    if b=='nullable':
        if a=='null':return True
        return _type_subset(source['of'],target['of']) if a=='nullable' else _type_subset(source,target['of'])
    if a=='nullable':
        if b=='null':return _type_subset(source['of'],target)
        return False  # Null cannot inhabit any other non-nullable, non-union target.
    if a=='enum':
        if b=='enum':
            return all(any(semantic_types.same(v,x) for x in target['values'])
                       for v in source['values'])
        try:
            return all(semantic_types.contains(target,v) for v in source['values'])
        except semantic_types.DomainError:
            return None
    if a==b and a in ('integer','real'):
        return ((target.get('min') is None or (source.get('min') is not None
                                               and source['min']>=target['min']))
                and (target.get('max') is None or (source.get('max') is not None
                                                   and source['max']<=target['max'])))
    if a==b=='string':
        return target.get('format','any')=='any'
    if a in ('set','sequence') and b in ('set','sequence'):
        if a=='sequence' and b=='set':
            return False  # Sequence permits duplicates; Set forbids duplicates.
        return _type_subset(source['element'],target['element'])
    if a==b=='record':
        # Records are closed: omitting a declaration means that key is always
        # missing. Presence is a separate state dimension from Domain.
        states={'required':{'value'},'optional':{'missing','value'},
                'absent':{'missing'},'undefined':{'undefined'}}
        left=source.get('fields',[]);right=target.get('fields',[])
        mine={x['id']:x for x in left}
        theirs={x['id']:x for x in right}
        if len(mine)!=len(left) or len(theirs)!=len(right):
            return None  # Malformed duplicate declarations have no proof.
        unknown=False
        for field_id in sorted(set(mine)|set(theirs)):
            producer=mine.get(field_id)
            consumer=theirs.get(field_id)
            producer_states=(states.get(producer.get('presence','required'))
                             if producer else {'missing'})
            consumer_states=(states.get(consumer.get('presence','required'))
                             if consumer else {'missing'})
            if producer_states is None or consumer_states is None:
                return None
            if not producer_states.issubset(consumer_states):
                return False  # Counterexample: key absent/undefined/value.
            if 'value' in producer_states:
                # Presence already guarantees a value on both boundaries.
                # Structural Domain inclusion is still required for that case.
                if producer is None or consumer is None:
                    return False
                result=_type_subset(producer['domain'],consumer['domain'])
                if result is False:
                    return False
                if result is None:
                    unknown=True
        return None if unknown else True
    if a=='integer' and b=='real':
        return None  # Unbounded integers need a representability proof.
    if a!=b:
        return False
    return None


def _link(binding,models):
    source=models.get(binding['source_process'])
    target=models.get(binding['target_process'])
    if source is None or target is None:raise CompositionError('binding targets a missing Process')
    a=binding['source_pi'];b=binding['target_pi']
    if not _bound(source,a,target['process'],'send'):
        raise CompositionError('source PI has no declared send boundary')
    if not _bound(target,b,source['process'],'receive'):
        raise CompositionError('target PI has no declared receive boundary')
    source_op=binding.get('source_operation')
    target_op=binding.get('target_operation')
    if source_op is None or target_op is None:
        raise CompositionError('connection must name both source and target operations')
    if not _operation(source,source_op,a,'provide'):
        raise CompositionError('source operation is not provided by its PI')
    if not _operation(target,target_op,b,'accept'):
        raise CompositionError('target operation is not accepted by its PI')
    fields=binding.get('field_links')
    if not isinstance(fields,list) or not fields:
        raise CompositionError('connection requires typed field links')
    seen=set();checks=[]
    for mapping in fields:
        if not isinstance(mapping,dict) or set(mapping)!={'source_field','target_field'}:
            raise CompositionError('field link must identify both endpoints')
        pair=(mapping['source_field'],mapping['target_field'])
        if pair in seen:raise CompositionError('duplicate field binding')
        seen.add(pair)
        f=_field(source,pair[0],'output',a)
        t=_field(target,pair[1],'input',b)
        inclusion=_type_subset(f['domain'],t['domain'])
        f_presence=f.get('presence','required')
        t_presence=t.get('presence','required')
        # Presence is independent of type/nullability: a producer's possible
        # states must be accepted by the consumer, including missing/undefined.
        states={'required':{'value'},'optional':{'missing','value'},
                'absent':{'missing'},'undefined':{'undefined'}}
        if f_presence not in states or t_presence not in states:
            raise CompositionError('unsupported boundary presence')
        presences_ok=states[f_presence].issubset(states[t_presence])
        if inclusion is False or not presences_ok:
            raise CompositionError('typed/presence mismatch on '+pair[0]+' -> '+pair[1])
        proof='matched' if inclusion is True else 'inconclusive'
        checks.append({'source_field':f['id'],'target_field':t['id'],
                       'type':f['domain'],'target_type':t['domain'],
                       'presence':(f_presence,t_presence),'status':proof})
    return {'source_process':source['process'],'target_process':target['process'],
            'source_pi':a,'target_pi':b,'source_operation':source_op,
            'target_operation':target_op,'field_links':checks,
            'status':'structurally-matched' if all(c['status']=='matched' for c in checks) else 'inconclusive',
            'external_effects_verified':False}

def compose(model_paths,binding_path=None):
    if len(model_paths)<2:raise CompositionError('composition requires >=2 Processes')
    models={};hashes={}
    for path in model_paths:
        raw=Path(path).read_bytes();model=json.loads(raw)
        pid=model.get('process')
        if not isinstance(pid,str) or not pid or pid in models:
            raise CompositionError('duplicate or missing Process ID')
        models[pid]=model;hashes[pid]=digest(raw)
    binding={'schema':'cat-process-bindings/v1','links':[]}
    binding_hash=None
    if binding_path is not None:
        raw=Path(binding_path).read_bytes();binding=json.loads(raw)
        binding_hash=digest(raw)
    if binding.get('schema')!='cat-process-bindings/v1' or not isinstance(binding.get('links'),list):
        raise CompositionError('invalid composition binding schema')
    if binding.get('model_sha256',hashes)!=hashes:
        raise CompositionError('composition model hash mismatch')
    edges=[]
    for model in models.values():edges.extend(_bounds(model))
    unresolved=[];proven=[];seen=set()
    for link in binding['links']:
        if not isinstance(link,dict):
            raise CompositionError('link record required')
        key=(link.get('source_process'),link.get('source_pi'),link.get('target_process'),
             link.get('target_pi'),link.get('source_operation'),link.get('target_operation'))
        if key in seen:raise CompositionError('duplicate connection link')
        seen.add(key)
        proven.append(_link(link,models))
    # Each validated link discharges both the sender's outgoing declaration
    # and the receiver's incoming declaration; neither proves external effects.
    bound_pairs=set()
    for x in proven:
        if x['status']!='structurally-matched':
            continue
        bound_pairs.add((x['source_process'],x['source_pi'],x['target_process'],'send'))
        bound_pairs.add((x['target_process'],x['target_pi'],x['source_process'],'receive'))
    for edge in edges:
        key=edge['source_process'],edge['source_pi'],edge['target_process'],edge['direction']
        if edge['target_process'] not in models:
            unresolved.append({**edge,'reason':'peer outside assembled Process set'})
        elif key not in bound_pairs:
            unresolved.append({**edge,'reason':'PI connection/effect lacks explicit binding'})
    unproved_local=[]
    for p,model in models.items():
        if model.get('status')!='confirmed' or model.get('coverage_requirement')!='closed' or model.get('unverified_rule_ids') or model.get('unresolved_domains') or model.get('presence_unproven'):
            unproved_local.append(p)
    # This proves typed links only. External effects, ordering and interleaving
    # are never proved merely by matching source/target schemas.
    statuses='inconclusive' if unresolved or unproved_local or any(not x['external_effects_verified'] for x in proven) else 'passed'
    return {'schema':'cat-process-composition/v1','status':statuses,
            'model_sha256':hashes,'binding_sha256':binding_hash,
            'bindings':proven,'unresolved_connections':unresolved,
            'unproved_local_processes':unproved_local,
            'reason':'typed connections match where bound; cross-Process effect/interleaving proof still required'
                     if statuses=='inconclusive' else 'all declared boundaries and external effects proved'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',action='append',required=True)
    p.add_argument('--binding')
    p.add_argument('--output',required=True)
    a=p.parse_args(argv)
    try:
        result=compose(a.model,a.binding)
        path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'path':str(path)},ensure_ascii=False))
        return 0
    except (CompositionError,ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
