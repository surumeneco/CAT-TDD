"""Sound, source-authorized intrinsic CAT model predicates.

Only a small exact vocabulary is certified. Free-text requirements, fixture
observations, and external effects can NEVER be converted into intrinsic proofs.
A proved predicate asserts precisely its documented model property, not a
general claim about a product's external implementation.
"""
from __future__ import annotations

CONTRACT='cat:intrinsic-model/v1'
SCOPE='assembled-process'
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


def evaluate(rule_documents,fields,triggers,tce_rules):
    """Return verified proofs; each certificate is bound to exact source bytes."""
    proofs=[]
    for doc in rule_documents:
        if doc.get('status')!='confirmed' or doc.get('scope_verified') is not True:
            continue
        for rule in doc.get('rules',[]):
            requirement=rule.get('requirement')
            if not (rule.get('condition')==SCOPE
                    and rule.get('verification_contract')==CONTRACT
                    and requirement in PREDICATES):
                continue
            if _property(requirement,fields,triggers,tce_rules):
                proofs.append({
                    'rule_id':rule['id'],
                    'source_artifact':doc['id'],
                    'source_sha256':doc['sha256'],
                    'requirement':requirement,
                    'verification_contract':CONTRACT,
                    'proof_method':CONTRACT,
                    'scope':SCOPE,
                    'status':'passed',
                })
    return sorted(proofs,key=lambda x:x['rule_id'])
