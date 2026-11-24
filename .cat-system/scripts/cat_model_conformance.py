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

from cat_compile_v2 import Blocked, format_expr, format_domain, read_artifact, _effect_totality_checks
from catlib import semantic_rules
from catlib import decimal_integer
from catlib import semantic_types
from catlib import independent_coverage
from catlib import independent_effect_proof
from catlib.markdown import parse_frontmatter
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
    observation_availability={item['id']:(item['source'],tuple(item.get('available_on',[]))
                                            if 'available_on' in item else None)
                              for item in p.get('observations',[])}

    # Derive the PI-input availability constraint directly from Source. A
    # submitted Model with a forged `confirmed` flag must not bypass the
    # Compiler's accepted-Operation check.
    if any('operations' in artifact for _,_,artifact in pi_docs):
        from cat_compile_v2 import used_refs
        reference_definitions={item['id']:item for item in domain['definitions']} if domain else {}
        accepts={}
        for _,fm,artifact in pi_docs:
            for op in artifact.get('operations',[]):
                if op['direction']=='accept':
                    accepts.setdefault(op['trigger'],[]).append(fm['id'])
        for _,_,artifact in tces:
            for rule in artifact['rules']:
                owners=accepts.get(rule['trigger'],[])
                if len(owners)>1:
                    continue  # Ambiguous accepted Operations remain unproved.
                active_owners=set(owners)
                # Independently derive the exact provided-operation response
                # bindings from Source. None/wildcard Trigger cannot license
                # a later reply; two providers at one Trigger are ambiguous.
                responses={}
                for _,fm,pi in pi_docs:
                    for op in pi.get('operations',[]):
                        if op['direction']=='provide' and op.get('trigger')==rule['trigger']:
                            responses.setdefault(fm['id'],[]).append(op['id'])
                active_owners.update(owner for owner,ops in responses.items() if len(ops)==1)
                refs=used_refs(rule['when'],reference_definitions)
                for result in rule['allowed']:
                    for effect in result['write']:
                        refs.update(used_refs(effect['expr'],reference_definitions))
                invalid=sorted(ref for ref in refs if fields.get(ref)=='input'
                               and field_owners.get(ref) not in active_owners)
                require(not invalid,'Source TCE reads an inactive PI input at '+rule['trigger']+': '+str(invalid))
                unavailable=sorted(ref for ref in refs if ref in observation_availability
                                   and observation_availability[ref][1] is not None
                                   and rule['trigger'] not in observation_availability[ref][1])
                require(not unavailable,'Source TCE reads Observation unavailable at Trigger '+rule['trigger']+': '+str(unavailable))

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

    # Effect proof inventory is derived from independent normative TCE/PI/Process
    # reads rather than trusting the submitted JSON TestModel's claimed proofs.
    effect_fields={ident:{'id':ident,'role':role,'domain':domains[ident],
                          'presence':presence.get(ident,'required'),
                          'source_pi':field_owners.get(ident)}
                   for ident,role in fields.items()}
    effect_rules=[{**rule,'source_artifact':fm['id']}
                  for _,fm,tce in tces for rule in tce['rules']]
    effect_definitions={item['id']:item for item in domain['definitions']} if domain else {}
    effect_operations=[{**operation,'source_pi':fm['id']}
                       for _,fm,pi in pi_docs for operation in pi.get('operations',[])]
    effect_presence=[{**override,'source_pi':fm['id']}
                     for _,fm,pi in pi_docs
                     for override in pi.get('operation_presence',[])]
    effect_checks=_effect_totality_checks(
        effect_rules,effect_fields,effect_definitions,
        pi_operations=effect_operations,operation_presence=effect_presence)
    # Revalidate every positive Effect claim via a separate Source-based
    # proof path. A shared Compiler helper bug must not certify a Model.
    unjustified_effect_proofs=independent_effect_proof.unjustified_positive(
        effect_rules,effect_fields,effect_definitions,effect_checks,
        pi_operations=effect_operations,operation_presence=effect_presence)
    unverified_effect_ids=sorted(ident for ident,check in effect_checks.items()
                                 if check['result']!='proved')
    source_guard_audit=independent_coverage.audit(p,pi_docs,tces,fields,domains,domain)
    constraint_scopes=[]
    unbound_constraints=[]
    markdown_bindings=[]
    for _,fm,pi in pi_docs:
        accepted=sorted({op['trigger'] for op in pi.get('operations',[])
                         if op['direction']=='accept'})
        own_fields={f['id']:f for f in pi['fields']}
        for expr in pi.get('constraints',[]):
            from cat_compile_v2 import used_refs
            refs=used_refs(expr,{x['id']:x for x in domain['definitions']} if domain else {})
            # The Compiler rejects cross-owner references. Independently keep
            # this claim in the Source→Model inventory rather than accepting
            # a field-name-only matching expression.
            owner_only=all(ref in own_fields for ref in refs)
            input_only=owner_only and all(own_fields[ref]['role']=='input' for ref in refs)
            active=accepted if input_only else []
            constraint_scopes.append((fm['id'],tuple(active),
                       format_expr(expr,language=fm.get('language','en'))))
            if pf.get('semantic_contract')=='markdown-v2':
                reason=(('non-input result relation' if not input_only
                         else 'no accepted Operation to bind PI constraint')
                        if not active else None)
                markdown_bindings.append((fm['id'],tuple(active),
                                          format_expr(expr,language=tf.get('language','en')),
                                          reason))
                if reason is not None:
                    unbound_constraints.append({'source_pi':fm['id'],
                                                'expr':expr,'reason':reason})
    intrinsic_proofs=_intrinsic_source_proofs(
        rule_docs,fields,domains,{x['id']:x['origin'] for x in p['triggers']},rules,effects,
        pi_docs,tces,effect_checks,set(unjustified_effect_proofs))
    intrinsic_ids={proof['rule_id'] for proof in intrinsic_proofs}
    all_rule_ids={rule['id'] for doc in rule_docs for rule in doc['rules']
                  if rule.get('verification_status')!='not-applicable'}
    source_all_confirmed=(all(fm.get('status')=='confirmed'
                              for _,fm in files if fm['kind'] not in ('common-rule','domain-spec'))
                          and all(doc['status']=='confirmed' for doc in rule_docs))
    # The Compiler's human-facing Source-to-Model mapping is itself a
    # claim about normative provenance. Reconstruct it directly from parsed
    # Process/PI/TCE/Rule/DomainRule inputs, not from any compiler map or
    # self-asserted Model metadata. This is *not* an extra reachability proof.
    source_semantic_map={
        'process':{
            'artifact':pf['id'],
            'triggers':[item['id'] for item in p['triggers']],
            'interfaces':list(p.get('interfaces',[])),
            'state':[item['id'] for item in p.get('state_fields',[])],
            'observations':[item['id'] for item in p.get('observations',[])],
            'actions':[item['id'] for item in p.get('actions',[])]},
        'pi':{
            'artifact':pif['id'] if len(pi_docs)==1 else None,
            'artifacts':[fm['id'] for _,fm,_ in pi_docs],
            'fields':[item['id'] for _,_,a in pi_docs for item in a['fields']],
            'operations':[item['id'] for _,_,a in pi_docs
                          for item in a.get('operations',[])],
            'constraint_count':sum(len(a.get('constraints',[])) for _,_,a in pi_docs)},
        'tce':[{'artifact':fm['id'],
                'rules':[item['id'] for item in a['rules']],
                'outcome_count':sum(len(item['allowed']) for item in a['rules']),
                'local_coverage':a['coverage']}
               for _,fm,a in tces],
        'common_rules':[doc['id'] for doc in rule_docs if doc['kind']=='common-rule'],
        'domain_specs':[doc['id'] for doc in rule_docs if doc['kind']=='domain-spec'],
        'type_definitions':[item['id'] for item in named_type_definitions],
        'domain_rule':{
            'artifact':dfile['id'] if dfile else None,
            'definitions':sorted(item['id'] for item in domain['definitions']) if domain else []},
    }
    return {
        'process':p['process'],
        'source_authority':{'markdown-v2':'cat-markdown/v2',
                            'markdown-v1':'cat-markdown/v1',
                            'machine-only':'cat-machine/v2'}[pf.get('semantic_contract','markdown-v1')],
        'source_language':(tf.get('language','en') if pf.get('semantic_contract')=='markdown-v2'
                           else 'en'),
        'process_closed_world':p['closed_world'],
        'source_semantic_map':source_semantic_map,
        'local_coverage_requirements':{fm['id']:a['coverage'] for _,fm,a in tces},
        'pi_artifacts':[fm['id'] for _,fm,_ in pi_docs],
        'source_guard_audit':source_guard_audit,
        'constraint_scopes':sorted(constraint_scopes),
        'constraint_bindings':sorted(markdown_bindings),
        # A result-time or ownerless PI constraint is not proved by local
        # acceptance-Guard partitioning. Independently retain its exact Source.
        'unbound_pi_constraints':(unbound_constraints
                                  if pf.get('semantic_contract')=='markdown-v2' else None),
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
            item['id']: (item['direction'], item.get('trigger'), item.get('peer')) for _,_,a in pi_docs
            for item in a.get('operations', [])
        },
        'operation_owners': {item['id']:fm['id'] for _,fm,artifact in pi_docs
                             for item in artifact.get('operations', [])},
        'triggers': {item['id']: item['origin'] for item in p['triggers']},
        'fields': fields, 'domains':domains, 'presence':presence,'field_owners':field_owners,
        'observation_availability':observation_availability,
        'normative_rule_inputs': {d['id']:(d['kind'],d['process'],d['sha256']) for d in rule_docs},
        'named_type_definitions':named_type_definitions,
        'intrinsic_rule_proofs':intrinsic_proofs,
        'unverified_rule_ids':sorted(all_rule_ids-intrinsic_ids),
        'effect_checks':effect_checks,
        'unjustified_effect_proofs':unjustified_effect_proofs,
        'unverified_effect_ids':unverified_effect_ids,
        'source_all_confirmed':source_all_confirmed,
        'rule_obligations': {r['id']:(r['source_artifact'],r['source_kind'],r['condition'],r['requirement'],r['verification_contract'],
                                    ('intrinsic-proved' if r['id'] in intrinsic_ids else
                                     r.get('verification_status','unverified')),
                                    r.get('source_sha256'),r.get('scope_binding'))
                             for d in rule_docs for r in d['rules']},
        'constraints': tuple(format_expr(expr, language=tf.get('language', 'en')) for _,_,a in pi_docs for expr in a.get('constraints', [])),
        'definitions': definitions,
        'rules': rules,
        'effects': effects,
        'frames': frames,
    }



