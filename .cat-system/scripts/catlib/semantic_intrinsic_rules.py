"""Sound, source-authorized intrinsic CAT model predicates.

Only a small exact vocabulary is certified. Free-text requirements, fixture
observations, and external effects can NEVER be converted into intrinsic proofs.
A proved predicate asserts precisely its documented model property, not a
general claim about a product's external implementation.
"""
from __future__ import annotations

from catlib import semantic_types as typed

CONTRACT='cat:intrinsic-model/v1'
SCOPE='assembled-process'
OUTCOME_PRESENCE='@cat:declared-outcome-output-presence/v1'
STATE_EQUALITY='@cat:all-trigger-state-equality-preservation/v1'
PREDICATES=frozenset({
    '@cat:effect-targets-declared/v1',
    '@cat:tce-triggers-declared/v1',
    '@cat:field-domains-resolved/v1',
})


def _resolved(domain):
    if not isinstance(domain,dict):return False
    kind=domain.get('type')
    if kind in (None,'unknown'):return False
    if kind=='reference':return bool(domain.get('resolved')) and _resolved(domain['of'])
    if kind=='record':
        return (domain.get('resolved') is True
                and all(_resolved(f.get('domain')) for f in domain.get('fields',[])))
    if kind in ('set','sequence'):return _resolved(domain.get('element'))
    if kind=='nullable':return _resolved(domain.get('of'))
    if kind=='union':return bool(domain.get('variants')) and all(_resolved(x) for x in domain['variants'])
    return True


def _property(token,fields,triggers,tce_rules):
    if token=='@cat:effect-targets-declared/v1':
        destinations={f['id'] for f in fields if f['role'] in ('output','state','action')}
        return all(all(effect['target'] in destinations
                       for outcome in rule['allowed']
                       for effect in outcome.get('write',[]))
                   for rule in tce_rules)
    if token=='@cat:tce-triggers-declared/v1':
        ids={t['id'] for t in triggers}
        return all(rule['trigger'] in ids for rule in tce_rules)
    if token=='@cat:field-domains-resolved/v1':
        return all(_resolved(f.get('domain')) for f in fields)
    return False


def _fresh_output_scope(scope, fields, triggers, rules, operations, overrides, effect_checks):
    """One explicit response-scoped output, not a persistent state variable."""
    parts=scope.split(' ') if isinstance(scope,str) else []
    if len(parts)!=5 or parts[0]!='fresh-output' or not all(parts):return False
    _,pi,operation,trigger,field_id=parts
    if trigger not in {t['id'] for t in triggers}:return False
    fields_by_id={f['id']:f for f in fields}
    field=fields_by_id.get(field_id)
    if not field or field['role']!='output' or field.get('source_pi')!=pi:return False
    if not _resolved(field.get('domain')):return False
    candidates=[op for op in operations if op['direction']=='provide'
                and op.get('trigger') in (None,trigger)]
    if len(candidates)!=1:return False
    op=candidates[0]
    if (op['id'],op.get('source_pi'),op.get('trigger'))!=(operation,pi,trigger):return False
    selected=[x['presence'] for x in overrides if x['operation']==operation
              and x['field']==field_id and x.get('source_pi')==pi]
    if len(selected)>1:return False
    presence=selected[0] if selected else field.get('presence','required')
    if presence not in ('optional','required','absent'):return False
    checked=0
    for rule in rules:
        if rule['trigger']!=trigger:continue
        for number,outcome in enumerate(rule['allowed'],1):
            writes=[(i,w) for i,w in enumerate(outcome['write'],1) if w['target']==field_id]
            absent=field_id in outcome['absent_outputs']
            if len(writes)>1 or bool(writes)==absent:return False
            if (presence=='required' and absent) or (presence=='absent' and writes):return False
            if writes:
                i,_=writes[0]
                key=f"{rule['source_artifact']}#{rule['id']}:{number}:{i}:{field_id}"
                if effect_checks.get(key,{}).get('result')!='proved':return False
            checked+=1
    return checked>0


def _state_equality_scope(scope, fields, triggers, rules, effect_checks):
    """Inductive preservation given an explicitly declared initial equality.

    Prove all declared outcomes, irrespective of Guard, using simultaneous
    before-state reads and frame identities. No reachability inference.
    """
    parts=scope.split(' ') if isinstance(scope,str) else []
    if len(parts)!=3 or parts[0]!='initial-state-equality' or not all(parts):return False
    _,left,right=parts
    by_id={f['id']:f for f in fields}
    a,b=by_id.get(left),by_id.get(right)
    if left==right or not a or not b or a['role']!='state' or b['role']!='state':return False
    domain=a.get('domain',{})
    if domain.get('type') not in ('boolean','integer','string','enum') or not typed.same(domain,b.get('domain')):return False
    trigger_ids={t['id'] for t in triggers}
    if not trigger_ids or {r['trigger'] for r in rules}!=trigger_ids:return False
    for rule in rules:
        if not rule['allowed']:return False
        for number,outcome in enumerate(rule['allowed'],1):
            expressions=[]
            for target in (left,right):
                writes=[(i,w) for i,w in enumerate(outcome['write'],1) if w['target']==target]
                if len(writes)>1:return False
                if writes:
                    i,w=writes[0]
                    key=f"{rule['source_artifact']}#{rule['id']}:{number}:{i}:{target}"
                    if effect_checks.get(key,{}).get('result')!='proved' or target in outcome['unchanged']:return False
                    expr=w['expr']
                else:
                    if target not in outcome['unchanged']:return False
                    expr={'ref':target}
                if set(expr)=={'ref'}:
                    expressions.append({'ref':left if expr['ref']==right else expr['ref']})
                elif set(expr)=={'literal'}:expressions.append(expr)
                else:return False
            if not typed.same(*expressions):return False
    return True


def evaluate(rule_documents,fields,triggers,tce_rules,operations=(),overrides=(),effect_checks=None,guard_invariants=()):
    """Return verified proofs; each certificate is bound to exact source bytes."""
    proofs=[]
    for doc in rule_documents:
        if doc.get('status')!='confirmed' or doc.get('scope_verified') is not True:
            continue
        for rule in doc.get('rules',[]):
            requirement=rule.get('requirement')
            if rule.get('verification_contract')!=CONTRACT:continue
            scope=rule.get('condition')
            if requirement==OUTCOME_PRESENCE:
                proved=_fresh_output_scope(scope,fields,triggers,tce_rules,operations,overrides,effect_checks or {})
            elif requirement==STATE_EQUALITY:
                proved=_state_equality_scope(scope,fields,triggers,tce_rules,effect_checks or {})
            elif requirement=='@cat:finite-state-guard-invariant/v1':
                proved=rule['id'] in guard_invariants
            else:
                proved=(scope==SCOPE and requirement in PREDICATES and
                        _property(requirement,fields,triggers,tce_rules))
            if proved:
                proofs.append({
                    'rule_id':rule['id'],
                    'source_artifact':doc['id'],
                    'source_sha256':doc['sha256'],
                    'requirement':requirement,
                    'verification_contract':CONTRACT,
                    'proof_method':CONTRACT,
                    'scope':scope,
                    'status':'passed',
                })
    return sorted(proofs,key=lambda x:x['rule_id'])
