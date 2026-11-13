#!/usr/bin/env python3
"""Independently compare confirmed CAT source semantics with a generated TestModel.

This validator intentionally does not call cat_compile_v2.load(). It reuses the
notation parser, then derives the expected semantic inventory separately and
compares it with the stored model representation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from cat_compile_v2 import Blocked, format_expr, read_artifact
from catlib import semantic_rules
from catlib import semantic_types
from catlib import semantic_named_types as named_types


def require(test, message):
    if not test:
        raise Blocked(message)


def markdown_body(path):
    raw = Path(path).read_text(encoding='utf-8-sig')
    end = raw.find('\n---\n', 4)
    require(raw.startswith('---\n') and end >= 0, 'invalid TestModel front matter')
    return raw[end + 5:]


def section(text, *names):
    for name in names:
        m = re.search(r'(?ms)^## ' + re.escape(name) + r'\s*$\n(.*?)(?=^##\s|\Z)', text)
        if m:
            return m.group(1).strip()
    return None


def split_row(line):
    line = line.strip()
    require(line.startswith('|') and line.endswith('|'), 'invalid Markdown table row')
    cells = []
    buf = []
    escaped = False
    for ch in line[1:-1]:
        if escaped:
            buf.append(ch)
            escaped = False
        elif ch == '\\':
            escaped = True
            buf.append(ch)
        elif ch == '|':
            cells.append(''.join(buf).strip().replace('\\|', '|'))
            buf = []
        else:
            buf.append(ch)
    cells.append(''.join(buf).strip().replace('\\|', '|'))
    return cells


def table(text, *names):
    sec = section(text, *names)
    if sec is None:
        return []
    lines = [line for line in sec.splitlines() if line.strip().startswith('|')]
    require(len(lines) >= 2, 'table missing in ' + '/'.join(names))
    header = split_row(lines[0])
    return [dict(zip(header, split_row(line))) for line in lines[2:]]


def cell(row, *names):
    for name in names:
        if name in row:
            return row[name].strip()
    raise Blocked('missing model column: ' + '/'.join(names))


def clean_expr(value):
    value = value.strip()
    if value.startswith('`') and value.endswith('`'):
        value = value[1:-1]
    return value


def split_list(value):
    value = value.strip()
    if value in ('', '-', '—', 'none', 'null', 'なし'):
        return []
    return [x.strip() for x in value.split(',') if x.strip()]


def source_semantics(process_path, pi_path, tce_path, domain_path=None, common_rules=(), domain_specs=(), allow_draft=False):
    pf, p = read_artifact(process_path, 'process', allow_draft)
    pi_paths=list(pi_path) if isinstance(pi_path,(list,tuple)) else [pi_path]
    pi_docs=[]
    for path in pi_paths:
        pif, pi=read_artifact(path,'pi',allow_draft)
        pi_docs.append((path,pif,pi))
    pif,pi=pi_docs[0][1:]
    rule_paths=[*common_rules,*domain_specs]
    try:rule_docs=semantic_rules.load_many(rule_paths,p['process'],allow_draft)
    except semantic_rules.RuleError as exc:raise Blocked(str(exc)) from exc
    try:
        type_registry=named_types.registry(rule_docs)
        named_type_definitions=named_types.resolved_definitions(type_registry)
    except (named_types.NamedTypeError,ValueError) as exc:raise Blocked(str(exc)) from exc
    def resolve_domain(domain):
        try:return named_types.resolve(domain,type_registry)
        except (named_types.NamedTypeError,ValueError) as exc:raise Blocked(str(exc)) from exc
    tce_paths = list(tce_path) if isinstance(tce_path, (list, tuple)) else [tce_path]
    require(tce_paths, 'at least one TCE artifact required')
    tces = []
    for path in tce_paths:
        tf, tce = read_artifact(path, 'tce', allow_draft)
        tces.append((path, tf, tce))
    tf = tces[0][1]
    dfile, domain = read_artifact(domain_path, 'domain-rule', allow_draft) if domain_path else (None, None)

    files = [(process_path, pf), *[(path,fm) for path,fm,_ in pi_docs],
             *[(path, fm) for path, fm, _ in tces]]
    files += [(path,{'id':doc['id'],'kind':doc['kind']}) for path,doc in zip(rule_paths,rule_docs)]
    if dfile:
        files.append((domain_path, dfile))

    fields = {}
    domains={}
    presence={}
    field_owners={}
    for _,pif,pi in pi_docs:
        for item in pi['fields']:
            require(item['id'] not in fields,'duplicate PI field '+item['id'])
            fields[item['id']] = item['role']
            domains[item['id']]=resolve_domain(item['domain'])
            presence[item['id']]=item.get('presence','required')
            field_owners[item['id']]=pif['id']
    for item in p.get('state_fields', []):
        fields[item['id']] = 'state'
        domains[item['id']]=resolve_domain(item['domain'])
    for item in p.get('observations', []):
        fields[item['id']] = 'observation'
        domains[item['id']]=resolve_domain(item['domain'])
    for item in p.get('actions', []):
        fields[item['id']] = 'action'
        domains[item['id']]=resolve_domain(item['domain'])

    state_ids = {key for key, role in fields.items() if role == 'state'}
    emitted_ids = {key for key, role in fields.items() if role in ('output', 'action')}

    rules = {}
    effects = set()
    frames = set()
    for _, tce_fm, tce in tces:
        for rule in tce['rules']:
            rid = rule['id']
            require(rid not in rules, 'duplicate TCE behavior ID across assembled specification: ' + rid)
            rules[rid] = (tce_fm['id'], rule['trigger'],
                          format_expr(rule['when'], language=tce_fm.get('language', 'en')))
            for number, outcome in enumerate(rule['allowed'], 1):
                targets = set()
                if outcome['write']:
                    for write in outcome['write']:
                        targets.add(write['target'])
                        effects.add((rid, number, write['target'],
                                     format_expr(write['expr'], language=tce_fm.get('language', 'en'))))
                else:
                    effects.add((rid, number, None, None))
                frames.add((rid, number, tuple(sorted(state_ids - targets)),
                            tuple(sorted(emitted_ids - targets))))

    definitions = {}
    if domain:
        for item in domain['definitions']:
            definitions[item['id']] = (
                tuple(item['params']),
                format_expr(item['body'], item['params'], tf.get('language', 'en')),
            )

    intrinsic_proofs=_intrinsic_source_proofs(
        rule_docs,fields,domains,{x['id']:x['origin'] for x in p['triggers']},rules,effects)
    intrinsic_ids={proof['rule_id'] for proof in intrinsic_proofs}
    all_rule_ids={rule['id'] for doc in rule_docs for rule in doc['rules']}
    source_all_confirmed=(all(fm.get('status')=='confirmed'
                              for _,fm in files if fm['kind'] not in ('common-rule','domain-spec'))
                          and all(doc['status']=='confirmed' for doc in rule_docs))
    return {
        'process':p['process'],
        'process_closed_world':p['closed_world'],
        'sources': {
            fm['id']: (fm['kind'], hashlib.sha256(Path(path).read_bytes()).hexdigest())
            for path, fm in files
        },
        'interfaces': tuple(sorted(p.get('interfaces', []))),
        'boundary': pi_docs[0][2].get('boundary') if len(pi_docs)==1 else None,
        'pi_boundaries': [{'artifact':fm['id'],**a['boundary']} for _,fm,a in pi_docs],
        'operation_presence':sorted((e['operation'],e['field'],e['presence'],fm['id'])
                                    for _,fm,a in pi_docs for e in a.get('operation_presence',[])),
        'operations': {
            item['id']: (item['direction'], item.get('trigger')) for _,_,a in pi_docs
            for item in a.get('operations', [])
        },
        'operation_owners': {item['id']:fm['id'] for _,fm,artifact in pi_docs
                             for item in artifact.get('operations', [])},
        'triggers': {item['id']: item['origin'] for item in p['triggers']},
        'fields': fields, 'domains':domains, 'presence':presence,'field_owners':field_owners,
        'normative_rule_inputs': {d['id']:(d['kind'],d['sha256']) for d in rule_docs},
        'named_type_definitions':named_type_definitions,
        'intrinsic_rule_proofs':intrinsic_proofs,
        'unverified_rule_ids':sorted(all_rule_ids-intrinsic_ids),
        'source_all_confirmed':source_all_confirmed,
        'rule_obligations': {r['id']:(r['source_artifact'],r['condition'],r['requirement'],r['verification_contract'],
                                    'intrinsic-proved' if r['id'] in intrinsic_ids else 'unverified')
                             for d in rule_docs for r in d['rules']},
        'constraints': tuple(format_expr(expr, language=tf.get('language', 'en')) for _,_,a in pi_docs for expr in a.get('constraints', [])),
        'definitions': definitions,
        'rules': rules,
        'effects': effects,
        'frames': frames,
    }



# Independently reconstruct intrinsic model-rule evidence from the source.
# This module deliberately does not invoke the Compiler's proof function.
def _intrinsic_source_proofs(rule_docs, fields, domains, triggers, tce_rules, effects):
    def resolved(d):
        if not isinstance(d,dict) or d.get('type') in (None,'unknown'):return False
        t=d['type']
        if t=='reference':return bool(d.get('resolved')) and resolved(d['of'])
        if t=='record':
            return d.get('resolved') is True and all(resolved(f['domain']) for f in d.get('fields',[]))
        if t in ('set','sequence'):return resolved(d['element'])
        if t=='nullable':return resolved(d['of'])
        if t=='union':return bool(d.get('variants')) and all(resolved(x) for x in d['variants'])
        return True
    predicates={
        '@cat:effect-targets-declared/v1':all(
            e[2] is None or fields.get(e[2]) in ('output','state','action')
            for e in effects),
        '@cat:tce-triggers-declared/v1':all(value[1] in triggers for value in tce_rules.values()),
        '@cat:field-domains-resolved/v1':all(resolved(d) for d in domains.values()),
    }
    proofs=[]
    for document in rule_docs:
        if document.get('status')!='confirmed' or not document.get('scope_verified'):
            continue
        for rule in document.get('rules',[]):
            token=rule.get('requirement')
            if (rule.get('condition')=='assembled-process'
                    and rule.get('verification_contract')=='cat:intrinsic-model/v1'
                    and predicates.get(token) is True):
                proofs.append({
                    'rule_id':rule['id'],'source_artifact':document['id'],
                    'source_sha256':document['sha256'],'requirement':token,
                    'verification_contract':'cat:intrinsic-model/v1',
                    'proof_method':'cat:intrinsic-model/v1',
                    'scope':'assembled-process','status':'passed',
                })
    return sorted(proofs,key=lambda item:item['rule_id'])


ROLE_ALIASES = {'受信': 'input', '送信': 'output', '状態': 'state', '観測': 'observation', '作用': 'action'}
DIRECTION_ALIASES = {'受信': 'receive', '送信': 'send', '双方向': 'bidirectional',
                     '受付': 'accept', '提供': 'provide'}


def markdown_model(path):
    text = markdown_body(path)
    sources = {}
    for row in table(text, 'Source artifacts', '出典Artifact'):
        ident = cell(row, 'Artifact ID')
        digest = clean_expr(cell(row, 'SHA-256'))
        sources[ident] = (cell(row, 'Kind', '種別'), digest)

    interfaces = tuple(sorted(cell(row, 'PI') for row in table(text, 'Process interfaces', 'Process境界')))

    boundary_rows = table(text, 'PI boundary', 'PI境界')
    boundary = None
    if boundary_rows:
        require(len(boundary_rows) == 1, 'TestModel PI boundary must have one row')
        direction = cell(boundary_rows[0], 'Direction', '方向')
        boundary = {'peer': cell(boundary_rows[0], 'Peer process', '相手Process'),
                    'direction': DIRECTION_ALIASES.get(direction, direction)}

    operations = {}
    for row in table(text, 'PI operations', 'PI操作'):
        direction = cell(row, 'Direction', '方向')
        trigger = cell(row, 'Trigger', '起点')
        operations[cell(row, 'ID')] = (DIRECTION_ALIASES.get(direction, direction),
                                       None if trigger in ('-', '—', '') else trigger)

    triggers = {cell(row, 'ID'): cell(row, 'Origin', '由来')
                for row in table(text, 'Triggers', '起点')}

    fields = {}
    for row in table(text, 'Fields', '仕様要素'):
        role = cell(row, 'Role', '役割')
        fields[cell(row, 'ID')] = ROLE_ALIASES.get(role, role)

    constraints = tuple(clean_expr(cell(row, 'Expression', '式'))
                        for row in table(text, 'PI constraints', 'PI制約'))

    definitions = {}
    for row in table(text, 'DomainRule definitions', 'DomainRule定義'):
        params = tuple(x.strip() for x in cell(row, 'Parameters', '引数').split(',') if x.strip() and x.strip() != '—')
        definitions[cell(row, 'ID')] = (params, clean_expr(cell(row, 'Expression', '式')))

    rules = {}
    for row in table(text, 'Rules', '規則'):
        rules[cell(row, 'ID')] = (cell(row, 'Source TCE', '出典TCE'),
                                  cell(row, 'Trigger', '起点'),
                                  clean_expr(cell(row, 'Condition', '条件')))

    effects = set()
    for row in table(text, 'Effects', '効果'):
        target = cell(row, 'Target', '対象')
        expr = cell(row, 'Expression', '式')
        effects.add((cell(row, 'Rule', '規則'), int(cell(row, 'Outcome', '結果')),
                     None if target == '—' else target,
                     None if expr == '—' else clean_expr(expr)))

    frames = set()
    for row in table(text, 'Derived frame conditions', '導出された不変条件'):
        frames.add((cell(row, 'Rule', '規則'), int(cell(row, 'Outcome', '結果')),
                    tuple(sorted(split_list(cell(row, 'Unchanged state', '不変状態')))),
                    tuple(sorted(split_list(cell(row, 'Absent outputs/actions', '不在の出力・作用'))))))

    return {'sources': sources, 'interfaces': interfaces, 'boundary': boundary,
            'operations': operations, 'triggers': triggers, 'fields': fields,
            'constraints': constraints, 'definitions': definitions, 'rules': rules,
            'effects': effects, 'frames': frames}


def json_model(path):
    model = json.loads(Path(path).read_text(encoding='utf-8'))
    require(isinstance(model,dict),'TestModel JSON must be an object')
    # Inventory comparisons use dictionaries; reject duplicates before their
    # last-wins normalization can conceal a corrupted or forged source entry.
    for name in ('source_records','triggers','fields','pi_operations','rules','named_type_definitions',
                 'definitions','normative_rule_inputs','rule_obligations'):
        if name not in model:
            continue
        items=model[name]
        require(isinstance(items,list),name+' inventory must be an array')
        identifiers=[]
        for item in items:
            require(isinstance(item,dict) and isinstance(item.get('id'),str) and bool(item['id']),
                    name+' inventory item requires an ID')
            identifiers.append(item['id'])
        require(len(identifiers)==len(set(identifiers)),'duplicate '+name+' inventory ID')
    boundaries=model.get('pi_boundaries',[])
    require(isinstance(boundaries,list),'PI boundaries must be an array')
    boundary_ids=[x.get('artifact') if isinstance(x,dict) else None for x in boundaries]
    require(all(isinstance(x,str) and x for x in boundary_ids),'PI boundary requires artifact ID')
    require(len(boundary_ids)==len(set(boundary_ids)),'duplicate PI boundary artifact')
    sources = {}
    if model.get('source_records'):
        for item in model['source_records']:
            sources[item['id']] = (item['kind'], item['sha256'])
    else:
        source_ids = model.get('source_artifacts', [])
        source_sha = model.get('source_sha256', {})
        source_pairs = list(source_sha.items())
        for index, ident in enumerate(source_ids):
            if index < len(source_pairs):
                kind, digest = source_pairs[index]
                sources[ident] = (kind, digest)

    fields = {item['id']: item['role'] for item in model.get('fields', [])}
    domains = {item['id']: item['domain'] for item in model.get('fields', [])}
    presence = {item['id']: item.get('presence','required') for item in model.get('fields', []) if item['role'] in ('input','output')}
    field_owners={item['id']:item.get('source_pi') for item in model.get('fields', []) if item['role'] in ('input','output')}
    rules = {item['id']: (item.get('source_artifact'), item['trigger'],
                          format_expr(item['when'], language=model.get('language', 'en')))
             for item in model.get('rules', [])}
    effects = set()
    frames = set()
    for rule in model.get('rules', []):
        for number, outcome in enumerate(rule.get('allowed', []), 1):
            if outcome.get('write'):
                for write in outcome['write']:
                    effects.add((rule['id'], number, write['target'],
                                 format_expr(write['expr'], language=model.get('language', 'en'))))
            else:
                effects.add((rule['id'], number, None, None))
            frames.add((rule['id'], number, tuple(sorted(outcome.get('unchanged', []))),
                        tuple(sorted(outcome.get('absent_outputs', [])))))
    definitions = {item['id']: (tuple(item['params']),
                   format_expr(item['body'], item['params'], model.get('language', 'en')))
                   for item in model.get('definitions', [])}
    operations = {item['id']: (item['direction'], item.get('trigger'))
                  for item in model.get('pi_operations', [])}
    return {
        'process':model.get('process'),
        'sources': sources,
        'interfaces': tuple(sorted(model.get('process_interfaces', []))),
        'boundary': model.get('pi_boundary'),
        'pi_boundaries':model.get('pi_boundaries',[]),
        'operation_presence':sorted((e['operation'],e['field'],e['presence'],e['source_pi'])
                                    for e in model.get('operation_presence',[])),
        'operations': operations,
        'operation_owners': {item['id']:item.get('source_pi') for item in model.get('pi_operations', [])},
        'triggers': {item['id']: item['origin'] for item in model.get('triggers', [])},
        'fields': fields, 'domains':domains,'presence':presence,'field_owners':field_owners,
        'normative_rule_inputs':{d['id']:(d['kind'],d['sha256']) for d in model.get('normative_rule_inputs',[])},
        'named_type_definitions':model.get('named_type_definitions',[]),
        'rule_obligations':{r['id']:(r['source_artifact'],r['condition'],r['requirement'],r['verification_contract'],r.get('verification_status','unverified')) for r in model.get('rule_obligations',[])},
        'intrinsic_rule_proofs':model.get('intrinsic_rule_proofs',[]),
        'unverified_rule_ids':model.get('unverified_rule_ids',[]),
        'status':model.get('status'),
        'coverage_requirement':model.get('coverage_requirement'),
        'coverage_claim':model.get('coverage_claim'),
        'coverage_checks':model.get('coverage_checks'),
        'presence_unproven':model.get('presence_unproven'),
        'unresolved_domains':model.get('unresolved_domains'),
        'unresolved_interfaces':model.get('unresolved_interfaces'),
        'constraints': tuple(format_expr(expr, language=model.get('language', 'en'))
                             for expr in model.get('pi_constraints', [])),
        'definitions': definitions,
        'rules': rules,
        'effects': effects,
        'frames': frames,
    }


def validate(process, pi, tce, model, domain_rule=None,common_rules=(),domain_specs=(),allow_draft=False):
    expected = source_semantics(process, pi, tce, domain_rule,common_rules,domain_specs,allow_draft)
    actual = json_model(model) if Path(model).suffix.lower() == '.json' else markdown_model(model)
    mismatches = []
    checks = ('sources', 'interfaces', 'boundary', 'operations', 'triggers', 'fields',
              'constraints', 'definitions', 'rules', 'effects', 'frames')
    if Path(model).suffix.lower()=='.json':
        checks += ('process','pi_boundaries','operation_owners','field_owners','operation_presence','normative_rule_inputs','rule_obligations','domains','presence','named_type_definitions','intrinsic_rule_proofs','unverified_rule_ids')
    for key in checks:
        # Python structural == conflates bool with int (True == 1). Domains
        # and named type definitions contain typed literal values and must
        # retain scalar identity throughout their nested inventory.
        same=(semantic_types.same(actual.get(key),expected.get(key))
              if key in ('domains','named_type_definitions')
              else actual.get(key)==expected.get(key))
        if not same:
            mismatches.append(key)
    if Path(model).suffix.lower()=='.json':
        if actual.get('status') not in ('draft','confirmed'):
            mismatches.append('model_status_invalid')
        # Claims of complete closure must be coherent with both the source
        # Process and the model's own finite proof records. This comparison
        # does not replace the independent process-closure Gate.
        checks_by_trigger=actual.get('coverage_checks')
        complete_checks=(
            isinstance(checks_by_trigger,dict)
            and set(checks_by_trigger)==set(expected['triggers'])
            and all(isinstance(v,dict) and v.get('result')=='proved'
                    for v in checks_by_trigger.values()))
        exact_claim=(actual.get('coverage_requirement') in ('closed','partial')
                     and actual.get('coverage_claim')==actual.get('coverage_requirement'))
        if actual.get('coverage_requirement')=='closed' and not expected['process_closed_world']:
            mismatches.append('closed_world_claim_unjustified')
        if actual.get('status')=='confirmed' and (
                not expected['source_all_confirmed']
                or not expected['process_closed_world']
                or expected['unverified_rule_ids']
                or not exact_claim
                or actual.get('coverage_requirement')!='closed'
                or not complete_checks
                or actual.get('presence_unproven')!=[]
                or actual.get('unresolved_domains')!=[]
                or actual.get('unresolved_interfaces')!=[]):
            mismatches.append('normative_status_unjustified')
    if Path(model).suffix.lower()!='.json' and expected.get('intrinsic_rule_proofs'):
        mismatches.append('intrinsic_rule_proofs: Markdown renderer omits source-bound proof evidence')
    if Path(model).suffix.lower()!='.json' and expected.get('named_type_definitions'):
        mismatches.append('named_type_definitions: Markdown renderer omits structural type provenance')
    if Path(model).suffix.lower()!='.json' and expected.get('operation_presence'):
        mismatches.append('operation_presence: Markdown renderer omits operation-specific semantics')
    return {
        'schema': 'cat-model-conformance/v1',
        'status': 'passed' if not mismatches else 'blocked',
        'mismatches': mismatches,
        'source_semantics': sorted(expected),
        'model_sha256': hashlib.sha256(Path(model).read_bytes()).hexdigest(),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('process')
    ap.add_argument('pi')
    ap.add_argument('--pi-extra',action='append',default=[])
    ap.add_argument('--common-rule',action='append',default=[])
    ap.add_argument('--domain-spec',action='append',default=[])
    ap.add_argument('--allow-draft',action='store_true')
    ap.add_argument('model')
    ap.add_argument('--tce', action='append', required=True)
    ap.add_argument('--domain-rule')
    args = ap.parse_args(argv)
    try:
        result = validate(args.process, [args.pi,*args.pi_extra], args.tce, args.model, args.domain_rule,args.common_rule,args.domain_spec,args.allow_draft)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result['status'] == 'passed' else 2
    except (Blocked, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
