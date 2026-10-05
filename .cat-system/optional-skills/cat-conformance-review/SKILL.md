---
name: cat-conformance-review
description: "Diagnose semantic conformance of specifications, tests, and implementations against the current CAT theory. Use for CAT conformance audits and Non-CAT diagnostics; review-only unless the user separately requests edits."
metadata:
  theory: CAT
  theory_ref: forGPT/SystemDevelopment/00_理論・構想/設計理論.md
  version: "0.4"
---

# CAT Conformance Review

## 権威

CATの規範的な意味・定義は `forGPT/SystemDevelopment/00_理論・構想/設計理論.md` を唯一の理論基準とする。このSkillはProcess / PI / TCE / 閉世界 / 意味保存等の規則を独自に再定義しない。理論正本を取得できない場合はCAT適合性を確定せず、`Unknown / Not assessable` とする。

対象プロジェクトでユーザーが別の規範文書を指定した場合、その文書はプロダクト仕様の正本として扱うが、CAT理論自体の定義を置換しない。

## レビュー原則

- 規範仕様、要求/決定証拠、test/TestModel、implementation、Interface/schema/config、generated artifactを区別する。
- コードやテストの観測事実を、それだけで望ましい仕様へ昇格させない。
- CAT用語の有無ではなく、理論正本が要求する意味関係を評価する。
- 証拠不足・未調査・対象外・規範競合は `Unknown / Not assessable` とし、違反へ加点しない。
- 一つの根本原因を仕様・テスト・実装へ重複加点しない。
- 一般的なstyle、design pattern、security、performance等は、CAT仕様または明示された領域別仕様・制約に関係する場合だけ対象にする。

## 手順

1. **Scope固定**: feature / Process / artifact / revisionを固定する。repository全体を暗黙に対象へ広げない。
2. **Normative basis固定**: CAT理論正本、プロダクト仕様正本、決定記録を取得し、証拠と分離する。
3. **仕様内部レビュー**: 理論正本に照らしてProcess境界、PI、TCE、閉包、Process接続、能力、領域別仕様、実装制約の整合性を確認する。
4. **仕様→TestModel/Test**: 仕様上の区別、遷移、許容結果、不変対象、oracleが失われたり追加されたりしていないか確認する。
5. **仕様→Implementation**: 内部構造ではなく、境界から観測できるInterface・状態差・Trigger結果・観測能力・作用能力を比較する。
6. **Evidence化**: findingには可能な限り `file:line`、symbol、schema path等を付ける。不在をfindingにする場合は検索scopeを示す。

## Non-CAT診断指数

`Non-CAT` は形式証明値ではなく、レビュー対象内の非適合度を要約する診断指数とする。理論規則そのものではない。

| Dimension | Weight |
| --- | ---: |
| Process boundary & PI | 15 |
| TCE behavior semantics | 20 |
| Closure & internal consistency | 15 |
| Process links & capabilities | 10 |
| Specification → test semantic preservation | 15 |
| Specification → implementation conformance | 20 |
| Traceability, domain rules & constraints | 5 |

十分な証拠があるdimensionだけ `r_i ∈ {0, 0.25, 0.5, 0.75, 1}` を割り当てる。適用対象外は `N/A`、証拠不足は `Unknown`。

```text
Non-CAT = 100 * Σ(weight_i * r_i) / Σ(weight_i for assessed applicable dimensions)
Review Coverage = 100 * Σ(weight_i for assessed dimensions) / Σ(weight_i for applicable dimensions)
```

Severityは `Critical / Major / Minor` を用いる。推測だけの項目にはSeverityを付けず `Suspected / Unknown` とする。

## 出力

```markdown
# CAT Conformance Review

Non-CAT: <0-100 or N/A>
Review Coverage: <0-100%>
Scope: <reviewed slice>
Normative basis: <theory + product specification sources>

## Violations
### <ID> — <title>
Severity: <Critical|Major|Minor>
Evidence: <file:line / symbol / range>
CAT rule: <理論正本のsectionまたは命題>
Finding: <観測された不整合>
Conformance condition: <違反でなくなるための条件>

## Unknown / Not assessable
- ...

## Conforming observations
- ...
```

CAT状態のような補助ラベルを用いる場合も、理論上の正式な状態分類とは扱わず、診断表示であることを明示する。

## 禁止事項

- このSkill本文をCAT理論正本として扱わない。
- コード/テストを望ましい仕様へ自動昇格しない。
- 有限テスト成功を一般的な正しさの証明にしない。
- 証拠のない違反をscoreへ加点しない。
- ユーザーが依頼していない仕様変更・実装修正をレビューの一部として行わない。
