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
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from catlib.common import Blocked, json_bytes, read_json, require, sha
from catlib.work import ALL_GATES, CONFORMANCE_GATES, EXTERNAL_GATES, ID, STAGES, read_work_markdown, render_work_markdown, validate, work_file
import cat_queue
import cat_scope_order
import cat_implementation_obligations as obligation_runtime

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / 'config' / 'routing.json'


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


def infer_flow(w):
    explicit = w.get('flow')
    if explicit:
        return explicit
    return {'confirmed-spec':'spec-implementation','issue':'issue-work','bug':'issue-work',
            'existing-code':'code-to-spec','refactor':'refactor'}.get(w.get('entry'),'issue-work')


def route(w, stage):
    require(stage in STAGES, f'unknown stage: {stage}')
    c = read_json(CATALOG)
    require(c.get('schema') == 'cat-routing/v2', 'routing schema must be cat-routing/v2')
    s = c.get('stages', {}).get(stage)
    require(isinstance(s, dict), f'no routing for stage: {stage}')
    executor = s.get('executor')
    require(isinstance(executor, dict) and executor.get('type') and executor.get('id'),
            f'invalid executor for stage: {stage}')
    adopted = c.get('technology_skills', {})
    tech = []
    unknown = []
    for t in sorted(set(w['technologies'])):
        if not s.get('include_technology_skills', False):
            continue
        if t not in adopted:
            unknown.append(t)
        else:
            mapped = adopted[t]
            require(isinstance(mapped, str) or
                    (isinstance(mapped, list) and mapped and all(isinstance(x, str) and x for x in mapped)),
                    f'invalid technology skill mapping: {t}')
            tech.extend([mapped] if isinstance(mapped, str) else mapped)
    items = list(s.get('skills', [])) + tech
    absent = [k for k in items if not (ROOT / 'skills' / k / 'SKILL.md').exists()]
    agents = []
    if executor['type'] == 'agent':
        agents.append(executor['id'])
    for cond in s.get('conditional', {}).values():
        if isinstance(cond, dict) and cond.get('type') == 'agent':
            agents.append(cond.get('id'))
    missing_agents = [a for a in agents if not (ROOT / 'agents' / f'{a}.agent.md').exists()]
    flow = infer_flow(w)
    flows = c.get('flows', {})
    require(flow in flows, f'unknown Work flow: {flow}')
    permitted = stage in flows[flow].get('stages', []) or stage in ('git','ci','merge','deployment','real-use','test-review','promotion')
    guard_required = executor.get('type') == 'agent' and bool(s.get('permissions', {}).get('write'))
    return {'stage': stage, 'flow': flow, 'executor': executor, 'guard_required': guard_required,
            'conditional': s.get('conditional', {}), 'permissions': s.get('permissions', {}),
            'on_result': s.get('on_result', {}), 'skills': sorted(set(items)),
            'unknown_technologies': unknown, 'missing_skills': absent,
            'missing_agents': missing_agents, 'stage_in_flow': permitted,
            'status': 'blocked' if unknown or absent or missing_agents or not permitted else 'ready',
            'adoption_authority': 'project technical documents, not this catalogue'}
def execution_route(w, stage, conditional=None):
    r=route(w,stage)
    if conditional is None:
        return r
    executor=r.get('conditional',{}).get(conditional)
    require(isinstance(executor,dict) and executor.get('type')=='agent' and executor.get('id'),
            f'no conditional Agent for {stage}:{conditional}')
    result=dict(r)
    result['base_executor']=r['executor']
    result['executor']=executor
    result['conditional_key']=conditional
    result['guard_required']=bool(r.get('permissions',{}).get('write'))
    return result


def workspace_root(wpath):
    # Standard Work placement is <workspace>/Lifecycle/Works/<state>/<id>/Work.md.
    # Recover that workspace boundary even when the runtime itself is invoked from
    # a source checkout (tests/tools) rather than the installed .cat-system tree.
    resolved=Path(wpath).resolve()
    for ancestor in resolved.parents:
        if ancestor.name=='Lifecycle' and (ancestor/'Works').is_dir():
            return ancestor.parent.resolve()
    installed = ROOT.parent.resolve()
    return installed if under(resolved, installed) else resolved.parent.resolve()


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
    require(p.is_file() or (not check and key in ('model', 'vectors', 'queue', 'tests_output', 'obligations')), f'{key} not found: {p}')
    return str(p)


def compilation_tce_paths(wpath, w, conf, check):
    refs = conf.get('tces') or [conf.get('tce')]
    require(isinstance(refs, list) and refs and all(isinstance(x, str) and x for x in refs),
            'compilation.tces must contain one or more paths')
    result = []
    for expr in refs:
        local = dict(conf)
        local['tce'] = expr
        result.append(compilation_path(wpath, w, local, 'tce', check))
    return result


