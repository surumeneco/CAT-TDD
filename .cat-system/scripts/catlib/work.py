#!/usr/bin/env python3
"""CAT Work Markdown contract parsing, rendering and validation.

This module contains no command execution, Git inspection or lifecycle evidence logic.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from catlib.common import Blocked, read_json, require
from catlib.markdown import parse_frontmatter

STAGES = ("intake", "reverse", "spec", "review", "process-closure", "model", "model-conformance",
          "queue", "tests", "test-review", "red", "implementation", "green",
          "implementation-conformance", "integration", "refactor-scope", "refactor", "regression",
          "ci", "git", "merge", "deployment", "real-use")
CONFORMANCE_GATES = ("process-closure", "model-conformance", "implementation-conformance")
EXTERNAL_GATES = ("semantic-review", "test-oracle-review", "red-review", "pr-review", "ci", "merge", "deployment", "real-use")
ALL_GATES = CONFORMANCE_GATES + EXTERNAL_GATES
FLOWS = ("spec-implementation", "issue-work", "specification", "code-to-spec", "refactor")
WORK_KINDS = ("implementation", "specification", "analysis", "documentation", "verification", "refactor")
ENTRIES = ("confirmed-spec", "issue", "bug", "existing-code", "refactor")
STATUSES = ("draft", "candidate", "confirmed", "unknown", "conflict")
GATE_STATUSES = ("passed", "not-applicable", "not-run", "blocked", "inconclusive")
ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")

def _markdown_body(path):
    raw = Path(path).read_text(encoding='utf-8-sig')
    end = raw.find('\n---\n', 4)
    require(raw.startswith('---\n') and end >= 0, f'{path}: invalid front matter')
    return raw[end + 5:]


def _split_md_row(line):
    line = line.strip()
    require(line.startswith('|') and line.endswith('|'), 'Markdown table rows must start/end with |')
    cells, buf, escaped = [], [], False
    for ch in line[1:-1]:
        if escaped:
            buf.append(ch); escaped = False; continue
        if ch == '\\':
            escaped = True; buf.append(ch); continue
        if ch == '|':
            cells.append(''.join(buf).strip().replace('\\|', '|')); buf = []
        else:
            buf.append(ch)
    cells.append(''.join(buf).strip().replace('\\|', '|'))
    return cells


def _section(text, name):
    m = re.search(r'(?ms)^## ' + re.escape(name) + r'\s*$\n(.*?)(?=^##\s|\Z)', text)
    return m.group(1).strip() if m else None


def _section_any(text, *names):
    for name in names:
        sec=_section(text,name)
        if sec is not None:
            return sec
    return None


def _table_from_section(sec, label, required=True):
    if sec is None:
        require(not required, f'missing ## {label} section')
        return []
    lines = [x for x in sec.splitlines() if x.strip().startswith('|')]
    if not lines:
        require(not required, f'## {label}: table required')
        return []
    header = _split_md_row(lines[0])
    require(len(lines) >= 2, f'## {label}: table separator required')
    sep = _split_md_row(lines[1])
    require(len(sep) == len(header) and all(re.fullmatch(r':?-{3,}:?', x.strip()) for x in sep),
            f'## {label}: invalid Markdown table separator')
    rows = []
    for line in lines[2:]:
        cells = _split_md_row(line)
        require(len(cells) == len(header), f'## {label}: row width differs from header')
        rows.append(dict(zip(header, cells)))
    return rows


def _table(text, name, required=True):
    return _table_from_section(_section(text,name),name,required)


def _table_any(text, names, required=True):
    return _table_from_section(_section_any(text,*names),'/'.join(names),required)

def _cell(row, *names, required=True):
    for name in names:
        if name in row:
            return row[name].strip()
    require(not required, 'table column required: ' + '/'.join(names))
    return ''


def _none(value):
    return value.strip() in ('', '-', '—', 'none', 'null', 'なし')


def _items(value):
    if _none(value):
        return []
    return [x.strip() for x in value.split(';') if x.strip()]


def _bool(value, where):
    low = value.strip().lower()
    if value.strip() in ('真','偽'): return value.strip() == '真'
    require(low in ('true', 'false'), f'{where}: true or false / 真 or 偽 required')
    return low == 'true'


def _gate_status(value):
    aliases={'成功':'passed','通過':'passed','対象外':'not-applicable','未実行':'not-run',
             '停止':'blocked','ブロック':'blocked','不確定':'inconclusive','結論不能':'inconclusive'}
    return aliases.get(value.strip(),value.strip())


def read_work_markdown(path):
    fm = parse_frontmatter(path)
    require(fm.get('kind') == 'work', f'{path}: front matter kind must be work')
    body = _markdown_body(path)
    evidence = [{'uri': _cell(r, 'URI', 'Uri', 'uri', '参照')} for r in _table_any(body, ('Evidence','証拠'))]
    scope_rows = _table_any(body, ('Scope','範囲'))
    require(len(scope_rows) == 1, 'Scope/範囲 requires exactly one data row')
    scope_row = scope_rows[0]
    tech = [_cell(r, 'Technology', 'technology', '技術') for r in _table_any(body, ('Technologies','技術'), required=False)]
    repos = []
    for row in _table_any(body, ('Repositories','リポジトリ'), required=False):
        repo = {'name': _cell(row, 'Name', 'name', '名前'), 'path': _cell(row, 'Path', 'path', 'パス'),
                'allowed_paths': _items(_cell(row, 'Allowed paths', 'Allowed Paths', 'allowed_paths', '許可パス')),
                'production_paths': _items(_cell(row, 'Production paths', 'Production Paths', 'production_paths', 'Production許可パス', required=False)),
                'test_paths': _items(_cell(row, 'Test paths', 'Test Paths', 'test_paths', 'Test許可パス', required=False))}
        base = _cell(row, 'Base ref', 'Base Ref', 'base_ref', '基準ref', required=False)
        branch = _cell(row, 'Branch pattern', 'Branch Pattern', 'branch_pattern', 'ブランチ規則', required=False)
        if not _none(base): repo['base_ref'] = base
        if not _none(branch): repo['branch_pattern'] = branch
        repos.append(repo)
    checks = []
    for row in _table_any(body, ('Checks','検査'), required=False):
        command = _cell(row, 'Command', 'command', 'コマンド')
        require('\n' not in command and '\r' not in command, 'check command must be one line')
        try: argv = shlex.split(command, posix=True)
        except ValueError as exc: raise Blocked('invalid quoted command: ' + str(exc)) from exc
        c = {'id': _cell(row, 'ID', 'Id', 'id'), 'stage': _cell(row, 'Stage', 'stage', '工程'),
             'runner': _cell(row, 'Runner', 'runner', '実行形式'), 'cwd': _cell(row, 'CWD', 'cwd', '作業場所'), 'argv': argv,
             'input_paths': _items(_cell(row, 'Inputs', 'Input paths', 'input_paths', '入力', required=False)),
             'output_paths': _items(_cell(row, 'Outputs', 'Output paths', 'output_paths', '出力', required=False))}
        tests = _items(_cell(row, 'Test IDs', 'Test ids', 'test_ids', 'テストID', required=False))
        if tests: c['test_ids'] = tests
        timeout = _cell(row, 'Timeout', 'Timeout seconds', 'timeout_seconds', 'タイムアウト', required=False)
        if not _none(timeout):
            require(timeout.isdigit(), f'{c["id"]}: Timeout must be integer seconds')
            c['timeout_seconds'] = int(timeout)
        checks.append(c)
    gates = []
    for row in _table_any(body, ('Gates','ゲート'), required=False):
        gate = {'id': _cell(row, 'Gate', 'ID', 'Id', 'id', 'ゲート'),
                'status': _gate_status(_cell(row, 'Status', 'status', '状態')),
                'evidence': _cell(row, 'Evidence', 'evidence', '証拠', required=False)}
        gates.append(gate)
    compilation = None
    comp_rows = _table_any(body, ('Compilation','変換'), required=False)
    if comp_rows:
        require(len(comp_rows) == 1, 'Compilation/変換 requires zero or one data row')
        row = comp_rows[0]
        compilation = {'schema': 'cat-compile/v2'}
        mapping = {('Process','プロセス'):'process',('PI',):'pi',('TCE',):'tce',('Domain rule','DomainRule','ドメイン規則'):'domain_rule',
                   ('Model','モデル'):'model',('Vectors','具体値'):'vectors',('Queue','キュー'):'queue',
                   ('Binding','接続'):'binding',('Tests','テスト'):'tests_output',
                   ('Obligations','適合義務'):'obligations'}
        for humans, key in mapping.items():
            value = _cell(row, *humans, key, required=False)
            if not _none(value): compilation[key] = value
        compilation['allow_draft'] = _bool(_cell(row, 'Allow draft', 'allow_draft', 'Draft許可'), 'Compilation Allow draft')
    decision = fm.get('decision_ref')
    if _none(str(decision or '')): decision = None
    return {'schema': 'cat-work/v1', 'id': fm.get('id'), 'entry': fm.get('entry'), 'mode': fm.get('mode'),
            'flow': fm.get('flow'), 'work_kind': fm.get('work_kind'), 'parent': fm.get('parent'),
            'depends_on': fm.get('depends_on', []),
            'issue_ref': fm.get('issue_ref'), 'project_entry_ref': fm.get('project_entry_ref'),
            'normative': [{'uri': x} for x in fm.get('source_refs', [])], 'evidence': evidence,
            'specification': {'status': fm.get('spec_status'), 'decision_ref': decision,
                              'artifact_refs': fm.get('refs', [])},
            'scope': {'process_ids': _items(_cell(scope_row, 'Process IDs', 'Process ids', 'process_ids', 'Process ID', 'プロセスID')),
                      'changed_ids': _items(_cell(scope_row, 'Changed IDs', 'Changed ids', 'changed_ids', '変更ID', required=False)),
                      'preserved_ids': _items(_cell(scope_row, 'Preserved IDs', 'Preserved ids', 'preserved_ids', '保持ID', required=False))},
            'technologies': tech, 'repositories': repos, 'checks': checks, 'gates': gates,
            **({'compilation': compilation} if compilation is not None else {})}

def render_work_markdown(identifier):
    return f"""---
