#!/usr/bin/env python3
"""Generate syntax-stable CAT Semantic Artifact Markdown scaffolds without inventing semantics."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ID = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9-]+)*$")
KINDS = ("process", "pi", "tce", "common-rule", "domain-rule", "domain-spec")

SECTIONS = {
    "ja": {
        "process": """# Process: {id}\n\n## 契約\n\nTO_BE_DEFINED\n\n## 境界\n\n| PI |\n| --- |\n| TO_BE_DEFINED |\n\n## 仕様状態\n\n| ID | Domain |\n| --- | --- |\n\n## 観測能力\n\n| ID | 由来 | Domain |\n| --- | --- | --- |\n\n## 作用能力\n\n| ID | 対象 | Domain |\n| --- | --- | --- |\n\n## 起点\n\n| ID | 起点元 |\n| --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED |\n""",
        "pi": """# PI: {id}\n\n## 境界\n\n| 相手Process | 方向 |\n| --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED |\n\n## 項目\n\n| ID | 方向 | Domain | 存在 |\n| --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n\n## 操作\n\n| ID | 方向 | 起点 |\n| --- | --- | --- |\n\n## 制約\n\n| 条件 |\n| --- |\n""",
        "tce": """# TCE: {id}\n\n網羅要求: partial\n\n## 振る舞い\n\n| ID | 起点 | 条件 | 結果 | 効果 |\n| --- | --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n""",
        "common-rule": """# Common Rule: {id}\n\n## 規則\n\n| ID | 適用対象 | 要求 | 検証 |\n| --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n""",
        "domain-rule": """# Domain Rule: {id}\n\n## 定義\n\n| ID | 引数 | 式 |\n| --- | --- | --- |\n| TO_BE_DEFINED | — | TO_BE_DEFINED |\n""",
        "domain-spec": """# Domain Specification: {id}\n\n## 対象\n\n| 参照 | 観点 |\n| --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED |\n\n## 規則\n\n| ID | 条件 | 要求 | 検証 |\n| --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n""",
    },
    "en": {
        "process": """# Process: {id}\n\n## Contract\n\nTO_BE_DEFINED\n\n## Interfaces\n\n| PI |\n| --- |\n| TO_BE_DEFINED |\n\n## State\n\n| ID | Domain |\n| --- | --- |\n\n## Observations\n\n| ID | Source | Domain |\n| --- | --- | --- |\n\n## Actions\n\n| ID | Target | Domain |\n| --- | --- | --- |\n\n## Triggers\n\n| ID | Source |\n| --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED |\n""",
        "pi": """# PI: {id}\n\n## Boundary\n\n| Peer process | Direction |\n| --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED |\n\n## Fields\n\n| ID | Direction | Domain | Presence |\n| --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n\n## Operations\n\n| ID | Direction | Trigger |\n| --- | --- | --- |\n\n## Constraints\n\n| Expression |\n| --- |\n""",
        "tce": """# TCE: {id}\n\nCoverage requirement: partial\n\n## Behaviors\n\n| ID | Trigger | Condition | Outcome | Effects |\n| --- | --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n""",
        "common-rule": """# Common Rule: {id}\n\n## Rules\n\n| ID | Applies to | Requirement | Verification |\n| --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n""",
        "domain-rule": """# Domain Rule: {id}\n\n## Definitions\n\n| ID | Parameters | Expression |\n| --- | --- | --- |\n| TO_BE_DEFINED | — | TO_BE_DEFINED |\n""",
        "domain-spec": """# Domain Specification: {id}\n\n## Targets\n\n| Ref | Aspect |\n| --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED |\n\n## Rules\n\n| ID | Condition | Requirement | Verification |\n| --- | --- | --- | --- |\n| TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED | TO_BE_DEFINED |\n""",
    },
}


def render(kind: str, identifier: str, process: str, source_ref: str, language: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unsupported kind: {kind}")
    if not ID.fullmatch(identifier):
        raise ValueError(f"invalid artifact id: {identifier}")
    if not ID.fullmatch(process):
        raise ValueError(f"invalid process id: {process}")
    if not source_ref.strip():
        raise ValueError("source_ref must be nonempty; use an actual normative/evidence reference")
    body = SECTIONS[language][kind].format(id=identifier)
    return f"""---
cat_version: '0.3'
kind: {kind}
id: {identifier}
status: candidate
process: {process}
source_refs:
  - {source_ref}
decision_ref: ''
refs: []
semantic_contract: markdown-v2
language: {language}
---

{body}"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--id", required=True)
    parser.add_argument("--process", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--language", choices=("ja", "en"), default="ja")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        text = render(args.kind, args.id, args.process, args.source_ref, args.language)
        if args.output.exists():
            raise ValueError(f"will not overwrite existing file: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
        print(args.output)
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"BLOCKED: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
