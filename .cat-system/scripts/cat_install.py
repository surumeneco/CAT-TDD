#!/usr/bin/env python3
"""Idempotent non-destructive VS Code/Copilot package planner/installer.

Plan by default. Requires --apply for writes; existing differing files are
never overwritten without --overwrite. Does not choose the technology stack.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from catlib.common import Blocked, json_bytes, read_json, require
from catlib.work import work_file


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(work, adapter):
    cat = read_json(ROOT / 'config/routing.json')['technology_skills']
    configured = set()
    for tech, mapped in cat.items():
        require(isinstance(mapped, str) or
                (isinstance(mapped, list) and mapped and all(isinstance(x, str) and x for x in mapped)),
                f'invalid technology skill mapping: {tech}')
        configured.update([mapped] if isinstance(mapped, str) else mapped)
    common = sorted(p for p in (ROOT / 'skills').glob('*/SKILL.md')
                    if p.parent.name not in configured)
    selected = []
    for tech in sorted(set(work.get('technologies', []))):
        require(tech in cat, f'no configured technology Skill for documented Work tech: {tech}')
        mapped = cat[tech]
        selected.extend(ROOT / 'skills' / name / 'SKILL.md'
                        for name in ([mapped] if isinstance(mapped, str) else mapped))
    extension = None
    if adapter:
        require(adapter.endswith('-adapter'), 'adapter name must end in -adapter')
        extension = ROOT / 'extensions' / adapter
        require((extension / 'SKILL.md').is_file(), f'adapter absent: {adapter}')
    skills = common + selected
    require(all(p.is_file() for p in skills), 'selected skill absent')
    agents = sorted((ROOT / 'agents').glob('*.agent.md'))
    return agents, skills, extension


def _add_tree(files, base, dest_base):
    if not base.exists():
        return
    candidates = [base] if base.is_file() else sorted(p for p in base.rglob('*') if p.is_file())
    for source in candidates:
        if '__pycache__' in source.parts or source.suffix == '.pyc':
            continue
        rel = source.name if base.is_file() else source.relative_to(base)
        files.append((source, dest_base / rel))


def plan(target, agents, skills, overwrite, extension=None):
    files = []
    for top in ('README.md', 'scripts', 'docs', 'config', 'optional-skills'):
        base = ROOT / top
        dest = target / '.cat-system' / top if base.is_dir() else target / '.cat-system'
        _add_tree(files, base, dest)
    # Only selected skills are present in the runtime package; copy the complete Skill
    # directory so its scripts/references/assets remain available to the Skill.
    for skill in skills:
        skill_dir = skill.parent
        _add_tree(files, skill_dir, target / '.cat-system' / 'skills' / skill_dir.name)
        _add_tree(files, skill_dir, target / '.github' / 'skills' / skill_dir.name)
    for agent in agents:
        files.append((agent, target / '.cat-system' / 'agents' / agent.name))
        files.append((agent, target / '.github' / 'agents' / agent.name))
    if extension is not None:
        for source in sorted(p for p in extension.rglob('*') if p.is_file()):
            rel = source.relative_to(extension)
            files.append((source, target / '.cat-system' / 'extensions' / extension.name / rel))
        _add_tree(files, extension, target / '.github' / 'skills' / extension.name)
    # Deduplicate exact destinations while preserving deterministic order.
    unique = {}
    for source, dest in files:
        unique[str(dest)] = (source, dest)
    result = []
    for source, dest in sorted(unique.values(), key=lambda x: str(x[1])):
        require(not dest.is_symlink(), f'refusing symlink target: {dest}')
        state = 'create'
        if dest.exists():
            require(dest.is_file(), f'non-file target: {dest}')
            state = 'same' if digest(source) == digest(dest) else ('replace' if overwrite else 'conflict')
        result.append((source, dest, state))
    return result


def planned_reference_errors(target, rows):
    """Validate local Markdown references against the post-install file set before writing."""
    planned = {dest.resolve(): source for source, dest, _ in rows}
    errors = []
    md_link = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
    runtime_ref = re.compile(r'`(\.cat-system/[^`\s]+)`')
    for source, dest, _ in rows:
        if source.suffix.lower() != '.md':
            continue
        text = source.read_text(encoding='utf-8-sig')
        refs = []
        for raw in md_link.findall(text):
            ref = raw.strip().split('#', 1)[0]
            if not ref or '://' in ref or ref.startswith(('mailto:', '#')):
                continue
            refs.append((dest.parent / ref).resolve())
        for raw in runtime_ref.findall(text):
            # Only concrete file references are enforceable. Directory mentions and
            # set-notation/examples are documentation, not required installed files.
            if raw.endswith('/') or any(ch in raw for ch in '{}*<>') or '...' in raw:
                continue
            if not Path(raw).suffix:
                continue
            refs.append((target / raw).resolve())
        for ref in refs:
            if ref not in planned and not ref.exists():
                errors.append(f'{dest.relative_to(target)} -> missing {ref.relative_to(target) if ref.is_relative_to(target) else ref}')
    return sorted(set(errors))


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--project-root', required=True)
    cli.add_argument('--work', required=True)
    cli.add_argument('--adapter', help='optional explicitly selected <project>-adapter')
    cli.add_argument('--apply', action='store_true')
    cli.add_argument('--overwrite', action='store_true', help='explicitly replace conflicting managed files')
    args = cli.parse_args(argv)
    try:
        _, w = work_file(args.work)
        target = Path(args.project_root).resolve()
        require(target.is_dir(), 'project root directory not found')
        agents, skills, extension = sources(w, args.adapter)
        files = plan(target, agents, skills, args.overwrite, extension)
        conflicts = [str(dst) for _, dst, state in files if state == 'conflict']
        refs = planned_reference_errors(target, files)
        require(not refs, 'post-install references unresolved: ' + '; '.join(refs[:10]))
        if args.apply:
            require(not conflicts, f'conflicting files: {conflicts[:10]} (run without --apply to inspect)')
            for source, dest, state in files:
                if state == 'same':
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_name(dest.name + '.cat-install.tmp')
                require(not temp.exists(), f'leftover temporary file: {temp}')
                shutil.copyfile(source, temp)
                os.replace(temp, dest)
        result = {'project_root': str(target), 'work_id': w['id'], 'apply': args.apply,
                  'installed_techs': sorted(set(w['technologies'])),
                  'adapter': args.adapter, 'agent_files': len(agents), 'skill_files': len(skills),
                  'created': sum(s == 'create' for _, _, s in files),
                  'identical': sum(s == 'same' for _, _, s in files),
                  'replacements': sum(s == 'replace' for _, _, s in files),
                  'conflicts': conflicts, 'reference_errors': refs,
                  'status': 'blocked' if conflicts else ('applied' if args.apply else 'plan-only'),
                  'note': 'Static package/reference checks passed; Copilot runtime behavior still requires environment validation'}
        print(json_bytes(result).decode(), end='')
        return 2 if conflicts else 0
    except (Blocked, OSError) as exc:
        print(json_bytes({'status':'blocked', 'error':str(exc)}).decode(), file=sys.stderr, end='')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
