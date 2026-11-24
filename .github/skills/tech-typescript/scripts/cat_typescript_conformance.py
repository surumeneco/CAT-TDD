#!/usr/bin/env python3
"""Deterministic TypeScript implementation-boundary inspector for CAT.

The inspector does not infer specification. A project binding declares which
public TypeScript symbols implement PI operations and which known external
capability classes implement declared observation/action semantic IDs. Known
capability use or public exports outside that binding are violations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3]
# A distributed .github Skill in the same checkout uses the canonical
# CAT runtime parser, not a nonexistent .github/scripts copy.
if PACKAGE.name == '.github':
    PACKAGE = PACKAGE.parent / '.cat-system'
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
                resolved = path.resolve()
                require(resolved.is_relative_to(repo), "source path outside repository: " + str(path))
                result.add(resolved)
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


# This is a deliberately closed *subset* of TypeScript, not a lexer for
# arbitrary TypeScript. Every non-trivia character must be consumed by its
# grammar. No calls, member access, imports, statements other than return,
# computed keys, object parameters, default values, or ambient names exist
# in the grammar. A successful parse proves only the absence of additional
# capability use in these module bodies, not the callers or the build system.
PURE_CONTRACT = 'primitive-pure-functions/v1'
PURE_TOKEN = re.compile(
    r"(?P<trivia>[ \t\r\n\f\v]+|//[^\r\n\u2028\u2029]*|/\*[\s\S]*?\*/)"
    r"|(?P<word>[A-Za-z_$][A-Za-z0-9_$]*)"
    r"|(?P<string>'[A-Za-z0-9_ -]*'|\"[A-Za-z0-9_ -]*\")"
    r"|(?P<number>0|[1-9][0-9]*)"
    r"|(?P<operator>===|!==|&&|\|\||[(){}:;,?!|])"
)
PURE_IDENTIFIER = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*\Z')
PURE_RESERVED = set('export function return const as true false null undefined boolean string number '
                    'await yield this super class new import default let var enum implements interface '
                    'public private protected static package arguments eval'.split())


class UnsupportedPureSource(ValueError):
    pass


class PrimitivePureModule:
    """Exhaustive recognition of the explicit pure-source grammar."""
    def __init__(self, source):
        if len(source) > 65536:
            raise UnsupportedPureSource('source exceeds pure grammar bound')
        self.tokens = []
        at = 0
        while at < len(source):
            match = PURE_TOKEN.match(source, at)
            if not match:
                raise UnsupportedPureSource('unsupported token at character ' + str(at))
            if match.lastgroup != 'trivia':
                self.tokens.append((match.group(), match.lastgroup))
            at = match.end()
        if len(self.tokens) > 4096:
            raise UnsupportedPureSource('source exceeds pure token bound')
        self.pos = 0
        self.parameters = set()

    def peek(self):
        return self.tokens[self.pos][0] if self.pos < len(self.tokens) else None

    def take(self, expected=None):
        if self.pos == len(self.tokens) or (expected is not None and self.peek() != expected):
            raise UnsupportedPureSource('expected ' + str(expected) + ' at token ' + str(self.pos))
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def maybe(self, token):
        if self.peek() == token:
            self.take(token)
            return True
        return False

    def identifier(self):
        name, kind = self.take()
        if kind != 'word' or not PURE_IDENTIFIER.fullmatch(name) or name in PURE_RESERVED:
            raise UnsupportedPureSource('unsupported identifier: ' + name)
        return name

    def primitive_type(self):
        value, kind = self.take()
        if value in ('boolean', 'string', 'number'):
            return
        if kind != 'string':
            raise UnsupportedPureSource('only primitive parameters/return types or string literal unions are supported')
        while self.maybe('|'):
            if self.take()[1] != 'string':
                raise UnsupportedPureSource('only string literals in the union are supported')

    def atom(self):
        if self.maybe('('):
            self.expression()
            self.take(')')
        elif self.maybe('{'):
            names = set()
            if self.peek() != '}':
                while True:
                    name = self.identifier()
                    if name == '__proto__' or name in names:
                        raise UnsupportedPureSource('unsupported object key: ' + name)
                    names.add(name)
                    self.take(':')
                    self.expression()
                    if not self.maybe(',') or self.peek() == '}':
                        break
            self.take('}')
            if self.maybe('as'):
                self.take('const')
        else:
            value, kind = self.take()
            if not (kind in ('string', 'number') or value in ('true', 'false') or value in self.parameters):
                raise UnsupportedPureSource('undeclared value or unsupported expression: ' + value)

    def unary(self):
        while self.maybe('!'):
            pass
        self.atom()

    def equality(self):
        self.unary()
        while self.peek() in ('===', '!=='):
            self.take()
            self.unary()

    def conjunction(self):
        self.equality()
        while self.maybe('&&'):
            self.equality()

    def expression(self):
        self.conjunction()
        while self.maybe('||'):
            self.conjunction()
        if self.maybe('?'):
            self.expression()
            self.take(':')
            self.expression()

    def module(self):
        names = set()
        while self.peek() is not None:
            self.take('export')
            self.take('function')
            name = self.identifier()
            if name in names:
                raise UnsupportedPureSource('duplicate function: ' + name)
            names.add(name)
            self.parameters = set()
            self.take('(')
            if self.peek() != ')':
                while True:
                    param = self.identifier()
                    if param in self.parameters:
                        raise UnsupportedPureSource('duplicate parameter: ' + param)
                    self.parameters.add(param)
                    self.take(':')
                    self.primitive_type()
                    if not self.maybe(','):
                        break
            self.take(')')
            if self.maybe(':'):
                self.primitive_type()
            self.take('{')
            self.take('return')
            self.expression()
            self.take(';')
            self.take('}')
        if not names:
            raise UnsupportedPureSource('no public functions')
        return names


def primitive_capability_analysis(repo, binding, sources, entrypoints, operations,
                                  process, interface_symbols):
    report = {'contract': PURE_CONTRACT, 'status': 'inconclusive',
              'scope': 'explicit public TypeScript source modules; excludes callers, loader and build transforms'}
    try:
        if process.get('closed_world') is not True or process.get('observations') or process.get('actions'):
            raise UnsupportedPureSource('requires a closed Process with no declared additional observations/actions')
        if binding.get('capabilities'):
            raise UnsupportedPureSource('requires no external capability bindings')
        paths = [Path(p).as_posix() for p in binding.get('source_globs', [])]
        observed_paths = {p.relative_to(repo).as_posix() for p in sources}
        if (len(paths) != len(set(paths)) or set(paths) != observed_paths or
                {Path(p).as_posix() for p in entrypoints} != observed_paths):
            raise UnsupportedPureSource('requires exact source files equal to public entrypoints')
        names = set()
        hashes = {}
        for path in sources:
            data = path.read_bytes()
            found = PrimitivePureModule(data.decode('utf-8-sig')).module()
            if names & found:
                raise UnsupportedPureSource('duplicate public symbol across modules')
            names.update(found)
            hashes[path.relative_to(repo).as_posix()] = hashlib.sha256(data).hexdigest()
        if names != set(interface_symbols) or set(interface_symbols.values()) != operations:
            raise UnsupportedPureSource('pure module public symbols do not exactly cover the PI operations')
        report.update(status='passed', source_sha256=hashes, public_symbols=sorted(names))
    except (UnsupportedPureSource, UnicodeError, RecursionError) as exc:
        report['reason'] = str(exc) or 'unsupported grammar depth'
    return report


def inspect(repo, binding_path, process_path, pi_path, pi_extras=()):
    repo = Path(repo).resolve()
    binding_path = Path(binding_path).resolve()
    require(repo.is_dir(), 'repository root missing')
    require(binding_path.is_file(), 'TypeScript conformance binding missing')
    binding = json.loads(binding_path.read_text(encoding='utf-8'))
    require(binding.get('schema') == 'cat-typescript-conformance-binding/v1', 'wrong TypeScript conformance binding schema')

    _, process = read_artifact(process_path, 'process', False)
    pi_docs=[read_artifact(path,'pi',False) for path in (pi_path,*pi_extras)]
    observations = {x['id'] for x in process.get('observations', [])}
    actions = {x['id'] for x in process.get('actions', [])}
    capability_refs = observations | actions
    operations = {x['id'] for _,pi in pi_docs for x in pi.get('operations', [])}
    require(len(operations)==sum(len(pi.get('operations',[])) for _,pi in pi_docs),
            'duplicate PI operation across implementation boundary')

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
        require(path in sources, "public entrypoint not included in inspected source: " + rel)
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
    observed_operations = {interface_symbols[symbol] for symbol in observed_exports
                           if symbol in interface_symbols}
    missing_ops = sorted(operations - observed_operations)
    missing_symbols = sorted(set(interface_symbols) - observed_exports)
    incomplete = []
    if wildcard_exports:
        incomplete.append('wildcard exports cannot be enumerated deterministically: ' + ', '.join(wildcard_exports))
    if missing_ops:
        incomplete.append('PI operations without observed public symbol: ' + ', '.join(missing_ops))
    if missing_symbols:
        incomplete.append('bound public symbols not observed: ' + ', '.join(missing_symbols))
    if operations and not entrypoints:
        incomplete.append('public_entrypoints not declared')

    status = 'blocked' if violations else ('inconclusive' if incomplete else 'passed')
    analysis = None
    if 'capability_analysis' in binding:
        require(binding['capability_analysis'] == PURE_CONTRACT, 'unknown capability analysis contract')
        if status == 'passed':
            analysis = primitive_capability_analysis(repo, binding, sources, entrypoints, operations,
                                                     process, interface_symbols)
        else:
            analysis = {'contract': PURE_CONTRACT, 'status': 'inconclusive',
                        'reason': 'base inspector is not passing'}
    covered = ({
        'interface.'+x['semantic_ref'] for x in checks
        if x['kind']=='interface' and x['status']=='passed'
    } | {
        'capability.'+x['semantic_ref'] for x in checks
        if x['kind']=='capability' and x['status']=='passed'
    }) if status == 'passed' else set()
    if analysis and analysis['status'] == 'passed':
        covered.add('capability.closed-set')
    return {
        'schema': 'cat-typescript-conformance-evidence/v1',
        'status': status,
        'violations': violations,
        'incomplete': incomplete,
        'checks': checks,
        'detected_capabilities': detected,
        'source_files': [str(x.relative_to(repo)) for x in sources],
        'public_exports': sorted(observed_exports),
        'covered_obligation_ids': sorted(covered),
        **({'capability_analysis': analysis} if analysis is not None else {}),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--binding', required=True)
    ap.add_argument('--process', required=True)
    ap.add_argument('--pi', required=True)
    ap.add_argument('--pi-extra', action='append', default=[])
    args = ap.parse_args(argv)
    try:
        result = inspect(args.repo, args.binding, args.process, args.pi,args.pi_extra)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result['status'] == 'passed' else (3 if result['status'] == 'inconclusive' else 2)
    except (Blocked, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