def compile_work(wpath, w, kind, check):
    conf = w.get('compilation')
    require(conf is not None, 'no machine-readable compilation declared')
    require(kind in ('model', 'vectors', 'queue', 'tests'), 'kind must be model, vectors, queue or tests')
    unsupported = [key for key in ('common_rules', 'domain_specs') if conf.get(key)]
    require(not unsupported, 'normative compiler does not map declared CommonRule/DomainSpec inputs: ' + ', '.join(unsupported))
    def loc(key):
        return compilation_path(wpath, w, conf, key, check)
    argv = [sys.executable, str(ROOT / 'scripts/cat_compile_v2.py'), kind]
    if kind == 'model':
        process = loc('process')
        pi = loc('pi')
        tces = compilation_tce_paths(wpath, w, conf, check)
        argv += [process, pi, *tces]
    else:
        require(conf.get('model'), 'compilation.model missing')
        if kind == 'vectors':
            argv += [loc('model')]
        else:
            require(conf.get('vectors'), 'compilation.vectors missing')
            argv += [loc('model'), loc('vectors')]
            if kind == 'tests':
                for key in ('binding', 'queue', 'tests_output'):
                    require(conf.get(key), f'compilation.{key} missing')
                argv += [loc('binding'), '--queue', loc('queue')]
        process = loc('process')
        pi = loc('pi')
        tces = compilation_tce_paths(wpath, w, conf, check)
        argv += ['--process', process, '--pi', pi]
        for tce in tces:
            argv += ['--tce', tce]
    if conf.get('domain_rule'):
        argv += ['--domain-rule', loc('domain_rule')]
    output_key = {'model':'model','vectors':'vectors','queue':'queue','tests':'tests_output'}[kind]
    argv += ['-o', loc(output_key)]
    if conf['allow_draft']:
        argv.append('--allow-draft')
    if check:
        argv.append('--check')
    p = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)
    return {'command': ['python', 'scripts/cat_compile_v2.py', kind, '...'],
            'exit_code': p.returncode, 'status': 'passed' if p.returncode == 0 else 'blocked',
            'stdout': p.stdout.strip()[-1000:], 'stderr': p.stderr.strip()[-1800:],
            'normative': not conf['allow_draft'], 'check_only': check}

def obligations_work(wpath, w, check=False):
    conf = w.get('compilation')
    require(conf is not None, 'implementation obligations require Compilation inputs')
    require(conf.get('obligations'), 'compilation.obligations missing')
    unsupported = [key for key in ('common_rules', 'domain_specs') if conf.get(key)]
    require(not unsupported, 'implementation obligations cannot omit declared CommonRule/DomainSpec semantics: ' + ', '.join(unsupported))
    def loc(key, exists=True):
        return compilation_path(wpath, w, conf, key, exists)
    tces = compilation_tce_paths(wpath, w, conf, True)
    output = loc('obligations', check)
    argv = [sys.executable, str(ROOT / 'scripts/cat_implementation_obligations.py'),
            loc('process'), loc('pi'), *tces]
    if conf.get('domain_rule'):
        argv += ['--domain-rule', loc('domain_rule')]
    for technology in sorted(set(w.get('technologies', []))):
        argv += ['--technology', technology]
    argv += ['-o', output]
    if check:
        argv.append('--check')
    p = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)
    return {'command': ['python', 'scripts/cat_implementation_obligations.py', '...'],
            'exit_code': p.returncode, 'status': 'passed' if p.returncode == 0 else 'blocked',
            'stdout': p.stdout.strip()[-1200:], 'stderr': p.stderr.strip()[-1800:],
            'check_only': check, 'output': output}


def technology_conformance(wpath, w, conf):
    results = []
    technologies = set(w.get('technologies', []))
    if 'TypeScript' in technologies:
        if not conf.get('conformance_binding'):
            return {'status': 'inconclusive', 'results': [],
                    'reason': 'TypeScript implementation-conformance requires Compilation Conformance binding'}
        binding_path = Path(compilation_path(wpath, w, conf, 'conformance_binding', True))
        binding = read_json(binding_path)
        require(binding.get('schema') == 'cat-typescript-conformance-binding/v1',
                'wrong TypeScript conformance binding schema')
        repo_name = binding.get('repository')
        require(isinstance(repo_name, str) and repo_name, 'TypeScript conformance binding repository required')
        repo_root = resolve_dir(wpath, w, '@repo:' + repo_name)
        argv = [sys.executable,
                str(ROOT / 'skills/tech-typescript/scripts/cat_typescript_conformance.py'),
                '--repo', str(repo_root), '--binding', str(binding_path),
                '--process', compilation_path(wpath, w, conf, 'process', True),
                '--pi', compilation_path(wpath, w, conf, 'pi', True)]
        p = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)
        payload = None
        raw = (p.stdout or p.stderr).strip()
        if raw:
            try:
                payload = __import__('json').loads(raw)
            except ValueError:
                payload = {'status': 'inconclusive', 'error': raw[-1600:]}
        if not isinstance(payload, dict):
            payload = {'status': 'inconclusive', 'error': 'technology inspector produced no structured result'}
        results.append({'technology': 'TypeScript', **payload})
    statuses = [x.get('status', 'inconclusive') for x in results]
    if any(x == 'blocked' for x in statuses):
        return {'status': 'blocked', 'results': results, 'reason': 'technology conformance violation'}
    if any(x != 'passed' for x in statuses):
        return {'status': 'inconclusive', 'results': results, 'reason': 'technology conformance evidence incomplete'}
    return {'status': 'passed', 'results': results, 'reason': 'available technology inspectors passed'}