# Independently reconstruct intrinsic model-rule evidence from the source.
# This module deliberately does not invoke the Compiler's proof function.
def _source_fresh_output(scope, triggers, pi_docs, tces, effect_checks, rejected):
    # Independently select an exact PI/Operation/Trigger/Field directly from
    # Source; do not consume the Compiler's derived Frame or certificate.
    if not isinstance(scope,str):return False
    words=scope.split(' ')
    if len(words)!=5 or words[0]!='fresh-output' or not all(words):return False
    _,owner,operation,trigger,field_id=words
    if trigger not in triggers:return False
    provided=[(fm['id'],op) for _,fm,pi in pi_docs for op in pi.get('operations',[])
              if op['direction']=='provide' and op.get('trigger') in (None,trigger)]
    if len(provided)!=1:return False
    actual_owner,op=provided[0]
    if actual_owner!=owner or op['id']!=operation or op.get('trigger')!=trigger:return False
    selected=[pi for _,fm,pi in pi_docs if fm['id']==owner]
    if len(selected)!=1:return False
    pi=selected[0]
    fields=[f for f in pi['fields'] if f['id']==field_id and f['role']=='output']
    if len(fields)!=1:return False
    overrides=[x['presence'] for x in pi.get('operation_presence',[])
               if x['operation']==operation and x['field']==field_id]
    if len(overrides)>1:return False
    presence=overrides[0] if overrides else fields[0].get('presence','required')
    if presence not in ('required','optional','absent'):return False
    seen=False
    for _,fm,tce in tces:
        for rule in tce['rules']:
            if rule['trigger']!=trigger:continue
            for n,outcome in enumerate(rule['allowed'],1):
                seen=True
                matching=[i for i,w in enumerate(outcome['write'],1) if w['target']==field_id]
                if len(matching)>1:return False
                if presence=='required' and not matching:return False
                if presence=='absent' and matching:return False
                if matching:
                    key=f"{fm['id']}#{rule['id']}:{n}:{matching[0]}:{field_id}"
                    if key in rejected or effect_checks.get(key,{}).get('result')!='proved':return False
    return seen


