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
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePath

from catlib.common import Blocked, json_bytes, read_json, require, sha
from catlib.work import ALL_GATES, CONFORMANCE_GATES, EXTERNAL_GATES, ID, STAGES, read_work_markdown, render_work_markdown, validate, work_file
import cat_queue
import cat_project_typecheck as project_typecheck
import cat_test_technology as test_technology
import cat_node_service_technology as node_service_technology
import cat_queue_evidence as queue_evidence
import cat_scope_order
import cat_implementation_obligations as obligation_runtime
import cat_verifier_contracts as verifier_runtime
import cat_model_conformance as source_model_runtime
import cat_process_composition as composition_runtime
import cat_effect_trace_correlation as effect_correlation_runtime
import cat_external_effect_receipts as effect_receipts_runtime

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
    on_result = dict(s.get('on_result', {}))
    if flow == 'spec-test-sync' and stage == 'vectors':
        on_result['passed'] = 'suite-plan'
    # Normative test regeneration is not executable from observations or Drafts.
    spec = w.get('specification') or {}
    normative_blocked = (flow == 'spec-test-sync' and
                         (spec.get('status') != 'confirmed' or not spec.get('decision_ref')))
    return {'stage': stage, 'flow': flow, 'executor': executor, 'guard_required': guard_required,
            'conditional': s.get('conditional', {}), 'permissions': s.get('permissions', {}),
            'evidence_policy': s.get('evidence_policy', {}),
            'on_result': on_result, 'skills': sorted(set(items)),
            'unknown_technologies': unknown, 'missing_skills': absent,
            'missing_agents': missing_agents, 'stage_in_flow': permitted,
            'status': 'blocked' if unknown or absent or missing_agents or not permitted or normative_blocked else 'ready',
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
    result['evidence_policy']={
        'execution_evidence_owner':'none',
        'agent_may_edit_execution_evidence':False,
        'external_facts':'provider-required',
        'interpretation':'review-reference-only',
    }
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


def compilation_paths(wpath, w, conf, plural, singular, check):
    refs=conf.get(plural) or ([conf[singular]] if conf.get(singular) else [])
    require(isinstance(refs,list) and all(isinstance(x,str) and x for x in refs),
            'compilation.'+plural+' must contain paths')
    result=[]
    for ref in refs:
        entry=dict(conf);entry[singular]=ref
        result.append(compilation_path(wpath,w,entry,singular,check))
    return result


def compilation_pi_paths(wpath,w,conf,check):
    paths=compilation_paths(wpath,w,conf,'pis','pi',check)
    require(paths,'at least one compilation PI required')
    return paths


def rule_cli_args(wpath,w,conf,check):
    args=[]
    for plural,singular,option in (('common_rules','common_rule','--common-rule'),
                                   ('domain_specs','domain_spec','--domain-spec')):
        for path in compilation_paths(wpath,w,conf,plural,singular,check):args.extend([option,path])
    return args


def compile_work(wpath, w, kind, check):
    conf = w.get('compilation')
    require(conf is not None, 'no machine-readable compilation declared')
    require(kind in ('model', 'vectors', 'queue', 'tests'), 'kind must be model, vectors, queue or tests')
    def loc(key):
        return compilation_path(wpath, w, conf, key, check)
    argv = [sys.executable, str(ROOT / 'scripts/cat_compile_v2.py'), kind]
    if kind == 'model':
        process = loc('process')
        pis = compilation_pi_paths(wpath, w, conf, check)
        tces = compilation_tce_paths(wpath, w, conf, check)
        argv += [process, pis[0], *tces]
        for pi in pis[1:]:argv+=['--pi-extra',pi]
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
        pis = compilation_pi_paths(wpath, w, conf, check)
        tces = compilation_tce_paths(wpath, w, conf, check)
        argv += ['--process', process, '--pi', pis[0]]
        for pi in pis[1:]:argv+=['--pi-extra',pi]
        for tce in tces:
            argv += ['--tce', tce]
    if conf.get('domain_rule'):
        argv += ['--domain-rule', loc('domain_rule')]
    argv += rule_cli_args(wpath,w,conf,check)
    if conf.get('allow_partial',True):argv.append('--allow-partial')
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
    def loc(key, exists=True):
        return compilation_path(wpath, w, conf, key, exists)
    tces = compilation_tce_paths(wpath, w, conf, True)
    output = loc('obligations', check)
    pis=compilation_pi_paths(wpath,w,conf,True)
    argv = [sys.executable, str(ROOT / 'scripts/cat_implementation_obligations.py'),
            loc('process'), pis[0], *tces]
    for pi in pis[1:]:argv+=['--pi-extra',pi]
    if conf.get('domain_rule'):
        argv += ['--domain-rule', loc('domain_rule')]
    argv += rule_cli_args(wpath,w,conf,True)
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
    # A declared Java implementation without a Java Inspector is not
    # evidence of a checked public interface or capability. JUnit supplies
    # generated-test execution, not a Java implementation Inspector.
    if 'Java' in technologies:
        results.append({'technology': 'Java', 'status': 'inconclusive',
                        'reason': 'no source-bound Java implementation inspector available'})
    if conf.get('technology_constraints'):
        binding_path = Path(compilation_path(wpath, w, conf, 'technology_constraints', True))
        binding = read_json(binding_path)
        repo_name = binding.get('repository')
        declared_repo = next((r for r in w['repositories'] if r['name'] == repo_name), None)
        require(declared_repo is not None, 'project typecheck binding repository not declared')
        # v1 deliberately covers a single production repository; it cannot
        # silently claim another repository's source files were checked.
        require(not any(r.get('production_paths') for r in w['repositories'] if r is not declared_repo),
                'project typecheck v1 requires all production scope in the bound repository')
        results.extend(project_typecheck.inspect(resolve_dir(wpath, w, '@repo:' + repo_name),
                        binding_path, declared_repo.get('production_paths', []), technologies))
    if 'TypeScript' in technologies:
        if not conf.get('conformance_binding'):
            if not conf.get('technology_constraints'):
                results.append({'technology': 'TypeScript', 'status': 'inconclusive',
                                'reason': 'Compilation Conformance binding missing'})
        else:
            binding_path = Path(compilation_path(wpath, w, conf, 'conformance_binding', True))
            binding = read_json(binding_path)
            require(binding.get('schema') == 'cat-typescript-conformance-binding/v1',
                    'wrong TypeScript conformance binding schema')
            repo_name = binding.get('repository')
            require(isinstance(repo_name, str) and repo_name, 'TypeScript conformance binding repository required')
            repo_root = resolve_dir(wpath, w, '@repo:' + repo_name)
            pis=compilation_pi_paths(wpath,w,conf,True)
            argv = [sys.executable,
                    str(ROOT / 'skills/tech-typescript/scripts/cat_typescript_conformance.py'),
                    '--repo', str(repo_root), '--binding', str(binding_path),
                    '--process', compilation_path(wpath, w, conf, 'process', True),
                    '--pi', pis[0]]
            for pi in pis[1:]:argv+=['--pi-extra',pi]
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
    if conf.get('runtime_constraints') and len(w['repositories'])==1:
        runtime_binding=Path(compilation_path(wpath,w,conf,'runtime_constraints',True)).resolve()
        results.extend(node_service_technology.inspect(wpath,w,resolve_dir(wpath,w,'@repo:'+w['repositories'][0]['name']),runtime_binding))
    # A passing Inspector for one technology does not cover other declared
    # technologies. In particular, JUnit runs tests but is not itself an
    # implementation Inspector; a successful TypeScript check cannot cover it.
    checked = {entry.get('technology') for entry in results}
    for technology in sorted(technologies - checked):
        results.append({'technology': technology, 'status': 'inconclusive',
                        'reason': 'no deterministic implementation inspector available for declared technology'})
    if not technologies:
        return {'status': 'passed', 'results': [],
                'reason': 'no technologies declared; no technology inspector obligations'}
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
        'technologies': w.get('technologies', []),
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
        keys.extend(['model','vectors','queue','obligations'])
        if conf.get('conformance_binding'):
            keys.append('conformance_binding')
        if conf.get('technology_constraints'):
            keys.append('technology_constraints')
        if conf.get('runtime_constraints'):
            keys.append('runtime_constraints')
        keys.extend(key for key in ('effect_trace','effect_packet','effect_driver')
                    if conf.get(key))
    # Runtime rule verification must be invalidated when its registered
    # runner/fixture/assertion identities change, even if the Work is unchanged.
    if kind in ('process-closure','implementation-conformance') and conf.get('verifier_registry'):
        keys.append('verifier_registry')
    if kind=='process-closure' and conf.get('composition_binding'):
        keys.append('composition_binding')
    result = {}
    for key in keys:
        if not conf.get(key):
            continue
        path = Path(compilation_path(wpath, w, conf, key, True))
        result[key] = {'path': str(path), 'sha256': sha(path.read_bytes())}
    for plural,singular in (('pis','pi'),('common_rules','common_rule'),('domain_specs','domain_spec')):
        for index, raw in enumerate(compilation_paths(wpath, w, conf, plural, singular, True), 1):
            path=Path(raw)
            result[singular+':'+str(index)]={'path':str(path),'sha256':sha(path.read_bytes())}
    for index, raw in enumerate(compilation_tce_paths(wpath, w, conf, True), 1):
        path = Path(raw)
        result['tce:' + str(index)] = {'path': str(path), 'sha256': sha(path.read_bytes())}
    if kind=='implementation-conformance' and conf.get('effect_packet'):
        packet_path=Path(compilation_path(wpath,w,conf,'effect_packet',True))
        packet=read_json(packet_path)
        observations=packet.get('observations')
        require(isinstance(observations,list),'Effect packet observations required')
        for index,receipt in enumerate(observations,1):
            require(isinstance(receipt,dict),'Effect receipt must be an object')
            if receipt.get('reported_status')=='not-observed':
                continue
            try:
                path=effect_receipts_runtime._local(packet_path.parent,
                                                    receipt.get('observation_file'))
            except (effect_receipts_runtime.ReceiptError,ValueError,OSError) as exc:
                raise Blocked('Effect observation input invalid: '+str(exc)) from exc
            result['effect_observation:'+str(index)]={'path':str(path),
                                                     'sha256':sha(path.read_bytes())}
    if kind=='implementation-conformance' and conf.get('queue'):
        queue_file=Path(compilation_path(wpath,w,conf,'queue',True))
        queue_data=read_json(queue_file)
        root=(wpath.parent/'.cat-flow'/'evidence').resolve()
        for item in queue_data.get('items',[]):
            if item.get('status')!='done':continue
            ref=item.get('evidence_ref')
            require(isinstance(ref,str) and bool(ref),
                    'done Queue missing Green evidence ref')
            evidence=Path(ref)
            require(evidence.is_file() and not evidence.is_symlink() and
                    evidence.resolve().is_relative_to(root),
                    'Queue Green evidence must remain in script-owned root')
            result['green:'+item['id']]={'path':str(evidence.resolve()),
                                         'sha256':sha(evidence.read_bytes())}
    if kind=='process-closure':
        for key in ('verifier_registry','composition_binding'):
            if conf.get(key):
                path=Path(compilation_path(wpath,w,conf,key,True))
                result[key]={'path':str(path),'sha256':sha(path.read_bytes())}
        if conf.get('composition_binding'):
            try:
                _,assemblies=composition_runtime.composition_source_inputs(result['composition_binding']['path'])
            except (composition_runtime.CompositionError,ValueError,OSError,KeyError,TypeError) as exc:
                raise Blocked('composition Source input invalid: '+str(exc)) from exc
            for process,entries in assemblies.items():
                for key,entry in entries.items():
                    result['composition_source:'+process+':'+key]=entry
        for i,rel in enumerate(conf.get('composition_models',[]),1):
            entry={**conf,'model':rel}
            path=Path(compilation_path(wpath,w,entry,'model',True))
            result['composition_model:'+str(i)]={'path':str(path),'sha256':sha(path.read_bytes())}
    if kind in ('process-closure','implementation-conformance') and conf.get('verifier_registry'):
        registry_path=Path(compilation_path(wpath,w,conf,'verifier_registry',True))
        registry=read_json(registry_path)
        for i,entry in enumerate(registry.get('entries',[]),1):
            for label in ('fixture','runner'):
                if not entry.get(label):continue
                try:dep=verifier_runtime.resolve(registry_path.parent,entry[label]['path'])
                except (verifier_runtime.VerifierError,KeyError,OSError) as exc:
                    raise Blocked('invalid verifier dependency: '+str(exc)) from exc
                result['verifier:'+str(i)+':'+label]={'path':str(dep),
                                                       'sha256':sha(dep.read_bytes())}
    return result


def _implementation_repository_fingerprint(wpath, w):
    """Pin an implementation Gate to both working-tree bytes and Git HEAD.

    Different commits can have the same tracked/untracked file contents. A
    Work receipt against one commit must not be reused after a ref moves to
    another commit, even when that checkout's file tree is unchanged. Write
    guards continue to compare file paths only (via _repo_state).
    """
    state = _repo_state(wpath, w)
    heads = {}
    for repository in w.get('repositories', []):
        root = resolve_dir(wpath, w, '@repo:' + repository['name'])
        heads[repository['name']] = (git_cmd(root, 'rev-parse', 'HEAD')
                                     if (root / '.git').exists() else 'not-available')
    return sha(json_bytes({'files': state, 'heads': heads}))


def conformance_runtime_fingerprint():
    """Content identity of the installed CAT Gate code and routing policy.

    A Source/Work/implementation HEAD may be unchanged while a new compiler,
    verifier, inspector, or Gate implementation would reach another result.
    Pin the complete shipped Python runtime (including Technology Skills) and
    routing config; the conservative inventory may invalidate evidence after
    unrelated runtime changes, but cannot silently retain an old Gate result.
    This is *not* an authenticity attestation or proof of Provider execution.
    """
    scripts = ROOT / 'scripts'
    routing = ROOT / 'config' / 'routing.json'
    require((scripts / 'cat_flow.py').is_file() and routing.is_file(),
            'CAT Gate runtime scripts/routing missing')
    files = [*scripts.rglob('*.py'), *((ROOT / 'skills').rglob('*.py')), routing]
    inventory = []
    for path in sorted(files, key=lambda x: x.relative_to(ROOT).as_posix()):
        require(path.is_file() and not path.is_symlink(),
                'CAT Gate runtime file must be regular: ' + str(path))
        inventory.append({'path': path.relative_to(ROOT).as_posix(),
                          'sha256': sha(path.read_bytes())})
    return sha(json_bytes({'schema': 'cat-gate-runtime-inventory/v1',
                           'files': inventory}))


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
        'runtime_sha256': conformance_runtime_fingerprint(),
        'verdict': result['status'],
        'reason': result.get('reason', ''),
        'supporting_evidence': supporting,
        'verifier_evidence':result.get('verifier_evidence'),
        'source_model_evidence':result.get('source_model_evidence'),
        'composition_evidence':result.get('composition_evidence'),
        'effect_correlation_evidence':result.get('effect_correlation_evidence'),
    }
    if kind == 'implementation-conformance':
        payload['repo_state_sha256'] = _implementation_repository_fingerprint(wpath, w)
        payload['technology_results'] = result.get('technology_results', [])
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
        if e.get('runtime_sha256') != conformance_runtime_fingerprint():
            return {'status': 'stale', 'evidence': str(path), 'reason': 'CAT Gate runtime code/routing changed'}
        # A recorded subset is not sufficient: deleting the TCE, verifier
        # runner or fixture entries must not preserve an old 'passed' verdict.
        # Reconstruct the entire dependency set from the current Work and
        # require both its members and every byte digest to match exactly.
        stored_inputs=e.get('input_sha256')
        if not isinstance(stored_inputs,dict):
            return {'status': 'stale', 'evidence': str(path),
                    'reason': 'conformance input inventory missing'}
        # Legacy reviewer-only Work receipts can be materialized without a
        # Compilation section; they have no discoverable file dependencies.
        # Once a Compilation is declared, require the *complete* live set.
        current_inputs=(conformance_input_hashes(wpath,w,kind)
                        if w.get('compilation') else {})
        if stored_inputs != current_inputs:
            return {'status': 'stale', 'evidence': str(path),
                    'reason': 'conformance input inventory changed'}
        if kind == 'implementation-conformance':
            if e.get('repo_state_sha256') != _implementation_repository_fingerprint(wpath, w):
                return {'status': 'stale', 'evidence': str(path), 'reason': 'implementation repository state changed'}
        return {'status': e.get('verdict', 'inconclusive'), 'evidence': str(path), 'reason': e.get('reason', '')}
    except (OSError, KeyError, Blocked):
        return {'status': 'stale', 'evidence': str(path), 'reason': 'conformance evidence cannot be revalidated'}