def conformance_context_sha(w):
    payload = {
        'id': w['id'],
        'flow': infer_flow(w),
        'specification': w['specification'],
        'scope': w['scope'],
        'compilation': w.get('compilation'),
        'repositories': w.get('repositories', []),
    }
    return sha(json_bytes(payload))


def conformance_input_hashes(wpath, w, kind):
    conf = w.get('compilation') or {}
    keys = ['process', 'pi', 'domain_rule']
    if kind == 'model-conformance':
        keys.append('model')
    elif kind == 'implementation-conformance':
        keys.extend(['model','queue','obligations'])
        if conf.get('conformance_binding'):
            keys.append('conformance_binding')
    result = {}
    for key in keys:
        if not conf.get(key):
            continue
        path = Path(compilation_path(wpath, w, conf, key, True))
        result[key] = {'path': str(path), 'sha256': sha(path.read_bytes())}
    for index, raw in enumerate(compilation_tce_paths(wpath, w, conf, True), 1):
        path = Path(raw)
        result['tce:' + str(index)] = {'path': str(path), 'sha256': sha(path.read_bytes())}
    return result


def record_conformance_evidence(wpath, w, kind, result):
    runtime = wpath.parent / '.cat-flow' / 'conformance'
    runtime.mkdir(parents=True, exist_ok=True)
    supporting = result.get('evidence')
    payload = {
        'schema': 'cat-conformance-evidence/v1',
        'work_id': w['id'],
        'gate': kind,
        'context_sha256': conformance_context_sha(w),
        'input_sha256': conformance_input_hashes(wpath, w, kind),
        'verdict': result['status'],
        'reason': result.get('reason', ''),
        'supporting_evidence': supporting,
    }
    if kind == 'implementation-conformance':
        payload['repo_state_sha256'] = sha(json_bytes(_repo_state(wpath, w)))
    path = runtime / (kind + '.json')
    path.write_bytes(json_bytes(payload))
    output = dict(result)
    output['supporting_evidence'] = supporting
    output['evidence'] = str(path)
    return output


def conformance_evidence_status(wpath, w, kind):
    path = wpath.parent / '.cat-flow' / 'conformance' / (kind + '.json')
    if not path.is_file():
        return {'status': 'not-run', 'evidence': '', 'reason': 'deterministic conformance evidence missing'}
    try:
        e = read_json(path)
        if e.get('schema') != 'cat-conformance-evidence/v1' or e.get('work_id') != w['id'] or e.get('gate') != kind:
            return {'status': 'stale', 'evidence': str(path), 'reason': 'conformance evidence identity mismatch'}
        if e.get('context_sha256') != conformance_context_sha(w):
            return {'status': 'stale', 'evidence': str(path), 'reason': 'conformance context changed'}
        for item in e.get('input_sha256', {}).values():
            p = Path(item['path'])
            if not p.is_file() or sha(p.read_bytes()) != item['sha256']:
                return {'status': 'stale', 'evidence': str(path), 'reason': 'conformance input changed'}
        if kind == 'implementation-conformance':
            if e.get('repo_state_sha256') != sha(json_bytes(_repo_state(wpath, w))):
                return {'status': 'stale', 'evidence': str(path), 'reason': 'implementation repository state changed'}
        return {'status': e.get('verdict', 'inconclusive'), 'evidence': str(path), 'reason': e.get('reason', '')}
    except (OSError, KeyError, Blocked):
        return {'status': 'stale', 'evidence': str(path), 'reason': 'conformance evidence cannot be revalidated'}