def _intrinsic_source_proofs(rule_docs, fields, domains, triggers, tce_rules, effects,
                            pi_docs=(),tces=(),effect_checks=None,rejected=()):
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
            scope=rule.get('condition')
            if rule.get('verification_contract')!='cat:intrinsic-model/v1':continue
            if token=='@cat:declared-outcome-output-presence/v1':
                target=scope.split(' ')[-1] if isinstance(scope,str) else None
                proved=(resolved(domains.get(target)) and
                        _source_fresh_output(scope,triggers,pi_docs,tces,effect_checks or {},rejected))
            else:
                proved=(scope=='assembled-process' and predicates.get(token) is True)
            if proved:
                proofs.append({
                    'rule_id':rule['id'],'source_artifact':document['id'],
                    'source_sha256':document['sha256'],'requirement':token,
                    'verification_contract':'cat:intrinsic-model/v1',
                    'proof_method':'cat:intrinsic-model/v1',
                    'scope':scope,'status':'passed',
                })
    return sorted(proofs,key=lambda item:item['rule_id'])


ROLE_ALIASES = {'受信': 'input', '送信': 'output', '状態': 'state', '観測': 'observation', '作用': 'action'}
DIRECTION_ALIASES = {'受信': 'receive', '送信': 'send', '双方向': 'bidirectional',
                     '受付': 'accept', '提供': 'provide'}