def implementation_effect_preflight(wpath,w,conf):
    """Source-bound packet/trace preflight; never grants a CAT Gate pass."""
    files=('effect_trace','effect_packet','effect_driver')
    selected=[key for key in files if conf.get(key)]
    require(not selected or len(selected)==3,
            'Effect evidence requires trace, packet and driver together')
    if not selected:
        return None
    def loc(key):return Path(compilation_path(wpath,w,conf,key,True))
    model=loc('model')
    trace=loc('effect_trace')
    packet=loc('effect_packet')
    driver=loc('effect_driver')
    repo=None
    driver_repo_path=None
    if conf.get('effect_repo') or conf.get('effect_repo_path'):
        require(conf.get('effect_repo') and conf.get('effect_repo_path'),
                'Effect checkout verification requires repository and relative path')
        repo=resolve_dir(wpath,w,'@repo:'+conf['effect_repo'])
        driver_repo_path=conf['effect_repo_path']
    try:
        result=effect_correlation_runtime.correlate(
            model.read_bytes(), read_json(trace), read_json(packet), driver.read_bytes(),
            packet.parent,repo,driver_repo_path)
    except (effect_correlation_runtime.CorrelationError,ValueError,OSError,KeyError,
            TypeError,IndexError,subprocess.TimeoutExpired) as exc:
        raise Blocked('Effect/trace evidence invalid: '+str(exc)) from exc
    runtime=wpath.parent/'.cat-flow'/'cache'
    runtime.mkdir(parents=True,exist_ok=True)
    path=runtime/'implementation-effect-correlation.json'
    path.write_bytes(json_bytes(result))
    return {'path':str(path),'status':result['status'],
            'normative_status':result['normative_status'],
            'provider_authentication_status':result['provider_authentication_status']}