def conformance_work(wpath, w, kind):
    require(kind in CONFORMANCE_GATES, 'unknown conformance gate')
    conf = w.get('compilation')
    require(conf is not None, 'conformance requires Compilation inputs')
    unmapped = [key for key in ('common_rules', 'domain_specs') if conf.get(key)]
    if unmapped:
        return {'gate': kind, 'status': 'blocked',
                'reason': 'declared CommonRule/DomainSpec semantics are not mapped by the normative compiler: ' + ', '.join(unmapped)}
    if kind == 'process-closure':
        if len(w['scope']['process_ids']) != 1:
            return {'gate':kind,'status':'inconclusive',
                    'reason':'current deterministic compiler proves one Process at a time; assembled multi-Process closure requires explicit composition evidence'}
        runtime = wpath.parent / '.cat-flow' / 'cache'
        runtime.mkdir(parents=True, exist_ok=True)
        def loc(key): return compilation_path(wpath, w, conf, key, False)
        tces = compilation_tce_paths(wpath, w, conf, True)
        argv=[sys.executable,str(ROOT/'scripts/cat_compile_v2.py'),'model',loc('process'),loc('pi'),*tces]
        if conf.get('domain_rule'): argv += ['--domain-rule',loc('domain_rule')]
        argv += ['-o',str(runtime/'process-closure.model.json')]
        p=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True,timeout=60,check=False)
        if p.returncode == 0:
            model = read_json(runtime/'process-closure.model.json')
            if model.get('coverage_requirement') != 'closed':
                return {'gate':kind,'status':'inconclusive','evidence':str(runtime/'process-closure.model.json'),
                        'reason':'local TCE coverage is partial; assembled Process closure requires additional deterministic or review evidence'}
            if not all(x.get('result') == 'proved' for x in model.get('coverage_checks', {}).values()):
                return {'gate':kind,'status':'inconclusive','evidence':str(runtime/'process-closure.model.json'),
                        'reason':'closed-world declaration exists but closure proof is incomplete'}
            return {'gate':kind,'status':'passed','evidence':str(runtime/'process-closure.model.json'),
                    'reason':'supported finite closed-world coverage compiled and proved from confirmed sources'}
        msg=(p.stderr or p.stdout).strip()
        inconclusive_markers=('currently supports','unproven','non-finite','requires a technology','unsupported')
        status='inconclusive' if any(x in msg for x in inconclusive_markers) else 'blocked'
        return {'gate':kind,'status':status,'reason':msg[-1800:]}
    if kind == 'model-conformance':
        require(conf.get('model'), 'model-conformance requires Compilation Model')
        def loc(key): return compilation_path(wpath, w, conf, key, True)
        argv=[sys.executable,str(ROOT/'scripts/cat_model_conformance.py'),loc('process'),loc('pi'),loc('model')]
        for tce in compilation_tce_paths(wpath, w, conf, True):
            argv += ['--tce', tce]
        if conf.get('domain_rule'): argv += ['--domain-rule',loc('domain_rule')]
        p=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True,timeout=60,check=False)
        if p.returncode == 0:
            return {'gate':kind,'status':'passed','evidence':p.stdout.strip(),
                    'reason':'independent source-to-TestModel semantic inventory matched'}
        msg=(p.stderr or p.stdout).strip()
        status='inconclusive' if any(x in msg for x in ('unsupported','currently supports','unproven','cannot compare')) else 'blocked'
        return {'gate':kind,'status':status,'reason':msg[-1800:]}
    tech = technology_conformance(wpath, w, conf)
    if tech['status'] == 'blocked':
        return {'gate': kind, 'status': 'blocked', 'reason': tech['reason'],
                'technology_results': tech['results']}
    require(conf.get('obligations'), 'implementation-conformance requires Compilation Obligations')
    obligation_check=obligations_work(wpath,w,check=True)
    if obligation_check['status'] != 'passed':
        return {'gate':kind,'status':'blocked',
                'reason':obligation_check.get('stderr') or 'implementation obligation skeleton is stale or not deterministic'}
    path=compilation_path(wpath,w,conf,'obligations',True)
    skeleton=read_json(Path(path))
    require(skeleton.get('schema')=='cat-implementation-obligations/v1','wrong implementation obligation schema')
    queue=None
    if conf.get('queue'):
        qpath=Path(compilation_path(wpath,w,conf,'queue',True))
        queue=read_json(qpath)
    model_gate=conformance_evidence_status(wpath,w,'model-conformance')
    data=obligation_runtime.aggregate(skeleton,queue,tech['results'],model_gate)
    runtime=wpath.parent/'.cat-flow'/'cache'
    runtime.mkdir(parents=True,exist_ok=True)
    evaluated=runtime/'implementation-obligations-evaluated.json'
    evaluated.write_bytes(json_bytes(data))
    items=data.get('items')
    require(isinstance(items,list) and items,'implementation obligations required')
    required={'interface','capability','behavior','invariant','cross-process','domain','implementation-constraint'}
    categories=set()
    for item in items:
        require(isinstance(item,dict),'obligation must be object')
        require(item.get('category') in required,'unknown obligation category')
        require(isinstance(item.get('source_ref'),str) and item['source_ref'],'obligation source_ref required')
        require(isinstance(item.get('method'),str) and item['method'],'obligation verification method required')
        require(isinstance(item.get('limitation'),str) and item['limitation'],'obligation limitation required')
        require(item.get('status') in ('passed','failed','inconclusive','not-run'),'invalid obligation status')
        if item['status'] in ('passed','failed'):
            require(isinstance(item.get('evidence'),str) and item['evidence'],item['status']+' obligation needs evidence')
        if item['status'] in ('inconclusive','not-run'):
            require(isinstance(item.get('reason'),str) and item['reason'],item['status']+' obligation needs reason')
        categories.add(item['category'])
    missing=sorted(required-categories)
    base={'missing_categories':missing,'technology_results':tech['results'],
          'evaluated_obligations':str(evaluated)}
    if any(x['status']=='failed' for x in items):
        return {'gate':kind,'status':'blocked','reason':'one or more implementation obligations failed',**base}
    if missing or any(x['status'] in ('inconclusive','not-run') for x in items):
        return {'gate':kind,'status':'inconclusive','reason':'obligations are incomplete or not machine-decidable',**base}
    if tech['status'] != 'passed':
        return {'gate':kind,'status':'inconclusive','reason':tech['reason'],**base}
    return {'gate':kind,'status':'passed',
            'reason':'all CAT implementation obligations and available technology inspectors passed',**base}


