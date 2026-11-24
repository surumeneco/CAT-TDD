#!/usr/bin/env python3
"""Check adopted TypeScript/Vue compiler constraints, not PI or capability semantics.

No project-selected executable commands or success receipts are accepted. Run the
installed compiler against the named project configuration, and independently
require every scoped source to appear in the compiler's actual file inventory.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from catlib.common import Blocked, require

SCHEMA = 'cat-project-typecheck/v1'
TS_SUFFIXES = {'.ts', '.tsx', '.mts', '.cts'}
COMPILERS = {'tsc': ('typescript', 'bin/tsc'),
             'vue-tsc': ('vue-tsc', 'bin/vue-tsc.js')}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_file(repo, raw):
    require(isinstance(raw, str) and raw, 'typecheck path must be a nonempty string')
    path = Path(raw)
    require(not path.is_absolute() and '..' not in path.parts, 'typecheck path escapes repository')
    resolved = (repo / path).resolve()
    require(resolved.is_relative_to(repo) and resolved.is_file(), 'typecheck file missing or outside repository: '+raw)
    return resolved


def load_binding(repo, path):
    doc = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(doc, dict) and doc.get('schema') == SCHEMA, 'invalid project typecheck binding schema')
    require(set(doc) == {'schema', 'repository', 'projects'}, 'unexpected project typecheck binding fields')
    require(isinstance(doc['repository'], str) and doc['repository'], 'typecheck repository required')
    entries = doc['projects']
    require(isinstance(entries, list) and entries, 'typecheck projects required')
    configs = []
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {'config', 'compiler'}, 'invalid project typecheck entry')
        require(entry['compiler'] in COMPILERS, 'unsupported typecheck compiler')
        config = relative_file(repo, entry['config'])
        require(config.suffix == '.json', 'typecheck project config must be JSON/JSONC')
        configs.append((config, entry['compiler']))
    require(len({c for c, _ in configs}) == len(configs), 'duplicate typecheck config')
    return doc, configs


def production_sources(repo, production_paths):
    """Derive scope from Work, not a conveniently smaller binding file list."""
    found = set()
    for raw in production_paths:
        require(isinstance(raw, str) and raw, 'invalid production path')
        path = Path(raw)
        require(not path.is_absolute() and '..' not in path.parts, 'production path escapes repository')
        # Vue/Nuxt routes contain literal brackets; check exact paths first.
        exact = repo / path
        matches = [exact] if exact.is_file() else list(repo.glob(raw))
        files = [p for p in matches if p.is_file()]
        if path.suffix in TS_SUFFIXES | {'.vue'} and not files:
            raise Blocked('scoped production source missing: '+raw)
        for p in files:
            if p.suffix in TS_SUFFIXES | {'.vue'}:
                p = p.resolve()
                require(p.is_relative_to(repo), 'production source outside repository')
                found.add(p)
    return found


def compiler_command(repo, name, lock):
    package, bin_path = COMPILERS[name]
    module = 'node_modules/'+package
    meta = relative_file(repo, module+'/package.json')
    info = json.loads(meta.read_text(encoding='utf-8'))
    version = lock.get('packages', {}).get(module, {}).get('version')
    require(info.get('name') == package and isinstance(version, str) and info.get('version') == version,
            'installed compiler does not match npm lockfile: '+package)
    if name == 'vue-tsc':
        for dependency in ('typescript', 'vue'):
            dep = 'node_modules/'+dependency
            package_info = json.loads(relative_file(repo, dep+'/package.json').read_text(encoding='utf-8'))
            expected = lock.get('packages', {}).get(dep, {}).get('version')
            require(package_info.get('name') == dependency and isinstance(expected, str)
                    and package_info.get('version') == expected, 'installed dependency does not match lockfile: '+dependency)
    executable = relative_file(repo, module+'/'+bin_path)
    return ['node', str(executable)], {'package': package, 'version': version,
            'entrypoint': executable.relative_to(repo).as_posix(), 'entrypoint_sha256': digest(executable),
            'package_json_sha256': digest(meta)}


def run_project(repo, config, name, required, lock):
    cmd, compiler = compiler_command(repo, name, lock)
    # Fail closed on explicit per-file opt-outs; a listed file is not
    # necessarily type checked if the source has opted out of diagnostics.
    for path in required:
        text = path.read_text(encoding="utf-8-sig")
        require("@ts-nocheck" not in text and "@vue-skip" not in text,
                "scoped source contains typecheck opt-out: " + path.relative_to(repo).as_posix())
    config_hash = digest(config)
    source_hashes = {p.relative_to(repo).as_posix(): digest(p) for p in sorted(required)}
    base = cmd+['--project', str(config), '--noEmit', '--pretty', 'false']
    show = subprocess.run(base+['--showConfig'], cwd=repo, capture_output=True, text=True, encoding='utf-8', timeout=90, check=False)
    require(show.returncode == 0, 'cannot resolve compiler project configuration: '+(show.stdout+show.stderr)[-1000:])
    effective = json.loads(show.stdout)
    options = effective.get('compilerOptions', {})
    require(options.get('noCheck') is not True and options.get('noEmit') is True,
            'compiler project disables type checking or noEmit')
    # Match the existing strict project contract; explicit opt-outs are not a strict check.
    require(options.get('strict') is True and all(options.get(k) is not False for k in (
        'noImplicitAny', 'strictNullChecks', 'strictFunctionTypes', 'strictBindCallApply',
        'strictPropertyInitialization', 'noImplicitThis', 'useUnknownInCatchVariables', 'alwaysStrict')),
        'compiler project does not enable strict TypeScript checking')
    if name == 'vue-tsc':
        require(effective.get('vueCompilerOptions', {}).get('skipTemplateCodegen') is not True,
                'Vue template type checking is disabled')
    run = subprocess.run(base+['--listFiles'], cwd=repo, capture_output=True, text=True, encoding='utf-8', timeout=180, check=False)
    result = {'config': config.relative_to(repo).as_posix(), 'config_sha256': config_hash,
              'compiler': compiler, 'command': base+['--listFiles'], 'exit_code': run.returncode,
              'effective_config_sha256': hashlib.sha256(show.stdout.encode()).hexdigest(),
              'stdout_sha256': hashlib.sha256(run.stdout.encode()).hexdigest(),
              'stderr_sha256': hashlib.sha256(run.stderr.encode()).hexdigest(),
              'source_sha256': source_hashes}
    if run.returncode != 0:
        result.update(status='blocked', reason='compiler rejected project', diagnostics=(run.stdout+run.stderr)[:2000])
        return result, set()
    # Do not use the config's claimed `include` patterns as proof of inclusion.
    # Only exact real filenames printed by the successful compiler are admitted.
    observed = set()
    for line in run.stdout.splitlines():
        candidate = Path(line.strip())
        if candidate.is_absolute() and candidate.is_file():
            observed.add(candidate.resolve())
    missing = required-observed
    require(config_hash == digest(config) and source_hashes == {p.relative_to(repo).as_posix(): digest(p) for p in sorted(required)},
            'typecheck inputs changed during compiler execution')
    result['observed_sources'] = sorted(p.relative_to(repo).as_posix() for p in required & observed)
    if missing:
        result.update(status='inconclusive', reason='compiler inventory omitted scoped sources',
                      missing_sources=sorted(p.relative_to(repo).as_posix() for p in missing))
    else:
        result['status'] = 'passed'
    return result, required & observed


def inspect(repo, binding_path, production_paths, technologies):
    repo = Path(repo).resolve()
    declared = set(technologies) & {'TypeScript', 'Vue'}
    if not declared:
        return []
    reports = []
    by_tech = {t: set() for t in declared}
    try:
        _, configs = load_binding(repo, Path(binding_path))
        lock_path = relative_file(repo, 'package-lock.json')
        lock = json.loads(lock_path.read_text(encoding='utf-8'))
        scope = production_sources(repo, production_paths)
        required = {'TypeScript': scope, 'Vue': {p for p in scope if p.suffix == '.vue'}}
        for config, name in configs:
            selected = {p for p in scope if p.is_relative_to(config.parent)
                        and (p.suffix != '.vue' or name == 'vue-tsc')}
            if not selected:
                continue
            report, observed = run_project(repo, config, name, selected, lock)
            reports.append(report)
            if report['status'] != 'blocked':
                if 'TypeScript' in declared:
                    by_tech['TypeScript'].update(observed)
                if 'Vue' in declared and name == 'vue-tsc':
                    by_tech['Vue'].update(p for p in observed if p.suffix == '.vue')
        results = []
        for tech in sorted(declared):
            missing = required[tech]-by_tech[tech]
            bad = any(x['status']=='blocked' for x in reports)
            ok = bool(required[tech]) and not missing and not bad
            results.append({'technology': tech, 'status': 'blocked' if bad else ('passed' if ok else 'inconclusive'),
                            'constraint_contract': SCHEMA, 'package_lock_sha256': digest(lock_path),
                            'reason': 'adopted strict compiler and scoped source coverage verified' if ok else
                                      'compiler rejected project' if bad else 'scoped sources not fully checked',
                            'missing_sources': sorted(p.relative_to(repo).as_posix() for p in missing),
                            'project_checks': reports,
                            'covered_obligation_ids': ['implementation-constraint.'+tech.lower()] if ok else [],
                            'limitation': 'compiler diagnostics and scoped input coverage only; not PI, capability, runtime behavior or arbitrary style constraints'})
        return results
    except (Blocked, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        return [{'technology': t, 'status': 'inconclusive', 'constraint_contract': SCHEMA,
                 'reason': str(exc), 'project_checks': reports, 'covered_obligation_ids': []} for t in sorted(declared)]