def markdown_model(path):
    # Front matter carries a separate normative authority/coverage claim. It
    # must be validated along with body tables, not ignored as presentation.
    front = parse_frontmatter(Path(path))
    text = markdown_body(path)
    requirement = section(text, 'Coverage requirement', '網羅要求')
    sources = {}
    for row in table(text, 'Source artifacts', '出典Artifact'):
        ident = cell(row, 'Artifact ID')
        digest = clean_expr(cell(row, 'SHA-256'))
        require(ident not in sources, 'duplicate Markdown Source artifact')
        sources[ident] = (cell(row, 'Kind', '種別'), digest)

    rule_sources = {}
    for row in table(text, 'Normative rule sources', '規範Rule出典'):
        ident=cell(row,'Source ID','出典ID')
        require(ident not in rule_sources,'duplicate Markdown normative Rule source')
        rule_sources[ident]=(cell(row,'Kind','種別'),cell(row,'Declaring Process','宣言元Process'),
                             clean_expr(cell(row,'SHA-256')))

    rule_obligations = {}
    for row in table(text,'Normative rule obligations','規範Rule義務'):
        ident=cell(row,'ID')
        require(ident not in rule_obligations,'duplicate Markdown normative Rule obligation')
        scope=cell(row,'Scope binding','適用範囲束縛')
        if scope=='—':
            scope=None
        else:
            try:scope=json.loads(scope)
            except (ValueError,TypeError) as exc:
                raise Blocked('invalid Markdown normative Rule scope binding') from exc
        rule_obligations[ident]=(
            cell(row,'Source artifact','出典Artifact'),
            cell(row,'Source kind','出典種別'),
            cell(row,'Condition','適用条件'),
            cell(row,'Requirement','要求'),
            cell(row,'Verification contract','検証契約'),
            cell(row,'Verification status','検証状態'),
            (None if cell(row,'Source SHA-256','出典SHA-256')=='—'
             else cell(row,'Source SHA-256','出典SHA-256')),
            scope,
        )

    # JSON code fence retains the exact typed definition graph, including
    # nested Domain shapes and per-definition Source provenance. A missing
    # fence is not an empty definition set.
    nominal=section(text,'Resolved named types','解決済み名前付き型')
    require(nominal is not None,'missing Markdown resolved named type inventory')
    match=re.fullmatch(r'```json\s*\n(.*?)\n```',nominal,re.DOTALL)
    require(match is not None,'invalid Markdown resolved named type inventory')
    try:named_types_data=decimal_integer.loads(match.group(1))
    except (ValueError,TypeError) as exc:
        raise Blocked('malformed Markdown resolved named type inventory') from exc
    require(isinstance(named_types_data,list),'resolved named types must be an array')
    ids=[item.get('id') for item in named_types_data if isinstance(item,dict)]
    require(len(ids)==len(named_types_data) and
            all(isinstance(x,str) and x for x in ids) and len(set(ids))==len(ids),
            'invalid/duplicate Markdown named type ID')
    operation_section=section(text,'Operation presence','操作別Presence')
    require(operation_section is not None,'missing Markdown Operation presence')
    operation_presence=[];seen_operation_presence=set()
    for row in table(text,'Operation presence','操作別Presence'):
        key=(cell(row,'Operation','操作'),cell(row,'Field','フィールド'))
        require(key not in seen_operation_presence,'duplicate Markdown Operation presence')
        seen_operation_presence.add(key)
        operation_presence.append((key[0],key[1],cell(row,'Presence'),cell(row,'Source PI','出典PI')))
    operation_presence.sort()
    observation_section=section(text,'Observation availability','観測利用可能時点')
    require(observation_section is not None,'missing Markdown observation availability')
    observation_availability={}
    for row in table(text,'Observation availability','観測利用可能時点'):
        ident=cell(row,'Observation ID','観測ID')
        require(ident not in observation_availability,'duplicate Markdown observation availability')
        try:available=decimal_integer.loads(clean_expr(cell(row,'Available on (JSON)','利用可能な起点(JSON)')))
        except (ValueError,TypeError) as exc:
            raise Blocked('invalid Markdown observation availability') from exc
        require(available is None or (isinstance(available,list)
                and all(isinstance(x,str) for x in available)),
                'invalid Markdown observation Trigger list')
        observation_availability[ident]=(cell(row,'Source','出典'),
                                         tuple(available) if available is not None else None)

    # A source-bound intrinsic proof has eight independently checkable fields.
    # A status label in the Rule table is not itself a proof certificate.
    intrinsic_proofs=[]
    proof_ids=set()
    for row in table(text,'Intrinsic rule proofs','内在Rule証明'):
        proof={
            'rule_id':cell(row,'Rule ID'),
            'source_artifact':cell(row,'Source artifact','出典Artifact'),
            'source_sha256':cell(row,'Source SHA-256','出典SHA-256'),
            'requirement':cell(row,'Requirement','要求'),
            'verification_contract':cell(row,'Verification contract','検証契約'),
            'proof_method':cell(row,'Proof method','証明方法'),
            'scope':cell(row,'Scope','適用範囲'),
            'status':cell(row,'Proof status','証明状態'),
        }
        require(proof['rule_id'] not in proof_ids,'duplicate Markdown intrinsic Rule proof')
        proof_ids.add(proof['rule_id'])
        intrinsic_proofs.append(proof)
    intrinsic_proofs.sort(key=lambda proof:proof['rule_id'])

    interfaces = tuple(sorted(cell(row, 'PI') for row in table(text, 'Process interfaces', 'Process境界')))

    boundary_rows = table(text, 'PI boundary', 'PI境界')
    boundary = None
    if boundary_rows:
        peers = [cell(row, 'Peer process', '相手Process') for row in boundary_rows]
        directions = [DIRECTION_ALIASES.get(cell(row, 'Direction', '方向'),
                                             cell(row, 'Direction', '方向'))
                      for row in boundary_rows]
        require(len(peers)==len(set(peers)) and len(set(directions))==1,
                'TestModel PI boundary peer set must be unique with one direction')
        boundary = {'peer':peers[0], 'direction':directions[0]}
        if len(peers)>1:
            boundary['peers']=peers

    require(section(text,'PI boundaries','PI境界一覧') is not None,
            'missing Markdown PI boundaries')
    pi_boundaries=[];seen_pi_boundaries=set()
    for row in table(text,'PI boundaries','PI境界一覧'):
        ident=cell(row,'Source PI','出典PI')
        require(ident not in seen_pi_boundaries,'duplicate Markdown PI boundary owner')
        seen_pi_boundaries.add(ident)
        direction=cell(row,'Direction','方向')
        direction=DIRECTION_ALIASES.get(direction,direction)
        try:peers=decimal_integer.loads(clean_expr(cell(row,'Peers (JSON)','相手Process一覧(JSON)')))
        except (ValueError,TypeError) as exc:
            raise Blocked('invalid Markdown PI peer list') from exc
        require(peers is None or (isinstance(peers,list)
                and all(isinstance(peer,str) and peer for peer in peers)),
                'invalid Markdown PI peer list')
        item={'artifact':ident,'peer':cell(row,'Peer process','相手Process'),
              'direction':direction}
        if peers is not None:item['peers']=peers
        pi_boundaries.append(item)

    operations = {};operation_owners={}
    for row in table(text, 'PI operations', 'PI操作'):
        direction = cell(row, 'Direction', '方向')
        trigger = cell(row, 'Trigger', '起点')
        peer = row.get('Peer process', row.get('相手Process', '—')).strip()
        ident=cell(row, 'ID')
        require(ident not in operations, 'duplicate Markdown PI operation')
        operations[ident] = (DIRECTION_ALIASES.get(direction, direction),
                                       None if trigger in ('-', '—', '') else trigger,
                                       None if peer in ('-', '—', '') else peer)
        operation_owners[ident]=cell(row,'Source PI','出典PI')

    triggers = {}
    for row in table(text, 'Triggers', '起点'):
        ident=cell(row, 'ID')
        require(ident not in triggers, 'duplicate Markdown Trigger')
        triggers[ident]=cell(row, 'Origin', '由来')

    fields = {};markdown_domains={};presence={};field_owners={}
    for row in table(text, 'Fields', '仕様要素'):
        role = cell(row, 'Role', '役割')
        ident=cell(row,'ID')
        require(ident not in fields,'duplicate Markdown Field')
        role=ROLE_ALIASES.get(role, role)
        fields[ident] = role
        markdown_domains[ident]=clean_expr(cell(row,'Domain'))
        base=cell(row,'Presence')
        owner=cell(row,'Source PI','出典PI')
        if role in ('input','output'):
            presence[ident]=base
            field_owners[ident]=owner
        else:
            require(base=='—' and owner=='—',
                    'Process-owned Markdown field cannot declare PI ownership or Presence')

    constraints = tuple(clean_expr(cell(row, 'Expression', '式'))
                        for row in table(text, 'PI constraints', 'PI制約'))
    constraint_bindings=[]
    for row in table(text,'PI constraint bindings','PI制約の束縛'):
        reason=cell(row,'Unproved reason','未証明理由')
        constraint_bindings.append((cell(row,'Source PI','出典PI'),
             tuple(split_list(cell(row,'Triggers','起点'))),
             clean_expr(cell(row,'Expression','式')),
             None if reason in ('—','-','') else reason))

    definitions = {}
    for row in table(text, 'DomainRule definitions', 'DomainRule定義'):
        params = tuple(x.strip() for x in cell(row, 'Parameters', '引数').split(',') if x.strip() and x.strip() != '—')
        ident=cell(row, 'ID')
        require(ident not in definitions, 'duplicate Markdown DomainRule definition')
        definitions[ident] = (params, clean_expr(cell(row, 'Expression', '式')))

    rules = {}
    for row in table(text, 'Rules', '規則'):
        ident=cell(row, 'ID')
        require(ident not in rules, 'duplicate Markdown TCE Rule')
        rules[ident] = (cell(row, 'Source TCE', '出典TCE'),
                                  cell(row, 'Trigger', '起点'),
                                  clean_expr(cell(row, 'Condition', '条件')))

    effects = set()
    for row in table(text, 'Effects', '効果'):
        target = cell(row, 'Target', '対象')
        expr = cell(row, 'Expression', '式')
        entry=(cell(row, 'Rule', '規則'), int(cell(row, 'Outcome', '結果')),
               None if target == '—' else target,
               None if expr == '—' else clean_expr(expr))
        require(entry not in effects, 'duplicate Markdown Effect')
        effects.add(entry)

    frames = set()
    for row in table(text, 'Derived frame conditions', '導出された不変条件'):
        entry=(cell(row, 'Rule', '規則'), int(cell(row, 'Outcome', '結果')),
               tuple(sorted(split_list(cell(row, 'Unchanged state', '不変状態')))),
               tuple(sorted(split_list(cell(row, 'Absent outputs/actions', '不在の出力・作用')))))
        require(entry not in frames, 'duplicate Markdown frame condition')
        frames.add(entry)

    return {'model_schema': front.get('schema'), 'model_process': front.get('process'),
            'model_status': front.get('status'),
            'model_authority': front.get('semantic_authority'),
            'model_language': front.get('language'),
            'coverage_requirement': (requirement.strip('`').strip()
                                     if isinstance(requirement, str) else None),
            'sources': sources, 'normative_rule_inputs':rule_sources,
            'rule_obligations':rule_obligations, 'intrinsic_rule_proofs':intrinsic_proofs,
            'named_type_definitions':named_types_data,
            'operation_presence':operation_presence,
            'observation_availability':observation_availability,
            'markdown_domains':markdown_domains,
            'interfaces': interfaces, 'boundary': boundary, 'pi_boundaries':pi_boundaries,
            'operations': operations, 'operation_owners':operation_owners,
            'triggers': triggers, 'fields': fields,
            'presence':presence, 'field_owners':field_owners,
            'constraints': constraints, 'constraint_bindings':sorted(constraint_bindings),
            'definitions': definitions, 'rules': rules,
            'effects': effects, 'frames': frames}