def conformance_work(wpath, w, kind):
    require(kind in CONFORMANCE_GATES, 'unknown conformance gate')
    conf = w.get('compilation')
    require(conf is not None, 'conformance requires Compilation inputs')
    if kind == 'process-closure':
        if len(w['scope']['process_ids']) != 1:
            if not conf.get('composition_models'):
                return {'gate':kind,'status':'inconclusive',
                        'reason':'cross-Process closure requires explicit model collection and typed bindings'}
            try:
                paths=[]
                for rel in conf['composition_models']:
                    entry={**conf,'model':rel}
                    paths.append(compilation_path(wpath,w,entry,'model',True))
                binding=compilation_path(wpath,w,conf,'composition_binding',True) if conf.get('composition_binding') else None
                composed=composition_runtime.compose(paths,binding)
            except (composition_runtime.CompositionError,Blocked,ValueError,OSError,KeyError,TypeError) as exc:
                return {'gate':kind,'status':'blocked','reason':str(exc)}
            path=wpath.parent/'.cat-flow'/'cache'/'process-composition.json'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(json_bytes(composed))
            return {'gate':kind,'status':'inconclusive' if composed['status']=='passed' else composed['status'],
                    'composition_evidence':str(path),
                    'reason':'typed composition evidence recorded; independent local Model Conformance and interleaving/effect proofs remain required'}
        runtime = wpath.parent / '.cat-flow' / 'cache'
        runtime.mkdir(parents=True, exist_ok=True)
        def loc(key): return compilation_path(wpath, w, conf, key, False)
        try:
            tces = compilation_tce_paths(wpath, w, conf, True)
            pis=compilation_pi_paths(wpath,w,conf,True)
            rules=rule_cli_args(wpath,w,conf,True)
        except Blocked as exc:
            return {'gate':kind,'status':'blocked','reason':str(exc)}
        argv=[sys.executable,str(ROOT/'scripts/cat_compile_v2.py'),'model',loc('process'),pis[0],*tces]
        for pi in pis[1:]:argv+=['--pi-extra',pi]
        argv+=rules
        argv+=['--allow-partial']
        if conf.get('domain_rule'): argv += ['--domain-rule',loc('domain_rule')]
        argv += ['-o',str(runtime/'process-closure.model.json')]
        p=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True,timeout=60,check=False)
        if p.returncode == 0:
            model_path = runtime/'process-closure.model.json'
            model = read_json(model_path)
            # A Compiler's own success is not an independent proof that the
            # TestModel preserves its normative Source. A formally passed
            # Closure must also survive a separately derived Source→Model
            # comparison. The independent validator cannot discharge any
            # still-unverified free-text Rule or real Provider effect.
            try:
                source_check = source_model_runtime.validate(
                    loc('process'), pis, tces, model_path,
                    loc('domain_rule') if conf.get('domain_rule') else None,
                    common_rules=compilation_paths(wpath,w,conf,'common_rules','common_rule',True),
                    domain_specs=compilation_paths(wpath,w,conf,'domain_specs','domain_spec',True))
            except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
                return {'gate':kind,'status':'blocked',
                        'reason':'independent Source-to-Model comparison failed: '+str(exc)}
            source_receipt = runtime/'process-closure-source-model.json'
            source_receipt.write_bytes(json_bytes(source_check))
            if source_check.get('status') != 'passed':
                return {'gate':kind,'status':'blocked',
                        'source_model_evidence':str(source_receipt),
                        'reason':'independent Source-to-Model comparison rejected the generated Model: '
                                 +', '.join(source_check.get('mismatches', []))[:900]}
            rule_status='passed'
            verifier_evidence=None
            # An explicitly submitted registry is evidence to validate even
            # when every Rule already has an intrinsic model proof. Otherwise
            # malformed or failed submitted evidence is silently bypassed.
            # Its non-normative fixture status cannot *replace* a valid source-
            # bound intrinsic proof or upgrade an unverified free-text Rule.
            if model.get('unverified_rule_ids') and not conf.get('verifier_registry'):
                rule_status='inconclusive'
            if conf.get('verifier_registry'):
                try:
                    registry_path=compilation_path(wpath,w,conf,'verifier_registry',True)
                    verified=verifier_runtime.evaluate(runtime/'process-closure.model.json',registry_path)
                    verifier_path=runtime/'process-closure-verifiers.json'
                    verifier_path.write_bytes(json_bytes(verified))
                    verifier_evidence=str(verifier_path)
                    if verified.get('status')=='failed':
                        # Failed submitted assertions invalidate the evidence,
                        # not the underlying normative Rule itself.
                        rule_status='failed'
                    elif model.get('unverified_rule_ids'):
                        rule_status=verified.get('normative_status','inconclusive')
                except (verifier_runtime.VerifierError,ValueError,OSError,KeyError) as exc:
                    return {'gate':kind,'status':'blocked','reason':'rule verifier registry invalid: '+str(exc)}
            if rule_status=='failed':
                return {'gate':kind,'status':'blocked','verifier_evidence':verifier_evidence,
                        'reason':'one or more registered verifier fixture assertions failed; normative meaning remains unproved'}
            if model.get('status')!='confirmed' or rule_status!='passed' or model.get('unresolved_domains') or model.get('presence_unproven') or model.get('unresolved_interfaces'):
                return {'gate':kind,'status':'inconclusive','evidence':str(runtime/'process-closure.model.json'),
                        'verifier_evidence':verifier_evidence,
                        'reason':'model has partial, unverified, unresolved or non-confirmed normative inputs'}
            if model.get('coverage_requirement') != 'closed':
                return {'gate':kind,'status':'inconclusive','evidence':str(runtime/'process-closure.model.json'),
                        'reason':'local TCE coverage is partial; assembled Process closure requires additional deterministic or review evidence'}
            if not all(x.get('result') == 'proved' for x in model.get('coverage_checks', {}).values()):
                return {'gate':kind,'status':'inconclusive','evidence':str(runtime/'process-closure.model.json'),
                        'reason':'closed-world declaration exists but closure proof is incomplete'}
            return {'gate':kind,'status':'passed','evidence':str(runtime/'process-closure.model.json'),
                    'verifier_evidence':verifier_evidence,
                    'source_model_evidence':str(source_receipt),
                    'reason':'independent Source-to-Model conformance and finite closed-world coverage passed; all applicable normative Rules have source-bound intrinsic proofs'}
        msg=(p.stderr or p.stdout).strip()
        inconclusive_markers=('currently supports','unproven','non-finite','requires a technology','unsupported')
        status='inconclusive' if any(x in msg for x in inconclusive_markers) else 'blocked'
        return {'gate':kind,'status':status,'reason':msg[-1800:]}
    if kind == 'model-conformance':
        require(conf.get('model'), 'model-conformance requires Compilation Model')
        def loc(key): return compilation_path(wpath, w, conf, key, True)
        pis=compilation_pi_paths(wpath,w,conf,True)
        argv=[sys.executable,str(ROOT/'scripts/cat_model_conformance.py'),loc('process'),pis[0],loc('model')]
        for pi in pis[1:]:argv+=['--pi-extra',pi]
        argv+=rule_cli_args(wpath,w,conf,True)
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
    effect_correlation=None
    if any(conf.get(key) for key in ('effect_trace','effect_packet','effect_driver')):
        try:
            effect_correlation=implementation_effect_preflight(wpath,w,conf)
        except Blocked as exc:
            return {'gate':kind,'status':'blocked','reason':str(exc)}
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
    verified_green={}
    if conf.get('queue'):
        qpath=Path(compilation_path(wpath,w,conf,'queue',True))
        queue=read_json(qpath)
        if any(x.get('status')=='done' for x in queue.get('items',[])):
            if not (conf.get('model') and conf.get('vectors')):
                return {'gate':kind,'status':'inconclusive',
                        'reason':'completed Queue needs exact model/vectors and Green receipts'}
            try:
                verified_green=queue_evidence.verify(
                    w['id'],qpath,
                    compilation_path(wpath,w,conf,'model',True),
                    compilation_path(wpath,w,conf,'vectors',True),
                    wpath.parent/'.cat-flow'/'evidence')
            except (Blocked,ValueError,KeyError,OSError,TypeError) as exc:
                return {'gate':kind,'status':'blocked',
                        'reason':'Queue Green evidence invalid: '+str(exc)}
    if queue and any(x in w.get('technologies',[]) for x in ('Vitest','Playwright')) and conf.get('binding') and conf.get('tests_output') and len(w['repositories'])==1:
        evidence=test_technology.inspect(wpath,w,resolve_dir(wpath,w,'@repo:'+w['repositories'][0]['name']),
            read_json(compilation_path(wpath,w,conf,'model',True)),read_json(compilation_path(wpath,w,conf,'vectors',True)),queue,
            Path(compilation_path(wpath,w,conf,'binding',True)).resolve(),Path(compilation_path(wpath,w,conf,'tests_output',True)).resolve())
        for result in evidence:
            tech['results']=[x for x in tech['results'] if x['technology']!=result['technology']]+[result]
        tech['status']='passed' if all(x['status']=='passed' for x in tech['results']) else 'inconclusive'
    model_gate=conformance_evidence_status(wpath,w,'model-conformance')
    rule_verification=None
    if any(x.get('method')=='normative-rule-verifier' for x in skeleton['items']):
        if conf.get('verifier_registry') and conf.get('model'):
            try:
                model_path=compilation_path(wpath,w,conf,'model',True)
                registry_path=compilation_path(wpath,w,conf,'verifier_registry',True)
                rule_verification=verifier_runtime.evaluate(model_path,registry_path)
            except (verifier_runtime.VerifierError,Blocked,ValueError,OSError,KeyError,TypeError) as exc:
                return {'gate':kind,'status':'blocked','reason':'invalid normative rule verifier: '+str(exc)}
    data=obligation_runtime.aggregate(skeleton,queue,tech['results'],model_gate,rule_verification,verified_green)
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
    if effect_correlation is not None:
        base['effect_correlation_evidence']=effect_correlation['path']
    if any(x['status']=='failed' for x in items):
        return {'gate':kind,'status':'blocked','reason':'one or more implementation obligations failed',**base}
    if missing or any(x['status'] in ('inconclusive','not-run') for x in items):
        return {'gate':kind,'status':'inconclusive','reason':'obligations are incomplete or not machine-decidable',**base}
    if tech['status'] != 'passed':
        return {'gate':kind,'status':'inconclusive','reason':tech['reason'],**base}
    predecessor=conformance_evidence_status(wpath,w,'process-closure')
    if predecessor.get('status')!='passed' or model_gate.get('status')!='passed':
        return {'gate':kind,'status':'inconclusive',
                'reason':'fresh passed process-closure and model-conformance evidence required',**base}
    if effect_correlation is not None:
        # A self-submitted trace/receipt has not proved that an Effect happened,
        # or that the declared Rule's free-text meaning equals the verifier.
        # Even checked-out driver bytes do not attest runner execution.
        return {'gate':kind,'status':'inconclusive',
                'reason':'Effect/trace receipt identities are consistent but provider authenticity and normative meaning are unproved',**base}
    return {'gate':kind,'status':'passed',
            'reason':'all CAT implementation obligations, predecessor Gates and technology inspectors passed',**base}


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