def _repo_state(wpath,w):
    result={}
    for repo in w['repositories']:
        root=resolve_dir(wpath,w,'@repo:'+repo['name'])
        if not (root/'.git').exists():
            continue
        p=subprocess.run(['git','-C',str(root),'ls-files','-co','--exclude-standard','-z'],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        require(p.returncode==0,'cannot snapshot repository files')
        state={}
        for raw in p.stdout.split(b'\0'):
            if not raw: continue
            rel=raw.decode(errors='surrogateescape');path=root/rel
            if path.is_file(): state[rel]=sha(path.read_bytes())
        result[repo['name']]=state
    return result


def _workspace_state(wpath, w):
    root = workspace_root(wpath)
    repo_roots = []
    for repo in w.get('repositories', []):
        try:
            repo_roots.append(resolve_dir(wpath, w, '@repo:' + repo['name']))
        except Blocked:
            pass
    excluded = {'.git', '__pycache__', 'node_modules', '.gradle', '.venv', 'venv', 'dist', 'build', 'target'}
    state = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if any(part in excluded for part in rel.parts):
            continue
        parts=rel.parts
        if any(parts[i]=='.cat-flow' and i+1 < len(parts) and parts[i+1]=='guards'
               for i in range(len(parts))):
            continue
        if any(under(path, repo_root) for repo_root in repo_roots):
            continue
        state[str(rel)] = sha(path.read_bytes())
    return state


def _workspace_write_patterns(wpath, w, permissions):
    mapping = {
        'Lifecycle/Tasks': ['Lifecycle/Tasks/**'],
        'Lifecycle/Works': ['Lifecycle/Works/**'],
        'CAT/Candidates': ['Lifecycle/CAT/Candidates/**'],
        'CAT/Draft': ['Lifecycle/CAT/Draft/**'],
        'Review': ['Lifecycle/CAT/Reviews/**', 'Lifecycle/TDD/Results/**', 'Lifecycle/Reviews/**'],
        'REF/Scopes': ['Lifecycle/REF/Scopes/**'],
        'Workflow': ['Lifecycle/Workflow/**'],
    }
    patterns = []
    for token in permissions.get('write', []):
        patterns.extend(mapping.get(token, []))
    root = workspace_root(wpath)
    if '.cat-flow/evidence' in permissions.get('write', []):
        ev = (wpath.parent / '.cat-flow' / 'evidence').resolve()
        if under(ev, root):
            patterns.append(str(ev.relative_to(root)) + '/**')
    return patterns


def _lifecycle_scope_ready(wpath,w):
    root=workspace_root(wpath)
    lifecycle=root/'Lifecycle'/'Works'
    if not lifecycle.is_dir() or not under(wpath,lifecycle):
        require(not (w.get('parent') or w.get('depends_on')),
                'cannot verify deepest-ready scope outside standard Lifecycle/Works placement')
        return {'enforced':False,'ready':True}
    active=[]
    completed=set()
    blocked_ids=set()
    for state in ('New','InProgress','Blocked','Completed','Cancelled'):
        base=lifecycle/state
        if not base.is_dir():
            continue
        for work_dir in sorted(x for x in base.iterdir() if x.is_dir()):
            if state=='Completed':
                completed.add(work_dir.name)
                continue
            if state=='Cancelled':
                continue
            if state=='Blocked':
                blocked_ids.add(work_dir.name)
            candidates=[work_dir/'Work.md',work_dir/'work.json']
            hit=next((x for x in candidates if x.is_file()),None)
            if hit:
                active.append(str(hit))
    require(active,'Lifecycle/Works contains no active Work manifests')
    order=cat_scope_order.build(active,completed)
    ready={x['id'] for x in order['ready'] if x['id'] not in blocked_ids}
    require(w['id'] in ready,
            'Work is not a deepest ready scope; ready='+','.join(sorted(ready)))
    return {'enforced':True,'ready':True,'ready_ids':sorted(ready)}


def _pending_guard(wpath,w,except_stage=None,except_conditional=None):
    folder=wpath.parent/'.cat-flow'/'guards'
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob('*.json')):
        try:
            data=read_json(path)
        except Exception:
            continue
        if data.get('work_id')!=w['id']:
            continue
        if data.get('stage')==except_stage and data.get('conditional')==except_conditional:
            continue
        if data.get('verdict') not in ('passed',):
            return {'stage':data.get('stage'),'verdict':data.get('verdict','pending'),'path':str(path)}
    return None


