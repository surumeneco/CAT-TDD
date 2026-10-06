#!/usr/bin/env python3
"""Deterministic TypeScript implementation-boundary inspector for CAT.

The inspector does not infer specification. A project binding declares which
public TypeScript symbols implement PI operations and which known external
capability classes implement declared observation/action semantic IDs. Known
capability use or public exports outside that binding are violations.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE / 'scripts'))
from cat_compile_v2 import Blocked, read_artifact


KNOWN_CAPABILITIES = {
    'environment': (
        re.compile(r'\bprocess\.env\b'),
        re.compile(r'\bDeno\.env\b'),
    ),
    'network': (
        re.compile(r'\bfetch\s*\('),
        re.compile(r'\baxios\b'),
        re.compile(r'''(?:from\s+|require\s*\(\s*)['"](?:node:)?https?['"]'''),
        re.compile(r'\bhttps?\.(?:request|get)\s*\('),
    ),
    'filesystem': (
        re.compile(r'''(?:from\s+|require\s*\(\s*)['"](?:node:)?fs(?:/promises)?['"]'''),
        re.compile(r'\b(?:readFile|writeFile|appendFile|readdir|mkdir|unlink)\s*\('),
    ),
    'clock': (
        re.compile(r'\bDate\.now\s*\('),
        re.compile(r'\bnew\s+Date\s*\('),
    ),
    'random': (
        re.compile(r'\bMath\.random\s*\('),
        re.compile(r'\bcrypto\.(?:randomUUID|randomBytes|getRandomValues)\s*\('),
    ),
    'timer': (
        re.compile(r'\bset(?:Timeout|Interval)\s*\('),
    ),
}

EXPORT_DECL = re.compile(
    r'(?m)^\s*export\s+(?:default\s+)?(?:async\s+)?'
    r'(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)'
)
EXPORT_LIST = re.compile(r'(?m)^\s*export\s*\{([^}]+)\}')
EXPORT_STAR = re.compile(r'(?m)^\s*export\s*\*')


def require(test, message):
    if not test:
        raise Blocked(message)


def safe_rel(value, where):
    p = Path(value)
    require(not p.is_absolute() and '..' not in p.parts, where + ' must stay under repository')
    return value


def files_for(repo: Path, globs):
    result = set()
    for pattern in globs:
        safe_rel(pattern, 'source_glob')
        for path in repo.glob(pattern):
            if path.is_file() and not any(x in path.parts for x in ('node_modules', 'dist', 'build', '.git')):
                result.add(path.resolve())
    return sorted(result)


def exports_from(path: Path):
    text = path.read_text(encoding='utf-8-sig')
    exports = set(EXPORT_DECL.findall(text))
    for match in EXPORT_LIST.finditer(text):
        for raw in match.group(1).split(','):
            item = raw.strip()
            if not item or item.startswith('type '):
                item = item[5:].strip() if item.startswith('type ') else item
            if not item:
                continue
            if ' as ' in item:
                exports.add(item.split(' as ', 1)[1].strip())
            else:
                exports.add(item.split()[0].strip())
    wildcard = bool(EXPORT_STAR.search(text))
    return exports, wildcard


def inspect(repo, binding_path, process_path, pi_path):
    repo = Path(repo).resolve()
    binding_path = Path(binding_path).resolve()
    require(repo.is_dir(), 'repository root missing')
    require(binding_path.is_file(), 'TypeScript conformance binding missing')
    binding = json.loads(binding_path.read_text(encoding='utf-8'))
    require(binding.get('schema') == 'cat-typescript-conformance-binding/v1', 'wrong TypeScript conformance binding schema')

    _, process = read_artifact(process_path, 'process', False)
    _, pi = read_artifact(pi_path, 'pi', False)
    observations = {x['id'] for x in process.get('observations', [])}
    actions = {x['id'] for x in process.get('actions', [])}
    capability_refs = observations | actions
    operations = {x['id'] for x in pi.get('operations', [])}

    source_globs = binding.get('source_globs', ['src/**/*.ts', 'src/**/*.tsx'])
    require(isinstance(source_globs, list) and source_globs and all(isinstance(x, str) and x for x in source_globs),
            'source_globs must be a nonempty string array')
    sources = files_for(repo, source_globs)
    require(sources, 'no TypeScript source matched conformance binding')

    capabilities = binding.get('capabilities', {})
    require(isinstance(capabilities, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in capabilities.items()),
            'capabilities must map class to semantic ID')
    violations = []
    checks = []
    for kind, semantic_ref in sorted(capabilities.items()):
        if kind not in KNOWN_CAPABILITIES:
            violations.append({'kind': 'binding', 'item': kind, 'reason': 'unknown capability class'})
        elif semantic_ref not in capability_refs:
            violations.append({'kind': 'binding', 'item': kind, 'reason': 'capability maps to undeclared observation/action: ' + semantic_ref})

    detected = {}
    for path in sources:
        text = path.read_text(encoding='utf-8-sig')
        rel = str(path.relative_to(repo))
        for kind, patterns in KNOWN_CAPABILITIES.items():
            if any(pattern.search(text) for pattern in patterns):
                detected.setdefault(kind, []).append(rel)
    for kind, paths in sorted(detected.items()):
        ref = capabilities.get(kind)
        if not ref:
            violations.append({'kind': 'capability', 'item': kind, 'paths': paths,
                               'reason': 'known external capability used without CAT semantic binding'})
        else:
            checks.append({'kind': 'capability', 'item': kind, 'semantic_ref': ref, 'paths': paths, 'status': 'passed'})

    entrypoints = binding.get('public_entrypoints', [])
    require(isinstance(entrypoints, list) and all(isinstance(x, str) and x for x in entrypoints),
            'public_entrypoints must be a string array')
    interface_symbols = binding.get('interface_symbols', {})
    require(isinstance(interface_symbols, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in interface_symbols.items()),
            'interface_symbols must map exported symbol to PI operation ID')
    for symbol, ref in interface_symbols.items():
        if ref not in operations:
            violations.append({'kind': 'binding', 'item': symbol,
                               'reason': 'public symbol maps to undeclared PI operation: ' + ref})

    observed_exports = set()
    wildcard_exports = []
    for raw in entrypoints:
        rel = safe_rel(raw, 'public_entrypoint')
        path = (repo / rel).resolve()
        require(path.is_file() and path.is_relative_to(repo), 'public entrypoint missing or outside repository: ' + rel)
        found, wildcard = exports_from(path)
        observed_exports |= found
        if wildcard:
            wildcard_exports.append(rel)
    for symbol in sorted(observed_exports):
        if symbol not in interface_symbols:
            violations.append({'kind': 'interface', 'item': symbol,
                               'reason': 'public export has no PI operation binding'})
        else:
            checks.append({'kind': 'interface', 'item': symbol,
                           'semantic_ref': interface_symbols[symbol], 'status': 'passed'})
    missing_ops = sorted(operations - set(interface_symbols.values())) if entrypoints else sorted(operations)
    incomplete = []
    if wildcard_exports:
        incomplete.append('wildcard exports cannot be enumerated deterministically: ' + ', '.join(wildcard_exports))
    if missing_ops:
        incomplete.append('PI operations without public symbol mapping: ' + ', '.join(missing_ops))
    if operations and not entrypoints:
        incomplete.append('public_entrypoints not declared')

    status = 'blocked' if violations else ('inconclusive' if incomplete else 'passed')
    return {
        'schema': 'cat-typescript-conformance-evidence/v1',
        'status': status,
        'violations': violations,
        'incomplete': incomplete,
        'checks': checks,
        'detected_capabilities': detected,
        'source_files': [str(x.relative_to(repo)) for x in sources],
        'public_exports': sorted(observed_exports),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--binding', required=True)
    ap.add_argument('--process', required=True)
    ap.add_argument('--pi', required=True)
    args = ap.parse_args(argv)
    try:
        result = inspect(args.repo, args.binding, args.process, args.pi)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result['status'] == 'passed' else (3 if result['status'] == 'inconclusive' else 2)
    except (Blocked, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