def json_model(path):
    model = decimal_integer.loads(Path(path).read_text(encoding='utf-8'))
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
    source_metadata_integrity = True
    if 'source_records' in model:
        # The compiler emits three representations of the same provenance.
        # Source-to-Model comparison must reject contradictions among them,
        # even if the canonical source_records inventory remains accurate.
        expected_source_ids=[]
        expected_source_hashes={}
        for item in model['source_records']:
            sources[item['id']] = (item['kind'], item['sha256'])
            expected_source_ids.append(item['id'])
            key=(item['kind'] if item['kind'] not in expected_source_hashes
                 else item['kind']+':'+item['id'])
            expected_source_hashes[key]=item['sha256']
        source_metadata_integrity=(
            model.get('source_artifacts')==expected_source_ids
            and model.get('source_sha256')==expected_source_hashes)
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
    observation_availability={item['id']:(item.get('source'),tuple(item['available_on'])
                                            if 'available_on' in item else None)
                              for item in model.get('fields', []) if item['role']=='observation'}
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
    operations = {item['id']: (item['direction'], item.get('trigger'), item.get('peer'))
                  for item in model.get('pi_operations', [])}
    return {
        'process':model.get('process'),
        'source_semantic_map':model.get('source_semantic_map'),
        'local_coverage_requirements':model.get('local_coverage_requirements'),
        'pi_artifacts':model.get('pi_artifacts'),
        'model_type':model.get('model_type'),
        'limits':model.get('limits'),
        'normalized_ir':model.get('normalized_ir'),
        'sources': sources,
        'source_metadata_integrity': source_metadata_integrity,
        'interfaces': tuple(sorted(model.get('process_interfaces', []))),
        'boundary': model.get('pi_boundary'),
        'pi_boundaries':model.get('pi_boundaries',[]),
        'operation_presence':sorted((e['operation'],e['field'],e['presence'],e['source_pi'])
                                    for e in model.get('operation_presence',[])),
        'operations': operations,
        'operation_owners': {item['id']:item.get('source_pi') for item in model.get('pi_operations', [])},
        'triggers': {item['id']: item['origin'] for item in model.get('triggers', [])},
        'fields': fields, 'domains':domains,'presence':presence,'field_owners':field_owners,
        'observation_availability':observation_availability,
        'normative_rule_inputs':{d['id']:(d['kind'],d.get('process'),d['sha256']) for d in model.get('normative_rule_inputs',[])},
        'named_type_definitions':model.get('named_type_definitions',[]),
        'rule_obligations':{r['id']:(r['source_artifact'],r.get('source_kind'),r['condition'],r['requirement'],r['verification_contract'],r.get('verification_status','unverified'),r.get('source_sha256'),r.get('scope_binding')) for r in model.get('rule_obligations',[])},
        'intrinsic_rule_proofs':model.get('intrinsic_rule_proofs',[]),
        'unverified_rule_ids':model.get('unverified_rule_ids',[]),
        'effect_checks':model.get('effect_checks'),
        'unverified_effect_ids':model.get('unverified_effect_ids'),
        'status':model.get('status'),
        'coverage_requirement':model.get('coverage_requirement'),
        'coverage_claim':model.get('coverage_claim'),
        'coverage_checks':model.get('coverage_checks'),
        'presence_unproven':model.get('presence_unproven'),
        'unresolved_domains':model.get('unresolved_domains'),
        'unresolved_interfaces':model.get('unresolved_interfaces'),
        'constraints': tuple(format_expr(expr, language=model.get('language', 'en'))
                             for expr in model.get('pi_constraints', [])),
        'constraint_scopes':sorted((e['source_pi'],tuple(e['triggers']),
             format_expr(e['expr'],language=model.get('language','en')))
             for e in model.get('pi_constraint_scopes',[])),
        'unbound_pi_constraints':model.get('unbound_pi_constraints'),
        'definitions': definitions,
        'rules': rules,
        'effects': effects,
        'frames': frames,
    }


