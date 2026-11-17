"""Resolve explicit DomainSpec structural record declarations; never infer shapes.

This is an opt-in extension: missing, ambiguous and cyclic types fail closed.
"""
from __future__ import annotations
from copy import deepcopy
from catlib import semantic_types

class NamedTypeError(ValueError):pass


def registry(documents):
    declared={}
    for doc in documents:
        for definition in doc.get('types',[]):
            name=definition['name']
            if name in declared:raise NamedTypeError('duplicate named type '+name)
            declared[name]=definition
    return declared


def resolve(domain,definitions,stack=()):
    t=domain['type']
    if t=='reference':
        if domain.get('resolved'):
            return semantic_types.validate(deepcopy(domain))
        name=domain['name']
        if name not in definitions:
            return deepcopy(domain)  # Unknown aliases remain unresolved, never guessed.
        if name in stack:
            raise NamedTypeError('cyclic named type: '+' -> '.join((*stack,name)))
        definition=definitions[name]
        body=resolve(definition['domain'],definitions,(*stack,name))
        if not _resolved(body):
            raise NamedTypeError('unresolved named type definition: '+name)
        return semantic_types.validate({
            'type':'reference','name':name,'resolved':True,'of':body,
            'definition_source':definition['source_artifact'],
            'definition_sha256':definition['source_sha256']})
    if t=='record':
        if 'name' in domain and not domain.get('resolved',False):
            name=domain['name']
            if name not in definitions:
                return deepcopy(domain)  # unresolved is not a normative success
            if name in stack:
                raise NamedTypeError('cyclic named type: '+' -> '.join((*stack,name)))
            definition=definitions[name]
            body=resolve(definition['domain'],definitions,(*stack,name))
            if body['type']!='record' or not body.get('resolved',False):
                raise NamedTypeError('unresolved named type definition: '+name)
            result={'type':'record','name':name,'resolved':True,
                    'fields':deepcopy(body['fields']),
                    'definition_source':definition['source_artifact'],
                    'definition_sha256':definition['source_sha256']}
            semantic_types.validate(result)
            return result
        result=deepcopy(domain)
        if 'fields' in result:
            result['fields']=[dict(field,domain=resolve(field['domain'],definitions,stack))
                              for field in result['fields']]
            result['resolved']=all(_resolved(field['domain']) for field in result['fields'])
        semantic_types.validate(result)
        return result
    if t in ('sequence','set'):
        result=deepcopy(domain);result['element']=resolve(domain['element'],definitions,stack)
        return semantic_types.validate(result)
    if t=='nullable':
        result=deepcopy(domain);result['of']=resolve(domain['of'],definitions,stack)
        return semantic_types.validate(result)
    if t=='union':
        result=deepcopy(domain);result['variants']=[resolve(x,definitions,stack) for x in domain['variants']]
        return semantic_types.validate(result)
    return semantic_types.validate(deepcopy(domain))


def _resolved(domain):
    t=domain['type']
    if t=='reference':return bool(domain.get('resolved')) and _resolved(domain['of']) if domain.get('resolved') else False
    if t=='record':return bool(domain.get('resolved')) and all(_resolved(f['domain']) for f in domain.get('fields',[]))
    if t in ('sequence','set'):return _resolved(domain['element'])
    if t=='nullable':return _resolved(domain['of'])
    if t=='union':return all(_resolved(x) for x in domain['variants'])
    return True


def resolved_definitions(definitions):
    # Validate every declaration, including types not currently referenced by a PI.
    result=[]
    for name in sorted(definitions):
        item=definitions[name]
        probe_type='record' if item['domain']['type']=='record' else 'reference'
        domain=resolve({'type':probe_type,'name':name,'resolved':False},definitions)
        if not _resolved(domain):raise NamedTypeError('unresolved named type definition: '+name)
        result.append({'id':name,'source_artifact':item['source_artifact'],
                       'source_sha256':item['source_sha256'],'domain':domain})
    return result