cat_version: '0.2'
kind: work
id: {identifier}
status: candidate
process: unknown.process
source_refs:
  - TO_BE_IDENTIFIED
decision_ref: ''
refs: []
entry: issue
mode: shadow
flow: issue-work
work_kind: analysis
parent: ''
depends_on: []
issue_ref: TO_BE_IDENTIFIED
project_entry_ref: TO_BE_IDENTIFIED
spec_status: unknown
---

# Work: {identifier}

## Evidence

| URI |
| --- |
| TO_BE_IDENTIFIED |

## Scope

Multiple IDs in one cell are separated by `;`.

| Process IDs | Changed IDs | Preserved IDs |
| --- | --- | --- |
| TO_BE_IDENTIFIED | — | — |

## Technologies

| Technology |
| --- |

## Repositories

`Allowed paths` uses `;` between path patterns.

| Name | Path | Base ref | Branch pattern | Allowed paths | Production paths | Test paths |
| --- | --- | --- | --- | --- | --- | --- |

## Checks

`Command` uses shell-like quoting only to express argv; execution never uses a shell. List cells use `;`.

| ID | Stage | Runner | CWD | Command | Test IDs | Inputs | Outputs | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |

## Gates

External/semantic gates are reported evidence. `passed` or `not-applicable` requires a concrete evidence/rationale reference.