def _guard_relative_name(path):
    """Portable relative paths; retain literal backslashes on POSIX."""
    require(isinstance(path, PurePath), 'guard path must be a pathlib value')
    return path.as_posix()


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
        state[_guard_relative_name(rel)] = sha(path.read_bytes())
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
            patterns.append(_guard_relative_name(ev.relative_to(root)) + '/**')
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


def _require_conditional_inconclusive(wpath,w,stage,conditional):
    if conditional is None:
        return
    require(conditional=='inconclusive','conditional Agent invocation is limited to inconclusive results')
    if stage in CONFORMANCE_GATES:
        state=conformance_evidence_status(wpath,w,stage)
        require(state.get('status')=='inconclusive',
                f'{stage} conditional reviewer requires current deterministic inconclusive evidence')
        return
    if stage=='red':
        current_manifest=sha(wpath.read_bytes())
        found=False
        for check in w.get('checks',[]):
            if check.get('stage')!='red':
                continue
            path=wpath.parent/'.cat-flow'/'evidence'/(check['id']+'.json')
            if not path.is_file():
                continue
            evidence=read_json(path)
            if (evidence.get('work_id')==w['id'] and evidence.get('check_id')==check['id']
                    and evidence.get('manifest_sha256')==current_manifest
                    and evidence.get('verdict')=='inconclusive'):
                found=True;break
        require(found,'red conditional reviewer requires current inconclusive Red evidence')
        return
    if stage=='git':
        require(any(x.get('status')=='inconclusive' for x in git_snapshot(wpath,w)),
                'git conditional reviewer requires inconclusive Git inspection')
        return
    # Non-normative legacy test-review remains an explicitly selected review path;
    # primary CAT-TDD flows do not include it.
    require(stage=='test-review','conditional reviewer lacks an inconclusive evidence contract for this stage')


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
    if phase=='start':
        _require_conditional_inconclusive(wpath,w,stage,conditional)
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
    # A re-check must not erase the previous finish decision or replace the
    # original baseline. Manual correction may change the current verdict,
    # but a claimed approval never exempts a changed path from the guard.
    previous_verdict=base.get('verdict')
    require(previous_verdict in ('pending','passed','blocked'), 'invalid guard verdict')
    if previous_verdict != 'pending':
        history=base.setdefault('finish_history',[])
        require(isinstance(history,list), 'invalid guard finish history')
        history.append({'verdict':previous_verdict,
                        'violations':base.get('violations',[]),
                        'finished_manifest_sha256':base.get('finished_manifest_sha256')})
    base['verdict']=verdict;base['violations']=violations;base['finished_manifest_sha256']=sha(wpath.read_bytes())
    path.write_bytes(json_bytes(base))
    return {'status':verdict,'stage':stage,'conditional':conditional,'violations':violations,
            'workspace_allowed':allowed_ws,'guard':str(path)}


