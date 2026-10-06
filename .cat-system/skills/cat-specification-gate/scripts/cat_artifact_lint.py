#!/usr/bin/env python3
"""Lightweight, deterministic CAT Markdown contract linter (not a semantic solver).

Example:
    python .cat-system/skills/cat-specification-gate/scripts/cat_artifact_lint.py --artifacts Lifecycle/CAT/Draft
Only flat YAML scalar fields plus simple block/inline scalar lists are parsed.
"""
import argparse
import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE_ROOT / "scripts"))
from catlib.markdown import parse_frontmatter

ID = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9-]+)*$")
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--files", nargs="+", type=Path, help="explicit CAT artifact files; excludes surrounding notes")
    args = parser.parse_args(argv)
    if not any([args.artifacts, args.files]):
        parser.error("specify at least one of --artifacts/--files")
    if args.artifacts and args.files:
        parser.error("--artifacts and --files are mutually exclusive")
    errors = artifact_errors(args.artifacts) if args.artifacts else artifact_errors(files=args.files)
    if errors:
        print("FAIL: contract lint", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("PASS: syntax, identifiers and explicit references (not CAT semantic completeness)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
