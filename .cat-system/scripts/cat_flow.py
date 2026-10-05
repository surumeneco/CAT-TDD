#!/usr/bin/env python3
"""CAT×TDD Work runner. Deterministic mechanics; never decides specification semantics.

Commands: init, validate, route, git, compile, run, status, handoff.
All user-selected executable commands are argv arrays (never shell=True).
No network access, PR/merge/deploy action, or automatic normative promotion.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from cat_artifact_lint import parse_frontmatter

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / 'config' / 'routing.json'
STAGES = ('intake', 'reverse', 'spec', 'review', 'model', 'tests', 'test-review', 'red',
          'implementation', 'green', 'refactor-scope', 'refactor', 'regression', 'ci', 'git',
          'merge', 'deployment', 'real-use')
ENTRIES = ('confirmed-spec', 'issue', 'bug', 'existing-code', 'refactor')
STATUSES = ('draft', 'candidate', 'confirmed', 'unknown', 'conflict')
GATE_STATUSES = ('passed', 'not-applicable', 'not-run', 'blocked', 'inconclusive')
EXTERNAL_GATES = ('semantic-review', 'test-oracle-review', 'red-review', 'pr-review', 'ci', 'merge', 'deployment', 'real-use')
ID = re.compile(r'^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$')

class Blocked(Exception):
    pass


def require(ok, msg):
    if not ok:
        raise Blocked(msg)


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       indent=2) + '\n').encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise Blocked(f'{path}: invalid JSON: {exc}') from exc


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
                'allowed_paths': _items(_cell(row, 'Allowed paths', 'Allowed Paths', 'allowed_paths', '許可パス'))}
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
                   ('Model','モデル'):'model',('Vectors','具体値'):'vectors',('Binding','接続'):'binding',('Tests','テスト'):'tests_output'}
        for humans, key in mapping.items():
            value = _cell(row, *humans, key, required=False)
            if not _none(value): compilation[key] = value
        compilation['allow_draft'] = _bool(_cell(row, 'Allow draft', 'allow_draft', 'Draft許可'), 'Compilation Allow draft')
    decision = fm.get('decision_ref')
    if _none(str(decision or '')): decision = None
    return {'schema': 'cat-work/v1', 'id': fm.get('id'), 'entry': fm.get('entry'), 'mode': fm.get('mode'),
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

| Name | Path | Base ref | Branch pattern | Allowed paths |
| --- | --- | --- | --- | --- |

## Checks

`Command` uses shell-like quoting only to express argv; execution never uses a shell. List cells use `;`.

| ID | Stage | Runner | CWD | Command | Test IDs | Inputs | Outputs | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |

## Gates

External/semantic gates are reported evidence. `passed` or `not-applicable` requires a concrete evidence/rationale reference.

| Gate | Status | Evidence |
| --- | --- | --- |
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

| Process | PI | TCE | Domain rule | Model | Vectors | Binding | Tests | Allow draft |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
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
            if gid not in EXTERNAL_GATES:
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


def resolve_dir(wpath, w, expr):
    if expr == '@package':
        return ROOT
    if expr == '@work':
        return wpath.parent
    if expr.startswith('@repo:'):
        name = expr[6:]
        repo = next((r for r in w['repositories'] if r['name'] == name), None)
        require(repo is not None, f'undeclared repo in cwd: {name}')
        p = Path(repo['path'])
        return (wpath.parent / p).resolve() if not p.is_absolute() else p.resolve()
    raise Blocked(f'unsupported cwd: {expr}')


def under(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def git_cmd(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=15, check=False)
    require(p.returncode == 0, f'git {args[0]} failed: {p.stderr.strip()[:250]}')
    return p.stdout.strip()


def git_snapshot(wpath, w):
    results = []
    for r in w['repositories']:
        repo = resolve_dir(wpath, w, '@repo:' + r['name'])
        item = {'name': r['name'], 'path': str(repo), 'status': 'not-run'}
        if not (repo / '.git').exists():
            item['reason'] = 'Git working tree not available locally; remote API evidence is separate'
            results.append(item)
            continue
        try:
            head = git_cmd(repo, 'rev-parse', 'HEAD')
            branch = git_cmd(repo, 'branch', '--show-current')
            remote = git_cmd(repo, 'remote', '-v').splitlines()
            base = r.get('base_ref')
            changed = set()
            if base:
                base_commit = git_cmd(repo, 'rev-parse', f'{base}^{{commit}}')
                changed.update(filter(None, git_cmd(repo, 'diff', '--name-only', '--diff-filter=ACMRDT', base_commit).splitlines()))
            else:
                changed.update(filter(None, git_cmd(repo, 'diff', '--name-only', 'HEAD').splitlines()))
            changed.update(filter(None, git_cmd(repo, 'ls-files', '--others', '--exclude-standard').splitlines()))
            allowed = r.get('allowed_paths', [])
            disallowed = sorted(p for p in changed if not any(fnmatch.fnmatchcase(p, pattern) for pattern in allowed))
            branch_ok = not r.get('branch_pattern') or fnmatch.fnmatchcase(branch, r['branch_pattern'])
            item.update(status='passed' if not disallowed and branch_ok else 'blocked',
                        head=head, branch=branch, base_ref=base, changes=sorted(changed),
                        disallowed_changes=disallowed, branch_ok=branch_ok,
                        remote_names=sorted({line.split()[0] for line in remote if line.split()}))
        except (Blocked, subprocess.TimeoutExpired, OSError) as exc:
            item.update(status='inconclusive', reason=str(exc))
        results.append(item)
    return results


def route(w, stage):
    require(stage in STAGES, f'unknown stage: {stage}')
    c = read_json(CATALOG)
    s = c.get('stages', {}).get(stage)
    require(isinstance(s, dict), f'no routing for stage: {stage}')
    adopted = c.get('technology_skills', {})
    tech = []
    unknown = []
    for t in sorted(set(w['technologies'])):
        if not s.get('include_technology_skills', False):
            continue
        if t not in adopted:
            unknown.append(t)
        else:
            tech.append(adopted[t])
    items = s['skills'] + tech
    absent = [k for k in items if not (ROOT / 'skills' / k / 'SKILL.md').exists()]
    agent = s['agent']
    require((ROOT / 'agents' / f'{agent}.agent.md').exists(), f'agent missing: {agent}')
    return {'stage': stage, 'agent': agent, 'skills': sorted(set(items)),
            'unknown_technologies': unknown, 'missing_skills': absent,
            'status': 'blocked' if unknown or absent else 'ready',
            'adoption_authority': 'project technical documents, not this catalogue'}


def workspace_root(wpath):
    # Installed runtime lives at <workspace>/.cat-system; source/test mode has no
    # authoritative workspace, so @workspace aliases the Work directory.
    return ROOT.parent.resolve() if ROOT.name == '.cat-system' else wpath.parent.resolve()


def compilation_path(wpath, w, conf, key, check):
    expr = conf[key]
    require(isinstance(expr, str) and expr, f'compilation.{key} path required')
    if expr.startswith('@work/'):
        base, rel = wpath.parent.resolve(), expr[len('@work/'):]; boundary = base
    elif expr.startswith('@workspace/'):
        base, rel = workspace_root(wpath), expr[len('@workspace/'):]; boundary = base
    elif expr.startswith('@package/'):
        base, rel = ROOT.resolve(), expr[len('@package/'):]; boundary = base
    elif expr.startswith('@repo:'):
        tail = expr[len('@repo:'):]
        require('/' in tail, f'{key}: @repo path must be @repo:<name>/<relative>')
        name, rel = tail.split('/', 1)
        base = resolve_dir(wpath, w, '@repo:' + name); boundary = base
    else:
        base, rel = wpath.parent.resolve(), expr; boundary = base
    require(not Path(rel).is_absolute() and '..' not in Path(rel).parts, f'{key} escapes allowed compilation boundary')
    p = (base / rel).resolve()
    require(under(p, boundary), f'{key} escapes allowed compilation boundary')
    require(p.is_file() or (not check and key in ('model', 'tests_output')), f'{key} not found: {p}')
    return str(p)


def compile_work(wpath, w, kind, check):
    conf = w.get('compilation')
    require(conf is not None, 'no machine-readable compilation declared: use CAT review/AI authoring')
    require(kind in ('model', 'tests'), 'kind must be model or tests')
    def loc(key):
        return compilation_path(wpath, w, conf, key, check)
    argv = [sys.executable, str(ROOT / 'scripts/cat_compile_v2.py'), kind]
    if kind == 'model':
        argv += [loc('process'), loc('pi'), loc('tce')]
        if conf.get('domain_rule'):
            argv += ['--domain-rule', loc('domain_rule')]
        argv += ['-o', loc('model')]
    else:
        for key in ('vectors', 'binding', 'tests_output'):
            require(conf.get(key), f'compilation.{key} missing')
        argv += [loc('model'), loc('vectors'), loc('binding'), '--process', loc('process'),
                 '--pi', loc('pi'), '--tce', loc('tce')]
        if conf.get('domain_rule'):
            argv += ['--domain-rule', loc('domain_rule')]
        argv += ['-o', loc('tests_output')]
    if conf['allow_draft']:
        argv.append('--allow-draft')
    if check:
        argv.append('--check')
    p = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)
    return {'command': ['python', 'scripts/cat_compile_v2.py', kind, '...'],
            'exit_code': p.returncode, 'status': 'passed' if p.returncode == 0 else 'blocked',
            'stdout': p.stdout.strip()[-1000:], 'stderr': p.stderr.strip()[-1800:],
            'normative': not conf['allow_draft'], 'check_only': check}


def junit_report(path, expected_ids):
    root = ET.parse(path).getroot()
    cases = root.findall('.//testcase')
    require(cases, 'JUnit report contains no testcase')
    by_name = {}
    for x in cases:
        key = x.get('name', '')
        # no ambiguous test name matching; required IDs must match uniquely
        by_name.setdefault(key, []).append(x)
    require(len(set(expected_ids)) == len(expected_ids), 'duplicate target IDs in Work')
    require(all(len(by_name.get(t, [])) == 1 for t in expected_ids),
            'each required JUnit test name must occur exactly once')
    def outcome(x):
        if x.find('error') is not None:
            return 'error'
        if x.find('failure') is not None:
            return 'failed'
        if x.find('skipped') is not None:
            return 'skipped'
        return 'passed'
    all_outcomes = {x.get('name', ''): outcome(x) for x in cases}
    target = {t: outcome(by_name[t][0]) for t in expected_ids}
    return all_outcomes, target


def _git_context_fingerprint(cwd):
    probe = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--show-toplevel'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if probe.returncode != 0:
        return None
    root = Path(probe.stdout.decode(errors='replace').strip()).resolve()
    head = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)
    require(head.returncode == 0, 'cannot fingerprint Git HEAD')
    diff = subprocess.run(['git', '-C', str(root), 'diff', '--binary', 'HEAD'], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)
    require(diff.returncode == 0, 'cannot fingerprint Git diff')
    untracked = subprocess.run(['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard', '-z'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(untracked.returncode == 0, 'cannot fingerprint untracked files')
    h = hashlib.sha256(); h.update(head.stdout); h.update(diff.stdout)
    for raw in sorted(x for x in untracked.stdout.split(b'\0') if x):
        rel = raw.decode(errors='surrogateescape'); path = root / rel
        h.update(raw); h.update(b'\0')
        if path.is_file(): h.update(path.read_bytes())
        else: h.update(b'<missing>')
    return 'git:' + h.hexdigest()


def context_fingerprint(cwd):
    git = _git_context_fingerprint(cwd)
    if git is not None:
        return git
    # Non-Git checks are fingerprinted recursively. Generated CAT evidence/cache and
    # common dependency/build caches are excluded; if the tree is too large, refuse
    # to claim durable evidence instead of silently ignoring dependencies.
    excluded = {'.cat-flow', '.git', 'node_modules', '.gradle', '.venv', 'venv', '__pycache__', 'dist', 'build', 'target'}
    h = hashlib.sha256(); count = 0; total = 0
    for path in sorted(cwd.rglob('*')):
        rel = path.relative_to(cwd)
        if any(part in excluded for part in rel.parts):
            continue
        if path.is_symlink():
            raise Blocked(f'context fingerprint refuses symlink: {rel}')
        if not path.is_file():
            continue
        count += 1; total += path.stat().st_size
        require(count <= 20000 and total <= 256 * 1024 * 1024,
                'non-Git command context too large to fingerprint; use a Git worktree or narrower cwd')
        h.update(str(rel).encode('utf-8', errors='surrogateescape')); h.update(b'\0'); h.update(path.read_bytes())
    return 'tree:' + h.hexdigest()


def command_work(wpath, w, key, execute=False):
    require(execute, 'commands do not run without the explicit --execute switch')
    check = next((c for c in w['checks'] if c['id'] == key), None)
    require(check is not None, f'check id not declared in Work: {key}')
    require(w['mode'] == 'implementation', 'shadow Work cannot execute declared commands; use validate/route/git/compile or an isolated external sandbox')
    if check['stage'] in ('red', 'green', 'regression'):
        require(w['mode'] == 'implementation', 'shadow Work cannot record real TDD stages')
        require(w['specification']['status'] == 'confirmed', 'no TDD gate without declared confirmed specification')
    cwd = resolve_dir(wpath, w, check['cwd'])
    require(cwd.is_dir(), f'command cwd unavailable: {cwd}')
    runtime = wpath.parent / '.cat-flow'
    reports = runtime / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    report = reports / (key + '.xml')
    require(under(report, runtime), 'invalid report path')
    argv = [a.replace('{report}', str(report)) for a in check['argv']]
    if check['runner'] == 'junit':
        require(any('{report}' in x for x in check['argv']), 'JUnit command must include {report}')
        if report.exists():
            report.unlink()  # ensure evidence was created by THIS invocation
    # Hash explicitly declared local sources; never assume remote sources are current.
    inputs = {}
    for name in check.get('input_paths', []):
        source = (cwd / name).resolve()
        require(under(source, cwd) and source.is_file(), f'check input not found under cwd: {name}')
        inputs[name] = sha(source.read_bytes())
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    outcome = 'inconclusive'
    reason = ''
    try:
        p = subprocess.run(argv, cwd=cwd, text=True, errors='replace', capture_output=True,
                           timeout=check.get('timeout_seconds', 120), check=False)
        code = p.returncode
        stdout_hash, stderr_hash = sha(p.stdout.encode()), sha(p.stderr.encode())
        if check['runner'] == 'exit-zero':
            outcome = 'passed' if code == 0 else 'blocked'
            reason = 'exit=0 for configured command' if code == 0 else 'configured command failed'
            named = None
        else:
            require(report.exists(), 'JUnit evidence missing from current invocation')
            all_cases, named = junit_report(report, check['test_ids'])
            others = [k for k, v in all_cases.items() if v in ('failed', 'error') and k not in named]
            any_skipped = [k for k, v in all_cases.items() if v == 'skipped']
            if check['stage'] == 'red':
                if code and all(v == 'failed' for v in named.values()) and not others and not any_skipped:
                    outcome = 'inconclusive'
                    reason = 'target Red failure observed; semantic cause review still required'
                else:
                    outcome = 'blocked'
                    reason = 'Red conditions unmet (no target failure / unrelated failures / skipped / exit mismatch)'
            elif code == 0 and all(v == 'passed' for v in named.values()) and not others and not any_skipped:
                outcome = 'passed'
                reason = 'declared JUnit target tests passed (only declared scope)'
            else:
                outcome = 'blocked'
                reason = 'Green/regression conditions unmet'
    except (Blocked, subprocess.TimeoutExpired, OSError, ET.ParseError) as exc:
        outcome = 'inconclusive'
        reason = str(exc)
        code = None
        stdout_hash = stderr_hash = None
        named = None
    outputs = {}
    for name in check.get('output_paths', []):
        dest = (cwd / name).resolve()
        if under(dest, cwd) and dest.is_file():
            outputs[name] = sha(dest.read_bytes())
        else:
            outcome = 'blocked'
            reason += f'; declared output missing: {name}'
    context_sha = context_fingerprint(cwd)
    evidence = {'schema': 'cat-flow-evidence/v1', 'work_id': w['id'],
                'manifest_sha256': sha(wpath.read_bytes()), 'check_id': key,
                'stage': check['stage'], 'runner': check['runner'],
                'cwd': str(cwd), 'argv': argv, 'timestamp_utc': started,
                'exit_code': code, 'stdout_sha256': stdout_hash,
                'stderr_sha256': stderr_hash,
                'input_sha256': inputs, 'output_sha256': outputs, 'context_sha256': context_sha,
                'junit_sha256': sha(report.read_bytes()) if check['runner'] == 'junit' and report.exists() else None,
                'observed_targets': named, 'verdict': outcome, 'reason': reason,
                'semantics_approved': False}
    evpath = runtime / 'evidence' / (key + '.json')
    evpath.parent.mkdir(parents=True, exist_ok=True)
    evpath.write_bytes(json_bytes(evidence))
    return {'evidence': str(evpath), **evidence}


def status_work(wpath, w):
    current_sha = sha(wpath.read_bytes())
    evidence = {}
    for c in w['checks']:
        path = wpath.parent / '.cat-flow' / 'evidence' / (c['id'] + '.json')
        if not path.is_file():
            evidence[c['id']] = {'stage': c['stage'], 'status': 'not-run'}
        else:
            e = read_json(path)
            stale_reason = None
            if e.get('manifest_sha256') != current_sha or e.get('check_id') != c['id']:
                stale_reason = 'manifest changed after run'
            else:
                try:
                    cwd = resolve_dir(wpath, w, c['cwd'])
                    if e.get('context_sha256') != context_fingerprint(cwd):
                        stale_reason = 'command context changed after run'
                    for path_kind in ('input', 'output'):
                        if stale_reason:
                            break
                        for name, digest in e.get(path_kind + '_sha256', {}).items():
                            source = (cwd / name).resolve()
                            if not (under(source, cwd) and source.is_file() and sha(source.read_bytes()) == digest):
                                stale_reason = f'{path_kind} changed after run: {name}'
                                break
                        if stale_reason:
                            break
                    if not stale_reason and e.get('junit_sha256'):
                        report = wpath.parent / '.cat-flow' / 'reports' / (c['id'] + '.xml')
                        if not report.is_file() or sha(report.read_bytes()) != e['junit_sha256']:
                            stale_reason = 'JUnit evidence changed after run'
                except (OSError, Blocked) as exc:
                    stale_reason = f'input check failed: {exc}'
            if stale_reason:
                evidence[c['id']] = {'stage': c['stage'], 'status': 'stale', 'reason': stale_reason}
            else:
                evidence[c['id']] = {'stage': c['stage'], 'status': e['verdict'],
                                     'reason': e['reason']}
    spec = w['specification']
    gate_map = {g['id']: {'status': g['status'], 'evidence': g.get('evidence', '')} for g in w.get('gates', [])}
    for gid in EXTERNAL_GATES:
        gate_map.setdefault(gid, {'status': 'not-run', 'evidence': ''})
    spec_gate = 'reported-confirmed/unverified' if spec['status'] == 'confirmed' else spec['status']
    next_actions = []
    if spec['status'] != 'confirmed':
        next_actions.append('Review observed/candidate behavior against normative sources; obtain semantic decision before using as oracle')
    if gate_map['semantic-review']['status'] not in ('passed', 'not-applicable'):
        next_actions.append('semantic-review: external/authority evidence not completed')
    for c in w['checks']:
        st = evidence[c['id']]['status']
        red_reviewed = c['stage'] == 'red' and st == 'inconclusive' and gate_map['red-review']['status'] == 'passed'
        if st != 'passed' and not red_reviewed:
            next_actions.append(f"{c['stage']}/{c['id']}: {st}; {evidence[c['id']].get('reason', 'execute or review')}")
    for gid in EXTERNAL_GATES:
        if gate_map[gid]['status'] not in ('passed', 'not-applicable'):
            next_actions.append(f"{gid}: {gate_map[gid]['status']}; external evidence or explicit rationale required")
    if not w['checks']:
        next_actions.append('Define executable checks for the scoped Work; no Red/Green evidence exists')
    git = git_snapshot(wpath, w)
    checks_ok = all(evidence[c['id']]['status'] == 'passed' or
                    (c['stage'] == 'red' and evidence[c['id']]['status'] == 'inconclusive' and
                     gate_map['red-review']['status'] == 'passed') for c in w['checks'])
    gates_ok = all(gate_map[g]['status'] in ('passed', 'not-applicable') for g in EXTERNAL_GATES)
    git_ok = all(x['status'] == 'passed' for x in git)
    reported_complete = (w['mode'] == 'implementation' and spec['status'] == 'confirmed' and
                         checks_ok and gates_ok and git_ok and bool(w['checks']))
    overall = 'reported-complete/unverified-external-evidence' if reported_complete else 'not-complete'
    return {'work_id': w['id'], 'entry': w['entry'], 'mode': w['mode'],
            'specification': spec_gate, 'checks': evidence, 'gates': gate_map,
            'git': git, 'next_actions': next_actions,
            'external_evidence_verification': 'required',
            'independent_unverified_gates': [g for g in EXTERNAL_GATES if gate_map[g]['status'] not in ('passed', 'not-applicable')],
            'overall': overall}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    init = sub.add_parser('init', help='create an unapproved Work scaffold')
    init.add_argument('--id', required=True)
    init.add_argument('-o', '--output', required=True)
    for key in ('validate', 'route', 'git', 'compile', 'run', 'status', 'handoff'):
        p = sub.add_parser(key)
        p.add_argument('--work', required=True)
        if key == 'route':
            p.add_argument('--stage', choices=STAGES, required=True)
        if key == 'compile':
            p.add_argument('--kind', choices=('model', 'tests'), required=True)
            p.add_argument('--check', action='store_true')
        if key == 'run':
            p.add_argument('--id', required=True)
            p.add_argument('--execute', action='store_true', help='explicitly execute the declared command')
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'init':
            require(ID.fullmatch(args.id), 'invalid Work id')
            p = Path(args.output).resolve()
            require(not p.exists(), 'will not overwrite existing Work')
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix.lower() == '.json':
                p.write_bytes(json_bytes({'schema': 'cat-work/v1', 'id': args.id,
                    'entry': 'issue', 'mode': 'shadow', 'issue_ref': 'TO_BE_IDENTIFIED',
                    'project_entry_ref': 'TO_BE_IDENTIFIED',
                    'normative': [{'uri': 'TO_BE_IDENTIFIED'}],
                    'evidence': [{'uri': 'TO_BE_IDENTIFIED'}],
                    'specification': {'status': 'unknown', 'decision_ref': None, 'artifact_refs': []},
                    'scope': {'process_ids': [], 'changed_ids': [], 'preserved_ids': []},
                    'technologies': [], 'repositories': [], 'checks': []}))
            else:
                p.write_text(render_work_markdown(args.id), encoding='utf-8', newline='\n')
            result = {'created': str(p), 'status': 'incomplete-template',
                      'warning': 'placeholder references are NOT verified sources'}
        else:
            p, w = work_file(args.work)
            if args.cmd == 'validate':
                placeholders = []
                for name in ('issue_ref', 'project_entry_ref'):
                    if 'TO_BE_IDENTIFIED' in w[name]:
                        placeholders.append(name)
                placeholders += [f'{n}[{i}]' for n in ('normative', 'evidence') for i, s in enumerate(w[n])
                                 if 'TO_BE_IDENTIFIED' in s['uri']]
                result = {'status': 'blocked' if placeholders else 'passed',
                          'contract_valid': True, 'unresolved_source_placeholders': placeholders,
                          'semantic_approval_verified': False}
            elif args.cmd == 'route':
                result = route(w, args.stage)
            elif args.cmd == 'git':
                result = {'repos': git_snapshot(p, w)}
            elif args.cmd == 'compile':
                result = compile_work(p, w, args.kind, args.check)
            elif args.cmd == 'run':
                result = command_work(p, w, args.id, args.execute)
            else:
                result = status_work(p, w)
        print(json_bytes(result).decode(), end='')
        if args.cmd == 'validate' and result['status'] != 'passed':
            return 2
        if args.cmd in ('route', 'compile', 'run') and result['status' if args.cmd != 'run' else 'verdict'] not in ('passed', 'ready'):
            return 2
        return 0
    except (Blocked, OSError, subprocess.TimeoutExpired) as exc:
        print(json_bytes({'status': 'blocked', 'error': str(exc)}).decode(), file=sys.stderr, end='')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())