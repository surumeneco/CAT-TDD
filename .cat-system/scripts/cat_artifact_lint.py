#!/usr/bin/env python3
"""Lightweight, deterministic CAT Markdown contract linter (not a semantic solver).

Example:
    python scripts/cat_artifact_lint.py --artifacts Lifecycle/CAT/Draft
    python scripts/cat_artifact_lint.py --skills .github/skills --agents .github/agents
Only flat YAML scalar fields plus simple block/inline scalar lists are parsed.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ID = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9-]+)*$")
SKILL = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KINDS = {"process", "pi", "tce", "common-rule", "domain-rule", "domain-spec", "test-model", "candidate", "work", "gate"}
STATUSES = {"candidate", "draft", "confirmed", "unknown", "conflict", "superseded"}
SEMANTIC_KINDS = {"process", "pi", "tce", "common-rule", "domain-rule", "domain-spec"}


def _body(path):
    raw=path.read_text(encoding="utf-8-sig")
    end=raw.find("\n---\n",4)
    return raw[end+5:] if end>=0 else ""


def _has_section(body, *names):
    return any(re.search(r"(?m)^## " + re.escape(name) + r"\s*$", body) for name in names)


def _section(body, *names):
    for name in names:
        m=re.search(r"(?ms)^## " + re.escape(name) + r"\s*$\n(.*?)(?=^##\s|\Z)",body)
        if m:
            return m.group(1).strip()
    return None


def _table_info(section):
    if section is None:
        return [], []
    lines=[x.strip() for x in section.splitlines() if x.strip().startswith('|') and x.strip().endswith('|')]
    if len(lines) < 2:
        return [], []
    def cells(line):
        return [x.strip() for x in line[1:-1].split('|')]
    header=cells(lines[0])
    sep=cells(lines[1])
    if len(sep)!=len(header) or not all(re.fullmatch(r':?-{3,}:?',x) for x in sep):
        return header, []
    rows=[]
    for line in lines[2:]:
        row=cells(line)
        if len(row)==len(header):
            rows.append(dict(zip(header,row)))
    return header, rows


def _table_header(section):
    return _table_info(section)[0]


def _require_table_columns(errors, path, body, section_names, column_groups, require_row=False):
    section=_section(body,*section_names)
    header,rows=_table_info(section)
    for group in column_groups:
        if not any(name in header for name in group):
            errors.append(f"{path}: markdown-v2 {'/'.join(section_names)} missing column {sorted(group)}")
    if require_row and not rows:
        errors.append(f"{path}: markdown-v2 {'/'.join(section_names)} requires at least one data row")
    return rows


def _scalar(value):
    value = value.strip()
    if value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"inline lists must use JSON-compatible scalar syntax: {exc}") from exc
    if len(value) >= 2 and value.startswith(("\"", "'")) and value.endswith(value[0]):
        return value[1:-1]
    return value


def parse_frontmatter(path):
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.startswith("---\n"):
        raise ValueError("missing YAML front matter at first line")
    end = raw.find("\n---\n", 4)
    if end < 0:
        raise ValueError("front matter closing delimiter missing")
    lines = raw[4:end].splitlines()
    fields = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if not match:
            raise ValueError(f"unsupported front matter line: {line[:80]}")
        key, value = match.groups()
        if key in fields:
            raise ValueError(f"duplicate field: {key}")
        if value:
            fields[key] = _scalar(value)
            i += 1
            continue
        items = []
        i += 1
        while i < len(lines):
            child = lines[i]
            if not child.strip() or child.lstrip().startswith("#"):
                i += 1
                continue
            item = re.match(r"^\s{2,}-\s+(.+?)\s*$", child)
            if not item:
                break
            parsed = _scalar(item.group(1))
            if isinstance(parsed, list):
                raise ValueError(f"{key}: nested lists are unsupported")
            items.append(parsed)
            i += 1
        fields[key] = items
    return fields


def artifact_errors(root=None, files=None):
    errors = []
    records = {}
    if files is not None:
        paths = sorted(Path(f) for f in files)
        if not paths:
            return ["--files requires at least one file"]
    elif root is not None and root.exists():
        paths = sorted(root.rglob("*.md"))
    else:
        return [f"{root}: path missing"]
    for path in paths:
        try:
            f = parse_frontmatter(path)
            for key in ("cat_version", "kind", "id", "status", "process", "source_refs", "refs"):
                if key not in f:
                    errors.append(f"{path}: required key {key} missing")
            identifier = f.get("id", "")
            if not ID.fullmatch(identifier):
                errors.append(f"{path}: invalid artifact ID '{identifier}'")
            elif identifier in records:
                errors.append(f"{path}: duplicate artifact ID '{identifier}' also {records[identifier][0]}")
            else:
                records[identifier] = (path, f)
            if f.get("kind") not in KINDS:
                errors.append(f"{path}: invalid kind {f.get('kind')}")
            if f.get("status") not in STATUSES:
                errors.append(f"{path}: invalid status {f.get('status')}")
            if not ID.fullmatch(f.get("process", "")):
                errors.append(f"{path}: invalid process reference")
            if f.get("status") == "confirmed" and not f.get("decision_ref"):
                errors.append(f"{path}: confirmed requires decision_ref")
            if f.get("kind") in SEMANTIC_KINDS and f.get("semantic_contract") not in {"markdown-v2", "markdown-v1", "machine-only"}:
                errors.append(f"{path}: semantic_contract must be markdown-v2 (preferred), markdown-v1 or machine-only (legacy)")
            if f.get("language") not in (None, "ja", "en"):
                errors.append(f"{path}: language must be ja or en when present")
            if f.get("semantic_contract") == "markdown-v2":
                body=_body(path)
                required_sections={
                    "process":[("Contract","契約"),("Interfaces","境界"),("State","仕様状態"),
                               ("Observations","観測能力"),("Actions","作用能力"),("Triggers","起点")],
                    "pi":[("Boundary","境界"),("Fields","項目"),("Operations","操作"),("Constraints","制約")],
                    "tce":[("Behaviors","振る舞い")],
                    "common-rule":[("Rules","規則")],
                    "domain-rule":[("Definitions","定義")],
                    "domain-spec":[("Targets","対象"),("Rules","規則")],
                }.get(f.get("kind"),[])
                for names in required_sections:
                    if not _has_section(body,*names):
                        errors.append(f"{path}: markdown-v2 missing section {'/'.join(names)}")
                if f.get('kind')=='process':
                    _require_table_columns(errors,path,body,('Interfaces','境界'),[{'PI','pi'}],require_row=True)
                    _require_table_columns(errors,path,body,('State','仕様状態'),[{'ID','Id','id'},{'Domain','domain'}])
                    _require_table_columns(errors,path,body,('Observations','観測能力'),
                                           [{'ID','Id','id'},{'Source','Origin','source','由来','情報源'},{'Domain','domain'}])
                    _require_table_columns(errors,path,body,('Actions','作用能力'),
                                           [{'ID','Id','id'},{'Target','target','対象'},{'Domain','domain'}])
                    _require_table_columns(errors,path,body,('Triggers','起点'),
                                           [{'ID','Id','id'},{'Source','Origin','source','origin','由来','起点元'}],require_row=True)
                if f.get('kind')=='tce':
                    if not re.search(r'(?im)^(?:Coverage requirement|網羅要求):\s*(?:closed|partial|閉包|部分)\s*$',body):
                        errors.append(f"{path}: markdown-v2 TCE requires Coverage requirement/網羅要求")
                    if _has_section(body,'Rules','Effects'):
                        errors.append(f"{path}: markdown-v2 TCE must use Behaviors/振る舞い, not legacy Rules/Effects")
                    _require_table_columns(errors,path,body,('Behaviors','振る舞い'),
                                           [{'ID','Id','id'},{'Trigger','trigger','起点'},{'Condition','When','condition','when','条件'},
                                            {'Outcome','outcome','結果'},{'Effects','Effect','effects','effect','効果'}],require_row=True)
                if f.get('kind')=='pi':
                    _require_table_columns(errors,path,body,('Boundary','境界'),
                                           [{'Peer process','Peer Process','peer','相手Process','相手プロセス'},{'Direction','direction','方向'}],require_row=True)
                    header=_table_header(_section(body,'Fields','項目'))
                    if 'Role' in header or 'role' in header or '役割' in header:
                        errors.append(f"{path}: markdown-v2 PI must not contain Role/state; use Direction and Process State")
                    required_alias_groups=[{'ID','Id','id'},{'Direction','direction','方向'},
                                           {'Domain','domain'},{'Presence','presence','存在'}]
                    _require_table_columns(errors,path,body,('Fields','項目'),required_alias_groups,require_row=True)
                    _require_table_columns(errors,path,body,('Operations','操作'),
                                           [{'ID','Id','id'},{'Direction','direction','方向'},{'Trigger','trigger','起点'}])
                    _require_table_columns(errors,path,body,('Constraints','制約'),
                                           [{'Expression','Condition','expression','condition','式','条件'}])
                if f.get('kind')=='common-rule':
                    rows=_require_table_columns(errors,path,body,('Rules','規則'),
                                               [{'ID','Id','id'},{'Applies to','Applies To','applies_to','適用対象'},
                                                {'Requirement','requirement','要求'},{'Verification','verification','検証'}],require_row=True)
                    for row in rows:
                        if any(not row.get(name,'').strip() for name in row):
                            errors.append(f"{path}: common-rule rows must not contain empty cells")
                if f.get('kind')=='domain-rule':
                    _require_table_columns(errors,path,body,('Definitions','定義'),
                                           [{'ID','Id','id'},{'Parameters','Params','parameters','params','引数'},
                                            {'Expression','Body','expression','body','式'}],require_row=True)
                if f.get('kind')=='domain-spec':
                    targets=_require_table_columns(errors,path,body,('Targets','対象'),
                                                   [{'Ref','Reference','ref','参照'},{'Aspect','aspect','観点'}],require_row=True)
                    rules=_require_table_columns(errors,path,body,('Rules','規則'),
                                                 [{'ID','Id','id'},{'Condition','condition','条件'},
                                                  {'Requirement','requirement','要求'},{'Verification','verification','検証'}],require_row=True)
                    for row in targets+rules:
                        if any(not value.strip() for value in row.values()):
                            errors.append(f"{path}: domain-spec rows must not contain empty cells")
            for key in ("source_refs", "refs"):
                if not isinstance(f.get(key), list) or not all(isinstance(x, str) and x.strip() for x in f.get(key, [])):
                    errors.append(f"{path}: {key} must be a scalar list")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    for identifier, (path, fields) in records.items():
        for ref in fields.get("refs", []):
            if ref not in records:
                errors.append(f"{path}: unresolved refs ID '{ref}' (partial snapshots require all referenced artifacts)")
    return errors


def skill_errors(root):
    errors = []
    if not root.exists():
        return [f"{root}: path missing"]
    for path in sorted(root.glob("*/SKILL.md")):
        try:
            f = parse_frontmatter(path)
            name = f.get("name", "")
            if name != path.parent.name or not SKILL.fullmatch(name) or len(name) > 64:
                errors.append(f"{path}: skill name mismatch or invalid: '{name}'")
            if not f.get("description") or len(f["description"]) > 1024:
                errors.append(f"{path}: missing/overlong description")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    return errors


def agent_errors(root):
    errors = []
    if not root.exists():
        return [f"{root}: path missing"]
    for path in sorted(root.glob("*.agent.md")):
        try:
            f = parse_frontmatter(path)
            if f.get("name") != path.name.removesuffix(".agent.md"):
                errors.append(f"{path}: agent name mismatch")
            if not f.get("description"):
                errors.append(f"{path}: description missing")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--files", nargs="+", type=Path, help="explicit CAT artifact files; excludes surrounding notes")
    parser.add_argument("--skills", type=Path)
    parser.add_argument("--agents", type=Path)
    args = parser.parse_args(argv)
    if not any([args.artifacts, args.files, args.skills, args.agents]):
        parser.error("specify at least one of --artifacts/--skills/--agents")
    errors = []
    if args.artifacts and args.files:
        parser.error("--artifacts and --files are mutually exclusive")
    if args.artifacts:
        errors.extend(artifact_errors(args.artifacts))
    if args.files:
        errors.extend(artifact_errors(files=args.files))
    if args.skills:
        errors.extend(skill_errors(args.skills))
    if args.agents:
        errors.extend(agent_errors(args.agents))
    if errors:
        print("FAIL: contract lint", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("PASS: syntax, identifiers and explicit references (not CAT semantic completeness)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())