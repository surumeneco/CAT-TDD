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


def source_semantics(process_path, pi_path, tce_path, domain_path=None):
    pf, p = read_artifact(process_path, 'process', False)
    pif, pi = read_artifact(pi_path, 'pi', False)
    tce_paths = list(tce_path) if isinstance(tce_path, (list, tuple)) else [tce_path]
    require(tce_paths, 'at least one TCE artifact required')
    tces = []
    for path in tce_paths:
        tf, tce = read_artifact(path, 'tce', False)
        tces.append((path, tf, tce))
    tf = tces[0][1]
    dfile, domain = read_artifact(domain_path, 'domain-rule', False) if domain_path else (None, None)

    files = [(process_path, pf), (pi_path, pif), *[(path, fm) for path, fm, _ in tces]]
    if dfile:
        files.append((domain_path, dfile))

    fields = {}
    for item in pi['fields']:
        fields[item['id']] = item['role']
    for item in p.get('state_fields', []):
        fields[item['id']] = 'state'
    for item in p.get('observations', []):
        fields[item['id']] = 'observation'
    for item in p.get('actions', []):
        fields[item['id']] = 'action'

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

    return {
        'sources': {
            fm['id']: (fm['kind'], hashlib.sha256(Path(path).read_bytes()).hexdigest())
            for path, fm in files
        },
        'interfaces': tuple(sorted(p.get('interfaces', []))),
        'boundary': pi.get('boundary'),
        'operations': {
            item['id']: (item['direction'], item.get('trigger')) for item in pi.get('operations', [])
        },
        'triggers': {item['id']: item['origin'] for item in p['triggers']},
        'fields': fields,
        'constraints': tuple(format_expr(expr, language=tf.get('language', 'en')) for expr in pi.get('constraints', [])),
        'definitions': definitions,
        'rules': rules,
        'effects': effects,
        'frames': frames,
    }


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
        'sources': sources,
        'interfaces': tuple(sorted(model.get('process_interfaces', []))),
        'boundary': model.get('pi_boundary'),
        'operations': operations,
        'triggers': {item['id']: item['origin'] for item in model.get('triggers', [])},
        'fields': fields,
        'constraints': tuple(format_expr(expr, language=model.get('language', 'en'))
                             for expr in model.get('pi_constraints', [])),
        'definitions': definitions,
        'rules': rules,
        'effects': effects,
        'frames': frames,
    }


def validate(process, pi, tce, model, domain_rule=None):
    expected = source_semantics(process, pi, tce, domain_rule)
    actual = json_model(model) if Path(model).suffix.lower() == '.json' else markdown_model(model)
    mismatches = []
    for key in ('sources', 'interfaces', 'boundary', 'operations', 'triggers', 'fields',
                'constraints', 'definitions', 'rules', 'effects', 'frames'):
        if actual.get(key) != expected.get(key):
            mismatches.append(key)
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
    ap.add_argument('model')
    ap.add_argument('--tce', action='append', required=True)
    ap.add_argument('--domain-rule')
    args = ap.parse_args(argv)
    try:
        result = validate(args.process, args.pi, args.tce, args.model, args.domain_rule)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result['status'] == 'passed' else 2
    except (Blocked, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