def validate(process, pi, tce, model, domain_rule=None,common_rules=(),domain_specs=(),allow_draft=False):
    expected = source_semantics(process, pi, tce, domain_rule,common_rules,domain_specs,allow_draft)
    actual = json_model(model) if Path(model).suffix.lower() == '.json' else markdown_model(model)
    mismatches = []
    if expected['unjustified_effect_proofs']:
        mismatches.append('effect_totality_independent')
    checks = ('sources', 'interfaces', 'boundary', 'operations', 'triggers', 'fields',
              'constraints', 'definitions', 'rules', 'effects', 'frames')
    if Path(model).suffix.lower()!='.json':
        # Markdown need not carry JSON proof receipts, but it must preserve
        # the normative PI/Operation Trigger and unresolved result-time scope.
        checks += ('constraint_bindings','normative_rule_inputs','rule_obligations','intrinsic_rule_proofs',
                   'named_type_definitions','operation_presence','observation_availability',
                   'presence','field_owners','operation_owners','pi_boundaries')
    if Path(model).suffix.lower()=='.json':
        checks += ('process','pi_boundaries','operation_owners','field_owners','operation_presence','observation_availability','normative_rule_inputs','rule_obligations','domains','presence','named_type_definitions','intrinsic_rule_proofs','unverified_rule_ids','effect_checks','unverified_effect_ids','constraint_scopes','unbound_pi_constraints')
        checks += ('source_semantic_map','local_coverage_requirements','pi_artifacts')
    if Path(model).suffix.lower()=='.json':
        # These are fixed Compiler proof-scope declarations, not product
        # assumptions a submitting Model can silently strengthen or remove.
        for key,claim in (
            ('model_type','symbolic-relation'),
            ('limits',['finite-guard-closure-only','no-general-reachability-proof',
                       'no-process-composition']),
            ('normalized_ir','cat-machine/v2' if expected['source_authority']
                                  in ('cat-markdown/v1','cat-markdown/v2') else None),
        ):
            if actual.get(key)!=claim:
                mismatches.append(key)
    for key in checks:
        # Python structural == conflates bool with int (True == 1). Domains
        # and named type definitions contain typed literal values and must
        # retain scalar identity throughout their nested inventory.
        same=(semantic_types.same(actual.get(key),expected.get(key))
              if key in ('domains','named_type_definitions','unbound_pi_constraints')
              else actual.get(key)==expected.get(key))
        if not same:
            mismatches.append(key)
    if Path(model).suffix.lower()!='.json':
        expected_display={ident:format_domain(domain,expected['source_language'])
                          for ident,domain in expected['domains'].items()}
        if actual['markdown_domains']!=expected_display:
            mismatches.append('domains')
    if Path(model).suffix.lower()=='.json':
        if actual.get('source_metadata_integrity') is not True:
            mismatches.append('source_metadata_integrity')
        # Independently recompute Source Guard partitions, not Compiler receipts.
        source_guard=expected['source_guard_audit']
        actual_guards=actual.get('coverage_checks')
        if (not isinstance(actual_guards,dict)
                or set(actual_guards)!=set(source_guard['triggers'])
                or any(not isinstance(actual_guards.get(k),dict)
                       or actual_guards[k].get('result')!=v['result']
                       for k,v in source_guard['triggers'].items())):
            mismatches.append('source_guard_coverage')
        # Proof diagnostics are evidence, not free-form UI labels: validate
        # finite counterexample witnesses, counts, reachability and Guard refs.
        receipt_keys=('guard_refs','overlap_count','overlaps','uncovered',
                      'uncovered_count','unreachable_rules',
                      'excluded_by_pi_constraints')
        symbolic_receipt_keys=('proof_method','partition_fields',
                               'abstract_state_count','proof_scope')
        if isinstance(actual_guards,dict):
            for trigger,expected_receipt in source_guard['triggers'].items():
                if expected_receipt['result'] in ('proved','uncovered','conflict'):
                    observed=actual_guards.get(trigger)
                    if (not isinstance(observed,dict) or any(
                            not semantic_types.same(observed.get(k),expected_receipt[k])
                            for k in receipt_keys)
                            or any(not semantic_types.same(observed.get(k),expected_receipt.get(k))
                                   for k in symbolic_receipt_keys)
                            or ('proof_method' not in expected_receipt and
                                any(k in observed for k in symbolic_receipt_keys))):
                        if 'source_guard_coverage' not in mismatches:
                            mismatches.append('source_guard_coverage')
                        break
        # Exact identity of Source-obligated output fields matters. A nonempty
        # invented/different pending ID is not proof that the required output
        # was preserved in the Model's unproved Presence inventory.
        pending=actual.get('presence_unproven')
        required_pending=set(source_guard['unproved_output_fields'])
        if (not isinstance(pending,list)
                or any(not isinstance(x,str) or x not in expected['fields']
                       for x in pending)
                or len(pending)!=len(set(pending))
                or not required_pending.issubset(set(pending))):
            mismatches.append('source_output_presence')
        guard_proved=(bool(source_guard['triggers'])
                      and all(c['result']=='proved' and not c['unreachable_rules']
                              for c in source_guard['triggers'].values())
                      and source_guard['output_presence_proved']
                      and not expected['unbound_pi_constraints'])
        if actual.get('coverage_requirement')=='closed' and not guard_proved:
            if 'source_guard_coverage' not in mismatches:
                mismatches.append('source_guard_coverage')
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
                or not guard_proved
                or not expected['process_closed_world']
                or expected['unverified_rule_ids']
                or expected['unverified_effect_ids']
                or not exact_claim
                or actual.get('coverage_requirement')!='closed'
                or not complete_checks
                or actual.get('unverified_effect_ids')!=[]
                or actual.get('presence_unproven')!=[]
                or actual.get('unresolved_domains')!=[]
                or actual.get('unresolved_interfaces')!=[]):
            mismatches.append('normative_status_unjustified')
    if Path(model).suffix.lower()!='.json':
        # A genuine Markdown Model has no JSON proof receipts, but it still
        # makes explicit claims in YAML and the Coverage requirement section.
        # Recompute only what Source proves, never derive authority from those
        # self-asserted labels. More complex obligations remain inconclusive.
        for key, source_value in (
            ('model_schema','cat-test-model/v2'),
            ('model_process',expected['process']),
            ('model_authority',expected['source_authority']),
            ('model_language',expected['source_language']),
        ):
            if actual.get(key)!=source_value:
                mismatches.append(key)
        declared_coverage=actual.get('coverage_requirement')
        declared_status=actual.get('model_status')
        guard_audit=expected['source_guard_audit']
        guard_proved=(bool(guard_audit['triggers'])
                      and all(c['result']=='proved' and not c['unreachable_rules']
                              for c in guard_audit['triggers'].values())
                      and guard_audit['output_presence_proved']
                      and not expected['unbound_pi_constraints'])
        if declared_coverage not in ('closed','partial'):
            mismatches.append('coverage_requirement_invalid')
        elif declared_coverage=='closed' and (
                not expected['process_closed_world'] or not guard_proved):
            mismatches.append('markdown_closed_world_claim_unjustified')
        if declared_status not in ('draft','confirmed'):
            mismatches.append('model_status_invalid')
        elif declared_status=='confirmed' and (
                declared_coverage!='closed'
                or not expected['source_all_confirmed']
                or not expected['process_closed_world'] or not guard_proved
                or expected['unverified_rule_ids'] or expected['unverified_effect_ids']):
            mismatches.append('markdown_normative_status_unjustified')
    if Path(model).suffix.lower()!='.json' and expected.get('unverified_effect_ids'):
        mismatches.append('effect_totality: Markdown renderer lacks source-bound Effect proof receipts')
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