def _verified_refactor_baseline(wpath,w):
    checks=[x for x in w.get('checks',[]) if x.get('stage')=='refactor-baseline']
    require(checks,'refactor requires at least one declared refactor-baseline check')
    refs=[]
    for check in checks:
        path=wpath.parent/'.cat-flow'/'evidence'/(check['id']+'.json')
        require(path.is_file(),'refactor baseline evidence missing: '+check['id'])
        evidence=read_json(path)
        require(evidence.get('work_id')==w['id'] and evidence.get('check_id')==check['id'],
                'refactor baseline evidence identity mismatch')
        require(evidence.get('stage')=='refactor-baseline' and evidence.get('verdict')=='passed',
                'refactor baseline must be passed')
        cwd=resolve_dir(wpath,w,check['cwd'])
        require(evidence.get('context_sha256')==context_fingerprint(cwd),
                'refactor baseline is stale for current source state')
        refs.append({'check_id':check['id'],'evidence':str(path),'context_sha256':evidence['context_sha256']})
    return refs


def guard_work(wpath,w,stage,phase,conditional=None):
    r=execution_route(w,stage,conditional)
    require(r['status']=='ready', 'cannot guard blocked route')
    require(r.get('guard_required'), 'write guard is only required for writing Agent stages')
    guard_id=stage + (('--'+conditional) if conditional else '')
    path=wpath.parent/'.cat-flow'/'guards'/(guard_id+'.json')
    if phase=='start':
        if path.is_file():
            previous=read_json(path)
            require(previous.get('verdict')=='passed',
                    'existing same-stage guard is pending/blocked; cannot replace its baseline')
        pending=_pending_guard(wpath,w,except_stage=stage,except_conditional=conditional)
        require(pending is None, 'previous Agent write guard is not passed: '+str(pending))
        scope=_lifecycle_scope_ready(wpath,w)
        refactor_baseline=_verified_refactor_baseline(wpath,w) if stage=='refactor' else []
        path.parent.mkdir(parents=True,exist_ok=True)
        payload={'schema':'cat-write-guard/v3','work_id':w['id'],'stage':stage,
                 'conditional':conditional,
                 'manifest_sha256':sha(wpath.read_bytes()),'repo_state':_repo_state(wpath,w),
                 'workspace_state':_workspace_state(wpath,w),
                 'permissions':r['permissions'],'scope_order':scope,
                 'refactor_baseline':refactor_baseline,'verdict':'pending'}
        path.write_bytes(json_bytes(payload))
        return {'status':'passed','guard':str(path),'stage':stage,'conditional':conditional,
                'scope_order':scope}
    require(path.is_file(),'guard baseline missing')
    base=read_json(path);require(base.get('manifest_sha256')==sha(wpath.read_bytes()),'Work changed after guard start')
    require(base.get('schema')=='cat-write-guard/v3','guard baseline schema stale; restart guard')
    after=_repo_state(wpath,w);violations=[]
    repo_write='repo:production' in r['permissions'].get('write',[])
    for repo in w['repositories']:
        before=base['repo_state'].get(repo['name'],{});now=after.get(repo['name'],{})
        changed=sorted(k for k in set(before)|set(now) if before.get(k)!=now.get(k))
        if repo_write:
            allowed=repo.get('production_paths') or repo.get('allowed_paths',[])
        else:
            allowed=[]
        bad=[p for p in changed if not any(fnmatch.fnmatchcase(p,pat) for pat in allowed)]
        if bad: violations.append({'repository':repo['name'],'paths':bad})
    before_ws=base.get('workspace_state',{});now_ws=_workspace_state(wpath,w)
    changed_ws=sorted(k for k in set(before_ws)|set(now_ws) if before_ws.get(k)!=now_ws.get(k))
    allowed_ws=_workspace_write_patterns(wpath,w,r['permissions'])
    bad_ws=[p for p in changed_ws if not any(fnmatch.fnmatchcase(p,pat) for pat in allowed_ws)]
    if bad_ws: violations.append({'workspace':str(workspace_root(wpath)),'paths':bad_ws})
    verdict='blocked' if violations else 'passed'
    base['verdict']=verdict;base['violations']=violations;base['finished_manifest_sha256']=sha(wpath.read_bytes())
    path.write_bytes(json_bytes(base))
    return {'status':verdict,'stage':stage,'conditional':conditional,'violations':violations,
            'workspace_allowed':allowed_ws,'guard':str(path)}


