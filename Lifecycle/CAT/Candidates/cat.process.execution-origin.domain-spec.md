---
cat_version: '0.3'
kind: domain-spec
id: cat.process.execution-origin
status: draft
process: cat.compiler
source_refs:
  - Docs/Decisions/GEN02-03-04-approval-20261118.md
decision_ref: ''
refs: []
semantic_contract: markdown-v2
language: ja
---

# 実行元Processを相手とするPIの意味候補

## 対象

| 参照 | 観点 |
| --- | --- |
| cat.compiler.pi | PI相手Processの静的／実行時動的な記述 |
| cat.compiler.execution | 実行単位の開始元相関と証拠境界 |

## 規則

| ID | 条件 | 要求 | 検証 |
| --- | --- | --- | --- |
| EO.boundary | PIで相手を実行元Processと宣言する | 固定されたProcess名ではなく、対象実行を開始したProcessへ束縛する。静的相手宣言を破壊せず、実装上のコンポーネント数やtransport方式を義務化しない | 静的／動的境界の出典付きparse・model差分・未宣言の拒否 |
| EO.operation | Operationが実行元Processに対応する | 1つのOperationを複数の実行元に対して記述でき、固定peerへの暗黙展開を規範としない | 2種類の相手からの起動・既存静的対応・型不整合・未宣言相手 |
| EO.correlation | 実行からの提供を実行元へ戻す | 同一実行の開始元との結び付きが必要であり、別実行の結果や開始元を代用しない。複数の同種コンポーネント呼出しを実行識別子で区別する | 複数同時実行、結果先取り違え、実行ID重複・欠落・未知起点の負例 |
| EO.proof | 静的Compositionまたは自己申告Traceを検査する | 同じ型やOperation名が一致しても実行元配送は未証明。未対応はinconclusive、明示相関矛盾はblockedとする | 有効な自己申告でもnormative_status=inconclusive・静的合成は未証明を維持 |

## 適用境界

本書は意味と最小反例の候補を定めるDraftであり、正式なProcess Closure・Model Conformance・外部Effectの合格証拠ではない。形式記法、動的なProcess参照の独立検証手法、真正な実施観測Providerについて追加の意味判断を必要とする場合、未確定部分を推測でConfirmedに変更しない。
