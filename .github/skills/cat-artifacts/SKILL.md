---
name: cat-artifacts
description: "Define and draft CAT Semantic Artifacts in human-readable markdown-v2: Process, PI, TCE, CommonRule, DomainRule and DomainSpec. Use when creating or changing a CAT specification Draft, process boundary, interface, behavior, cross-cutting rule or domain specification; do not use for Work or evidence management."
---

# CAT Artifact authoring

使用局面: 要求の意味が決まっており、Process/PI/TCE/CommonRule/DomainRule/DomainSpecをDraftへ具体化するとき。まず`.cat-system/docs/Artifact記法.md`を読み、新規Semantic Artifactは`semantic_contract: markdown-v2`で作成する。未承認の候補なら`cat-reverse`を使う。

1. Workの要求決定、対象Process、外部観測者、親子境界、正本revisionを明示する。
2. Processの観測可能な責務を先に固定し、内部moduleと混同しない。`Contract / Interfaces / State / Observations / Actions / Triggers`（日本語alias可）を第一級構文として記述する。
3. PIはProcess間境界として`Boundary / Fields / Operations / Constraints`を記述する。Fieldsはdirection・domain・presenceを持ち、Process内部stateをPIへ入れない。JSON ASTを手書きしない。
4. TCEは`Behaviors / 振る舞い`表でTrigger・Condition・Outcome・Effectsを同じ振る舞い単位にまとめる。`Coverage requirement / 網羅要求`は要求であり検証結果ではない。内部SQL・API method呼出しそのものをEffectにしない。
5. 式はArtifact記法で許可された限定構文だけを使う。任意コード、未定義演算、暗黙の型変換を持ち込まない。
6. 複数Artifactへ横断するプロダクト規則はCommonRule、PI/TCEへ自然に還元しづらい構造・複数実行・視覚・DOM・accessibility等はDomainSpecとして対象・要求・検証方式を明示する。式として再利用できる計算だけDomainRuleに置く。
7. 別ProcessへのEffect接続、変更されない宣言済み作用先、親Processの外部結果への経路を追跡する。
8. 未解消の意味分岐は`unknown`/`conflict`として分離し、confirmedを捏造しない。

## 定型構造はスクリプトで生成

新規Semantic Artifactの空構造は、インストール後の`python .cat-system/skills/cat-artifacts/scripts/cat_artifact_scaffold.py <kind> --id <id> --process <process-id> --source-ref <url> -o <file>`を使う。`process / pi / tce / common-rule / domain-rule / domain-spec`に対応し、必須front matter・見出し・表だけを決定論的に作る。生成時は`status: candidate`と`TO_BE_DEFINED`を明示し、要求の意味、Condition、Outcome、field、rule等を推測しない。既存ファイルは上書きしない。

機械変換が必要な場合も、`cat_compile_v2.py`にMarkdown正本を渡し、内部`cat-machine/v2` IRは生成物として扱う。旧`machine-only` JSONは移行用互換形式であり、新規作成しない。

出力: CAT/Draft下のMarkdown、使用した決定URLとProcess/PI/TCE/Rule ID、未決定事項。コード実装や実装依存テストの生成は本Skillの対象外。