def queue_state_work(wpath,w,evidence_path):
    conf=w.get('compilation') or {}
    require(conf.get('queue'),'queue-state requires Compilation Queue')
    qpath=Path(compilation_path(wpath,w,conf,'queue',True))
    qfile,queue=cat_queue.load(qpath)
    current=cat_queue.current(queue)
    require(current is not None,'Queue has no current item')
    evidence=Path(evidence_path).resolve()
    allowed=(wpath.parent/'.cat-flow'/'evidence').resolve()
    require(under(evidence,allowed) and evidence.is_file(),'queue-state evidence must be script-owned .cat-flow/evidence')
    ev=read_json(evidence)
    require(ev.get('schema')=='cat-flow-evidence/v1' and ev.get('work_id')==w['id'],'invalid Green evidence identity')
    require(ev.get('stage')=='green' and ev.get('verdict')=='passed','Queue item can be done only from passed Green evidence')
    qc=ev.get('queue_context') or {}
    require(qc.get('current_item_id')==current['id'],'Green evidence does not belong to current Queue item')
    require(qc.get('sha256')==sha(qpath.read_bytes()),'Queue changed since Green evidence')
    current['status']='done';current['evidence_ref']=str(evidence)
    nxt=cat_queue.activate_next(queue)
    cat_queue.save(qfile,queue)
    return {'status':'passed','outcome':'next-item' if nxt else 'complete',
            'transitioned':current['id'],'current':nxt,'queue':str(qpath),
            'next_stage':'tests' if nxt else 'implementation-conformance'}


def handoff_work(wpath,w,stage,conditional=None):
    pending=_pending_guard(wpath,w,except_stage=stage,except_conditional=conditional)
    require(pending is None,'cannot hand off while prior Agent guard is pending/blocked: '+str(pending))
    r=execution_route(w,stage,conditional)
    st=status_work(wpath,w)
    guard=None
    if r.get('guard_required') and r.get('status')=='ready':
        guard=guard_work(wpath,w,stage,'start',conditional)
    conf=w.get('compilation') or {}
    source=[]
    for key in ('process','pi','tce','domain_rule','model','queue','obligations'):
        if not conf.get(key): continue
        try:
            p=Path(compilation_path(wpath,w,conf,key,True))
            source.append({'kind':key,'path':str(p),'sha256':sha(p.read_bytes())})
        except (Blocked,OSError):
            source.append({'kind':key,'status':'missing-or-unresolved'})
    current=None
    if conf.get('queue'):
        try:
            q=read_json(Path(compilation_path(wpath,w,conf,'queue',True)))
            hit=[x for x in q.get('items',[]) if x.get('status')=='current']
            if len(hit)==1: current=hit[0]
        except (Blocked,OSError): pass
    stale=[{'check':k,**v} for k,v in st['checks'].items() if v['status']=='stale']
    return {'schema':'cat-handoff/v1','work_id':w['id'],'flow':r['flow'],'stage':stage,
            'executor':r['executor'],'permissions':r['permissions'],'source_state':source,
            'current_queue_item':current,'specification':st['specification'],
            'unresolved_decision':w['specification']['status']!='confirmed',
            'evidence_refs':[x['uri'] for x in w['evidence']],
            'stale_inputs':stale,'next_permitted_action':r['executor'],
            'route_status':r['status'],'conditional_key':conditional,'guard':guard}
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


def _queue_context(wpath,w):
    conf=w.get('compilation') or {}
    if not conf.get('queue'):
        return None
    path=Path(compilation_path(wpath,w,conf,'queue',True))
    queue=read_json(path)
    current=[x for x in queue.get('items',[]) if x.get('status')=='current']
    require(len(current)<=1,'Queue may contain at most one current item')
    return {'path':str(path),'sha256':sha(path.read_bytes()),
            'current_item_id':current[0]['id'] if current else None}