| Gate | Status | Evidence |
| --- | --- | --- |
| process-closure | not-run | — |
| model-conformance | not-run | — |
| implementation-conformance | not-run | — |
| semantic-review | not-run | — |
| test-oracle-review | not-run | — |
| red-review | not-run | — |
| pr-review | not-run | — |
| ci | not-run | — |
| merge | not-run | — |
| deployment | not-run | — |
| real-use | not-run | — |

## Compilation

Remove this section when deterministic compilation is not used.

| Process | PI | TCE | Domain rule | Model | Vectors | Queue | Binding | Tests | Obligations | Allow draft |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""


def work_file(path):
    p = Path(path).resolve()
    require(p.is_file(), f'Work file missing: {p}')
    w = read_json(p) if p.suffix.lower() == '.json' else read_work_markdown(p)
    errs = validate(w)
    require(not errs, 'Work contract:\n- ' + '\n- '.join(errs))
    return p, w


def validate(w):
    errs = []
    if not isinstance(w, dict):
        return ['Work must normalize to an object']
    if w.get('schema') != 'cat-work/v1':
        errs.append('schema must be cat-work/v1')
    if not isinstance(w.get('id'), str) or not ID.fullmatch(w['id']):
        errs.append('invalid Work id')
    if w.get('entry') not in ENTRIES:
        errs.append('entry must be one of ' + ', '.join(ENTRIES))
    if w.get('mode') not in ('shadow', 'implementation'):
        errs.append('mode must be shadow or implementation')
    if w.get('flow') is not None and w.get('flow') not in FLOWS:
        errs.append('flow invalid')
    if w.get('work_kind') is not None and w.get('work_kind') not in WORK_KINDS:
        errs.append('work_kind invalid')
    if w.get('parent') is not None and not isinstance(w.get('parent'), str):
        errs.append('parent must be a Work ID or empty')
    deps = w.get('depends_on', [])
    if not isinstance(deps, list) or not all(isinstance(x, str) and x for x in deps):
        errs.append('depends_on must be a string array')
    for field in ('issue_ref', 'project_entry_ref'):
        if not isinstance(w.get(field), str) or not w[field].strip():
            errs.append(f'{field}: nonempty URI or issue reference required')
    for name in ('normative', 'evidence'):
        items = w.get(name)
        if not isinstance(items, list) or not items:
            errs.append(f'{name}: nonempty array of source descriptors required')
            continue
        for i, src in enumerate(items):
            if not isinstance(src, dict) or not isinstance(src.get('uri'), str) or not src['uri'].strip():
                errs.append(f'{name}[{i}]: uri required')
    spec = w.get('specification')
    if not isinstance(spec, dict) or spec.get('status') not in STATUSES:
        errs.append('specification.status invalid')
    else:
        if spec['status'] == 'confirmed' and not spec.get('decision_ref'):
            errs.append('confirmed specification requires decision_ref')
        if not isinstance(spec.get('artifact_refs'), list):
            errs.append('specification.artifact_refs must be list')
    scope = w.get('scope')
    if not isinstance(scope, dict) or not isinstance(scope.get('process_ids'), list) or not scope['process_ids']:
        errs.append('scope.process_ids: nonempty array required')
    elif not all(isinstance(s, str) and s for s in scope['process_ids']):
        errs.append('scope.process_ids: must contain nonempty strings')
    if not isinstance(w.get('technologies'), list) or not all(isinstance(t, str) and t for t in w['technologies']):
        errs.append('technologies: string array required (empty permitted)')
    repos = w.get('repositories')
    if not isinstance(repos, list):
        errs.append('repositories must be an array')
    else:
        names = set()
        for i, repo in enumerate(repos):
            if not isinstance(repo, dict) or not all(isinstance(repo.get(k), str) and repo[k] for k in ('name', 'path')):
                errs.append(f'repositories[{i}]: name/path required')
                continue
            if repo['name'] in names:
                errs.append(f'duplicate repository name {repo["name"]}')
            names.add(repo['name'])
            if not isinstance(repo.get('allowed_paths', []), list) or not all(isinstance(v, str) and v for v in repo.get('allowed_paths', [])):
                errs.append(f'repositories[{i}].allowed_paths invalid')
            for path_kind in ('production_paths', 'test_paths'):
                vals = repo.get(path_kind, [])
                if not isinstance(vals, list) or not all(isinstance(v, str) and v for v in vals):
                    errs.append(f'repositories[{i}].{path_kind} invalid')
    checks = w.get('checks')
    if not isinstance(checks, list):
        errs.append('checks must be an array (empty permitted)')
    else:
        ids = set()
        for i, c in enumerate(checks):
            if not isinstance(c, dict):
                errs.append(f'checks[{i}] must be object')
                continue
            key = c.get('id')
            if not isinstance(key, str) or not ID.fullmatch(key):
                errs.append(f'checks[{i}].id invalid')
            elif key in ids:
                errs.append(f'duplicate check id: {key}')
            else:
                ids.add(key)
            if c.get('stage') not in STAGES:
                errs.append(f'checks[{i}].stage invalid')
            argv = c.get('argv')
            if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
                errs.append(f'checks[{i}].argv must be nonempty string array')
            if not isinstance(c.get('cwd'), str) or not (c['cwd'] in ('@work', '@package') or c['cwd'].startswith('@repo:')):
                errs.append(f'checks[{i}].cwd must be @work/@package/@repo:name')
            if c.get('runner') not in ('exit-zero', 'junit'):
                errs.append(f'checks[{i}].runner invalid')
            if c.get('stage') in ('red', 'green', 'regression') and c.get('runner') != 'junit':
                errs.append(f'checks[{i}]: TDD Red/Green/regression requires JUnit test evidence')
            if c.get('runner') == 'junit' and (not isinstance(c.get('test_ids'), list) or not c['test_ids']
                                              or not all(isinstance(s, str) and s for s in c['test_ids'])):
                errs.append(f'checks[{i}].test_ids required for JUnit')
            if c.get('runner') == 'exit-zero' and c.get('stage') not in ('intake', 'review', 'model', 'tests'):
                errs.append(f'checks[{i}]: exit-only evidence cannot prove {c.get("stage")} gate')
            for path_kind in ('input_paths', 'output_paths'):
                ins = c.get(path_kind, [])
                if not isinstance(ins, list) or not all(isinstance(v, str) and v and not Path(v).is_absolute() and '..' not in Path(v).parts for v in ins):
                    errs.append(f'checks[{i}].{path_kind} must be relative names within cwd')
            timeout = c.get('timeout_seconds', 120)
            if not isinstance(timeout, int) or not 1 <= timeout <= 3600:
                errs.append(f'checks[{i}].timeout_seconds outside 1..3600')
    gates = w.get('gates', [])
    if not isinstance(gates, list):
        errs.append('gates must be an array (empty permitted for legacy Work)')
    else:
        seen_gates = set()
        for i, gate in enumerate(gates):
            if not isinstance(gate, dict):
                errs.append(f'gates[{i}] must be object'); continue
            gid = gate.get('id')
            status = gate.get('status')
            evidence = gate.get('evidence', '')
            if gid not in ALL_GATES:
                errs.append(f'gates[{i}].id invalid')
            elif gid in seen_gates:
                errs.append(f'duplicate gate id: {gid}')
            else:
                seen_gates.add(gid)
            if status not in GATE_STATUSES:
                errs.append(f'gates[{i}].status invalid')
            if status in ('passed', 'not-applicable') and (not isinstance(evidence, str) or _none(evidence)):
                errs.append(f'gates[{i}].evidence required for {status}')
    compilation = w.get('compilation')
    if compilation is not None:
        if not isinstance(compilation, dict) or compilation.get('schema') != 'cat-compile/v2':
            errs.append('compilation.schema must be cat-compile/v2')
        else:
            for key in ('process', 'pi', 'tce', 'model'):
                if not isinstance(compilation.get(key), str) or not compilation[key]:
                    errs.append(f'compilation.{key} required')
            if not isinstance(compilation.get('allow_draft'), bool):
                errs.append('compilation.allow_draft must be boolean')
    return errs