def queue_state_work(wpath,w,evidence_path):
    conf=w.get('compilation') or {}
    require(conf.get('queue'),'queue-state requires Compilation Queue')
    qpath=Path(compilation_path(wpath,w,conf,'queue',True))
    allowed=(wpath.parent/'.cat-flow'/'evidence').resolve()
    result=cat_queue.done_from_green(
        qpath,Path(evidence_path).resolve(),
        expected_work_id=w['id'],allowed_evidence_root=allowed)
    result.update(queue=str(qpath),
                  next_stage='tests' if result['outcome']=='next-item' else 'implementation-conformance')
    return result


def handoff_work(wpath,w,stage,conditional=None):
    _require_conditional_inconclusive(wpath,w,stage,conditional)
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
        if '.cat-flow' in Path(rel).parts:
            continue  # executor-owned evidence must not invalidate itself
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
    if check['stage'] in ('red', 'green'):
        require(w['specification']['status'] == 'confirmed',
                'no TDD gate without declared confirmed specification')
    if check['stage'] in ('refactor-baseline', 'regression'):
        require(infer_flow(w) == 'refactor',
                'independent refactor checks require the refactor flow')
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
    runner_identity=test_technology.identity(cwd,argv,w.get('technologies',[]))
    env=os.environ.copy()
    if runner_identity and 'playwright' in runner_identity:
        env['DEBUG']='pw:browser'
    runner_observation=None
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    outcome = 'inconclusive'
    reason = ''
    try:
        p = subprocess.run(argv, cwd=cwd, text=True, errors='replace', capture_output=True,
                           timeout=check.get('timeout_seconds', 120), check=False, env=env)
        runner_observation=test_technology.observation(runner_identity,test_technology.identity(cwd,argv,w.get('technologies',[])),p.stdout,p.stderr,report)
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
                'queue_context': queue_context, 'semantics_approved': False,
                'test_technology':runner_observation}
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
    review_claims = {}
    for gid in ALL_GATES:
        gate_map.setdefault(gid, {'status': 'not-run', 'evidence': ''})
    for gid in CONFORMANCE_GATES:
        machine = conformance_evidence_status(wpath, w, gid)
        declared = declared_gates.get(gid, {'status': 'not-run', 'evidence': ''})
        # Work.gates is a claim, not authority to revise the script-owned
        # Conformance verdict. In particular, a review:* string is neither
        # resolved evidence nor a source-bound normative decision.
        gate_map[gid] = machine
        if declared['status'] == 'passed' and declared.get('evidence'):
            review_claims[gid] = {
                'status': 'unverified-claim',
                'reference': declared['evidence'],
                'declared_status': declared['status'],
                'machine_status': machine['status'],
                'reason': 'Work-declared evidence is not a verified machine Gate result',
            }
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
            'review_claims': review_claims,
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