def command_work(wpath, w, key, execute=False):
    require(execute, 'commands do not run without the explicit --execute switch')
    check = next((c for c in w['checks'] if c['id'] == key), None)
    require(check is not None, f'check id not declared in Work: {key}')
    require(w['mode'] == 'implementation', 'shadow Work cannot execute declared commands; use validate/route/git/compile or an isolated external sandbox')
    if check['stage'] in ('red', 'green', 'regression', 'refactor-baseline'):
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
    queue_context = _queue_context(wpath,w) if check['stage'] in ('red','green') else None
    evidence = {'schema': 'cat-flow-evidence/v1', 'work_id': w['id'],
                'manifest_sha256': sha(wpath.read_bytes()), 'check_id': key,
                'stage': check['stage'], 'runner': check['runner'],
                'cwd': str(cwd), 'argv': argv, 'timestamp_utc': started,
                'exit_code': code, 'stdout_sha256': stdout_hash,
                'stderr_sha256': stderr_hash,
                'input_sha256': inputs, 'output_sha256': outputs, 'context_sha256': context_sha,
                'junit_sha256': sha(report.read_bytes()) if check['runner'] == 'junit' and report.exists() else None,
                'observed_targets': named, 'verdict': outcome, 'reason': reason,
                'queue_context': queue_context, 'semantics_approved': False}
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
    declared_gates = {g['id']: {'status': g['status'], 'evidence': g.get('evidence', '')} for g in w.get('gates', [])}
    gate_map = dict(declared_gates)
    for gid in ALL_GATES:
        gate_map.setdefault(gid, {'status': 'not-run', 'evidence': ''})
    for gid in CONFORMANCE_GATES:
        machine = conformance_evidence_status(wpath, w, gid)
        declared = declared_gates.get(gid, {'status': 'not-run', 'evidence': ''})
        if machine['status'] == 'passed':
            gate_map[gid] = machine
        elif machine['status'] == 'inconclusive' and declared['status'] == 'passed' and declared.get('evidence'):
            gate_map[gid] = {'status': 'passed', 'evidence': declared['evidence'],
                             'deterministic_status': 'inconclusive',
                             'deterministic_evidence': machine['evidence'],
                             'reason': 'deterministic validator was inconclusive; explicit review evidence supplied'}
        else:
            gate_map[gid] = machine
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
    required_gates = list(EXTERNAL_GATES)
    if infer_flow(w) == 'spec-implementation':
        required_gates += list(CONFORMANCE_GATES)
    gates_ok = all(gate_map[g]['status'] in ('passed', 'not-applicable') for g in required_gates)
    git_ok = all(x['status'] == 'passed' for x in git)
    reported_complete = (w['mode'] == 'implementation' and spec['status'] == 'confirmed' and
                         checks_ok and gates_ok and git_ok and bool(w['checks']))
    overall = 'reported-complete/unverified-external-evidence' if reported_complete else 'not-complete'
    return {'work_id': w['id'], 'entry': w['entry'], 'mode': w['mode'],
            'specification': spec_gate, 'checks': evidence, 'gates': gate_map,
            'git': git, 'next_actions': next_actions,
            'external_evidence_verification': 'required',
            'independent_unverified_gates': [g for g in required_gates if gate_map[g]['status'] not in ('passed', 'not-applicable')],
            'overall': overall}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    init = sub.add_parser('init', help='create an unapproved Work scaffold')
    init.add_argument('--id', required=True)
    init.add_argument('-o', '--output', required=True)
    for key in ('validate', 'route', 'git', 'compile', 'obligations', 'conformance', 'guard', 'queue-state', 'run', 'status', 'handoff'):
        p = sub.add_parser(key)
        p.add_argument('--work', required=True)
        if key == 'route':
            p.add_argument('--stage', choices=STAGES, required=True)
        if key == 'compile':
            p.add_argument('--kind', choices=('model', 'vectors', 'queue', 'tests'), required=True)
            p.add_argument('--check', action='store_true')
        if key == 'obligations':
            p.add_argument('--check', action='store_true')
        if key == 'conformance':
            p.add_argument('--kind', choices=CONFORMANCE_GATES, required=True)
        if key == 'guard':
            p.add_argument('--stage', choices=STAGES, required=True)
            p.add_argument('--phase', choices=('start','finish'), required=True)
            p.add_argument('--conditional')
        if key == 'queue-state':
            p.add_argument('--evidence', required=True)
        if key == 'handoff':
            p.add_argument('--stage', choices=STAGES, required=True)
            p.add_argument('--conditional')
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
            elif args.cmd == 'obligations':
                result = obligations_work(p, w, args.check)
            elif args.cmd == 'conformance':
                result = record_conformance_evidence(p, w, args.kind, conformance_work(p, w, args.kind))
            elif args.cmd == 'guard':
                result = guard_work(p, w, args.stage, args.phase, args.conditional)
            elif args.cmd == 'queue-state':
                result = queue_state_work(p, w, args.evidence)
            elif args.cmd == 'run':
                result = command_work(p, w, args.id, args.execute)
            elif args.cmd == 'handoff':
                result = handoff_work(p, w, args.stage, args.conditional)
            else:
                result = status_work(p, w)
        print(json_bytes(result).decode(), end='')
        if args.cmd == 'validate' and result['status'] != 'passed':
            return 2
        if args.cmd in ('route', 'compile', 'obligations', 'conformance', 'guard', 'run') and result['status' if args.cmd != 'run' else 'verdict'] not in ('passed', 'ready', 'inconclusive'):
            return 2
        return 0
    except (Blocked, OSError, subprocess.TimeoutExpired) as exc:
        print(json_bytes({'status': 'blocked', 'error': str(exc)}).decode(), file=sys.stderr, end='')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
