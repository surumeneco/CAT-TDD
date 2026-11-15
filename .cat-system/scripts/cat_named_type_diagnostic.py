#!/usr/bin/env python3
"""Source-bound named-type dependency audit; never a Process Closure Gate.

This diagnostic reports why explicit DomainSpec types cannot be resolved.
Unknown JSON/time primitives stay unknown; declared Delta is not misreported
as missing when its JSON dependency is absent. No inferred type is emitted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from catlib import semantic_named_types, semantic_rules

SCHEMA = 'cat-named-type-diagnostic/v1'

class DiagnosticError(ValueError):
    pass


def dependencies(domain, path=''):
    """Yield (name, field path) for direct unresolved nominal references."""
    kind = domain.get('type')
    if kind == 'reference':
        if not domain.get('resolved'):
            yield domain['name'], path
        elif 'of' in domain:
            yield from dependencies(domain['of'], path)
    elif kind == 'record':
        if 'name' in domain and not domain.get('resolved'):
            yield domain['name'], path
        else:
            for field in domain.get('fields', []):
                nested = f"{path}.{field['id']}" if path else field['id']
                yield from dependencies(field['domain'], nested)
    elif kind in ('sequence', 'set'):
        yield from dependencies(domain['element'], path+'[]')
    elif kind == 'nullable':
        yield from dependencies(domain['of'], path)
    elif kind == 'union':
        for index, arm in enumerate(domain['variants']):
            yield from dependencies(arm, f'{path}|{index}')


def diagnose(definitions):
    """Describe direct and transitive named-type obligations, retaining Source SHA.

    `resolved` means only Domain syntax and declared aliases were resolved. It
    never proves runtime transport, data invariants, a Rule, or normative status.
    """
    if not isinstance(definitions, dict):
        raise DiagnosticError('named type registry must be a mapping')
    graph = {}
    for name, item in definitions.items():
        if (not isinstance(item, dict) or item.get('name') != name
                or not isinstance(item.get('source_artifact'),str)
                or not re.fullmatch(r'[0-9a-fA-F]{64}', item.get('source_sha256',''))
                or not isinstance(item.get('domain'),dict)):
            raise DiagnosticError('named type requires exact Source identity: '+str(name))
        graph[name] = sorted(set(dependencies(item['domain'])))

    rows = []
    missing = set()
    for name in sorted(definitions):
        item = definitions[name]
        issues = []
        def follow(current, chain, locations):
            for dep, location in graph[current]:
                new_chain = chain + [dep]
                new_locations = locations + [location]
                if dep not in definitions:
                    missing.add(dep)
                    kind = 'missing-declaration'
                elif dep in chain:
                    kind = 'cyclic-dependency'
                else:
                    follow(dep, new_chain, new_locations)
                    continue
                issues.append({
                    'kind': kind,
                    'missing_name': dep if kind=='missing-declaration' else None,
                    'dependency_chain':new_chain,
                    'field_path':' -> '.join(x for x in new_locations if x),
                    'source_artifact': item['source_artifact'],
                    'source_sha256': item['source_sha256'],
                    'source_chain':[
                        {'name': node, 'source_artifact': definitions[node]['source_artifact'],
                         'source_sha256': definitions[node]['source_sha256']}
                        for node in new_chain if node in definitions],
                })
        follow(name, [name], [])
        issues.sort(key=lambda x: (x['kind'],x['dependency_chain'],x['field_path']))
        if not issues:
            try:
                domain = semantic_named_types.resolve(
                    {'type':'reference','name':name,'resolved':False}, definitions)
                if not semantic_named_types._resolved(domain):
                    issues.append({'kind':'unresolved-domain','reason':'domain remains unresolved'})
            except (semantic_named_types.NamedTypeError,ValueError,KeyError) as exc:
                issues.append({'kind':'unresolved-domain','reason':str(exc)})
        rows.append({'name':name, 'source_artifact':item['source_artifact'],
                     'source_sha256':item['source_sha256'],
                     'status':'blocked' if issues else 'resolved', 'issues':issues,
                     'direct_dependencies':[
                         {'name':dep,'field_path':path} for dep,path in graph[name]]})
    resolved = sum(row['status']=='resolved' for row in rows)
    return {'schema':SCHEMA,'status':'diagnostic','formal_gate_status':'not-run',
            'scope':'named type declaration and dependency closure only; not Product Conformance',
            'declared_count':len(rows),'resolved_count':resolved,
            'all_resolved':resolved==len(rows),
            'missing_roots':sorted(missing),'types':rows}


def diagnose_sources(paths,process,allow_draft=False):
    docs=semantic_rules.load_many(paths,process,allow_draft=allow_draft)
    result=diagnose(semantic_named_types.registry(docs))
    result['inputs']=[{'id':doc['id'],'status':doc['status'],
                       'source_sha256':doc['sha256'],'process':doc['process']}
                      for doc in docs]
    result['authority']='diagnostic-only; candidate/draft inputs are not promoted'
    return result


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--process',required=True)
    ap.add_argument('--domain-spec',action='append',required=True)
    ap.add_argument('--allow-draft',action='store_true')
    ap.add_argument('--output',required=True)
    args=ap.parse_args(argv)
    try:
        report=diagnose_sources(args.domain_spec,args.process,args.allow_draft)
        target=Path(args.output)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':report['status'],
                          'declared_count':report['declared_count'],
                          'resolved_count':report['resolved_count'],
                          'all_resolved':report['all_resolved'],
                          'missing_roots':report['missing_roots'],
                          'output':str(target)},ensure_ascii=False))
        return 0  # Audit executed, not all types resolved or any Gate passed.
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
