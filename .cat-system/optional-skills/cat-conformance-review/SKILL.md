---
name: cat-conformance-review
description: "Diagnose semantic conformance of specifications, tests, test models, and implementations against CAT (Closed-world Abstraction and Transformation). Use for CAT conformance audits, Non-CAT diagnostics, PI/TCE reviews, or checks that specification meaning is preserved through test and implementation. Self-contained; no external CAT theory document is required."
compatibility: "Requires read access to the artifacts under review. Review-only unless the user separately requests edits."
metadata:
  theory: CAT
  expansion: Closed-world Abstraction and Transformation
  version: "0.5"
---


# CAT Conformance Review


## 目的


既存の仕様、テストモデル、テスト、ソースコード、および必要に応じて関連するInterface・schema・設定・領域別仕様を、CATへの**意味上の適合性**に限定してレビューする。


このSkillは単体で導入・利用できる。CATレビューに必要な基準は本Skill内に保持し、特定repository、特定Google Driveパス、別Skill、別文書の存在を前提にしない。


レビュー結果は `Non-CAT` を非適合度の診断指数として示し、CAT上の違反を証拠付きで列挙する。一般的なコード品質、好み、命名、style、design pattern、security、performance等は、それ自体ではCAT違反にしない。CAT仕様、領域別仕様、または明示された実装制約に関係する場合だけ対象にする。


このSkillはレビュー専用である。ユーザーが明示的に変更を依頼しない限り、仕様、テスト、ソース、設定、snapshot等を書き換えない。


## 規範の扱い


### 内蔵CAT基準


本Skillの「CAT基準」を、外部規範が与えられていない場合のレビュー基準とする。これはCATレビューを単体で成立させるための実用的な基準であり、形式証明器そのものではない。


### 外部のCAT規範がある場合


ユーザーまたは対象projectが、別のCAT理論文書・仕様体系を明示的に規範として指定している場合、その文書を対象projectにおけるCAT規範として優先する。


その場合も本Skillの基準を無視せず、次のように扱う。


- 外部規範が本Skillの基準を具体化・拡張する場合は、その追加条件を含めて評価する。
- 外部規範が本Skillの基準と異なる場合は、差分を明示し、外部規範に従った評価とする。
- 外部規範が取得できない場合でも、本Skill単体のCAT基準によるレビューは継続できる。ただし、project固有規範への適合性は `Unknown / Not assessable` とする。


### 規範と証拠を分離する


規範的入力の優先順位は次の通りとする。


1. ユーザーが規範的仕様またはCAT規範として明示した文書・決定。
2. 対象repositoryやproject内で明示的に正本・仕様・契約として扱われている成果物。
3. 本Skillの内蔵CAT基準。
4. それ以外の文書、テスト、ソース、実行結果は現状を示す証拠。


テストやソースに存在する振る舞いを、それだけを理由に望ましい仕様へ昇格してはならない。プロダクト仕様が不明な場合は、コードから仕様を推測して適合と判定せず、該当範囲を `Unknown / Not assessable` とする。


## 判定原則


### 用語ではなく意味を判定する


`Process`、`PI`、`TCE` という名称を使っていないこと自体は違反ではない。同等の境界、状態空間、Trigger、Condition、Effect、許容結果、接続関係が一意に復元できるなら、その意味を評価する。


逆にPI/TCEという語を使用していても、必要な状態領域や振る舞いが欠落・矛盾していれば適合扱いにしない。


### 確認できないものを違反にしない


証拠不足、未調査、対象外、規範の競合は `Unknown / Not assessable` とする。未確認事項をNon-CATへ加点しない。


ただし、対象scopeを十分に探索した結果として「CAT上必要な定義が存在しない」こと自体を確認できた場合は、その欠落を違反として扱える。単に見つけられなかっただけなら違反にしない。


### 同一原因を重複加点しない


一つの根本原因が仕様、テスト、実装へ連鎖している場合、違反は根本原因を中心に一件として記録し、派生影響をその項目内に列挙する。別々の独立した意味破壊だけを別違反とする。


## CAT基準


### Process境界


- Processは実装moduleではなく、観測と責務を定める任意粒度のブラックボックス境界として扱えること。
- Processは必要に応じて入れ子にでき、上位Processの仕様を内部class/function/service構造へ還元しないこと。
- 境界の相手、観測可能なInterface、利用可能な観測能力、作用能力が、対象の意味を判定できる程度に定義されていること。
- 観測能力は、時刻、乱数、環境値、外部応答等、Conditionを決めるために読み取れる情報源を含む。
- 作用能力は、返却、状態更新、外部Processへの作用等、Effectを成立させるために変化させられる対象を含む。


### PI


PIはProcess間の境界上で仕様上区別する状態空間であり、単なる実装型定義ではない。


次が必要な範囲で識別できること。


- 相手となるProcess。
- 入力、出力、受付操作、提供操作等の方向。
- 境界上で区別する項目。
- 各項目の集合・領域。
- 複数項目の組合せ成立条件。
- 必須、不在、optional、undefined等の区別。
- 後続の振る舞いを変える状態差。


Process間接続では、概念的に次の包含が成立すること。


```text
送信側が出し得る状態 ⊆ 受信側が受け入れられる状態
```


境界から観測されない内部補助Interfaceまで禁止するものではない。


### TCE


振る舞いを `Trigger -> Condition -> Effect` の関係として解釈できること。


- **Trigger**: 振る舞いを評価する起点。
- **Condition**: Trigger成立時の仕様状態を区別する条件。
- **Effect**: 結果として成立しなければならない返却、状態変化、外部作用または関係。


次を満たすこと。


- Triggerの発生源が仕様世界内で追跡できる。
- Conditionが宣言済みの仕様状態・観測能力だけを参照する。
- Conditionが参照する状態は、少なくともPI、到達可能な過去のEffect、宣言済み観測能力のいずれかへ由来する。
- Effectは実装手順ではなく、成立すべき結果・許容結果として定義される。
- Effectの作用先が当該Processの作用能力から利用可能である。
- 同一Triggerについて、到達可能なCondition領域に欠落、意図しない重複、矛盾がない。
- 到達不能な分岐や、後続状態・出力・領域別判定へ寄与しないEffectを、必要性または接続欠落の観点から説明できる。


EffectはActionではない。たとえば `Repository.save()`、`COMMIT`、特定API呼出し等の実装手順そのものをEffectとして要求しない。必要なのは、境界から観測した時に何が成立するかである。


複数結果を許す場合は、許容結果集合として保持する。


```text
E: result ∈ {A, B}
```


### Process仕様と領域別仕様


Processの仕様は概念的に次で構成する。


```text
Process Specification
= PI
+ TCE
+ 共通規則
+ 必要な領域別仕様
```


領域別仕様は、PI/TCEだけでは自然に保存しにくいが、適合判定には必要な構造・複数実行間関係・視覚・DOM・accessibility・統計的性質等を扱える。


領域別仕様を用いる場合は、少なくとも次を確認する。


- 対象となる状態・実行・構造。
- 許容される関係。
- 検証方法またはテストモデルへの変換規則。
- PI/TCEで表せる意味を無意味に二重定義していないこと。


技術選定、依存関係、静的解析、coding rule等は、同じ仕様上の振る舞いを満たす実装方法を制限する**実装制約**として区別する。振る舞い差を生む場合はPI/TCE/領域別仕様にも反映する。


### 閉包と閉世界


仕様要素は、明示された宣言とそこから到達可能な導出からなる最小の閉包として扱えること。


- 参照元のない状態、Trigger、Condition参照、Effect、Interface接続を残さない。
- 仕様が区別しない差異を、実装者やAIが独自に意味のある仕様として追加しない。
- 明示された変更以外を不変とみなす閉世界上の判定が、対象仕様から成立する。
- 変更が許可されていない作用先は、同じTrigger/Conditionで不変として扱える。
- 仕様世界に痕跡のない独立要件の発見までCATが保証すると扱わない。


CATが扱う完全性は、宣言された仕様世界の**内部完全性**である。必要な要件がすべて発見済みであることとは区別する。


### Process間接続と能力


- 接続されるProcess間でInterfaceの方向、項目、領域、成立条件が整合している。
- 一方が出力しない値を他方が入力前提にしない。
- 送信側が出し得る状態を、受信側が受け入れられない状態のまま接続しない。
- Conditionが利用する観測元が当該Processから利用可能である。
- Effectが要求する作用先が当該Processから制御可能である。


概念的な必要条件は次の通り。


```text
参照する観測 ⊆ Processが利用できる観測能力
要求する作用先 ⊆ Processが制御できる対象
```


これを満たしても、計算量、物理制約、資源制約、外部サービス保証等を含む実現可能性全体が証明されたとは扱わない。


### 仕様からテストへの意味保存


テストモデルまたはテストが、仕様上区別される状態、Trigger、Condition領域、遷移、許容結果、不変対象を失わないこと。


少なくとも次を確認する。


- **欠落がない**: 到達可能な仕様上の区別に対応するテストモデル要素が存在する。
- **余計な区別を加えない**: テスト側の仕様的な区別はPI/TCE/共通規則/領域別仕様へ由来を遡れる。
- **許容結果を保存する**: 仕様が許す複数結果を、根拠なく一つへ狭めない。
- **到達可能性を保存する**: 到達不能状態を通常ケースへ混入させず、必要な状態遷移列を失わない。
- **不変対象を保存する**: 変更が許可されていない状態を変更可能として扱わない。


具体テストは有限な選択であり、有限個の例だけで任意実装の完全な正しさを証明したと扱わない。


### 実装適合性


Interfaceについて次を基準にする。


```text
境界から観測可能な実装Interface ⊆ 宣言済みInterface
PIの必須Interface ⊆ 境界から観測可能な実装Interface
```


振る舞いについて、仕様状態 `s` とTrigger `t` に対する実装の観測可能な結果が、仕様で許容された結果集合 `B_P(t, s)` の範囲内にあることを確認する。


一つの仕様状態 `s` に複数の実装内部状態 `a`, `b` が対応し、同じTriggerに対して異なる観測可能結果 `X`, `Y` を生む場合は、次のいずれかが必要である。


- `X` と `Y` の双方が同じ仕様状態の許容結果に含まれる。
- `a` と `b` の差が仕様状態へ昇格されている。


どちらでもない場合は、仕様が区別しないhidden stateが振る舞いを変えている。


実装が仕様にない時刻、乱数、環境変数、file、network、外部状態等を観測し、その差で仕様上の振る舞いを変える場合は未宣言の観測能力として検査する。仕様にない作用先へEffectを生じさせる場合も同様に検査する。


領域別仕様、非機能制約、実装技術制約が規範的入力として明示されている場合は、その範囲も適合性へ含める。


### 仕様同値性と交換可能性


同じProcess境界に対する二つの仕様が、到達可能な範囲で同じTrigger・仕様状態に対して同じ許容結果関係を与えるなら、仕様上同値と扱える。


実装交換可能性は、宣言されたPI、TCE、領域別仕様、観測範囲、実装制約についての交換可能性である。性能、費用、資源、可用性等を交換条件に含めるなら、それらも規範として宣言されている必要がある。


## レビュー手順


### 1. Scopeを固定する


ユーザー指定scopeを最優先する。明示がなければ現在の依頼から対象feature、Process、artifact、revisionを推定し、repository全体を無条件にレビューしない。


確認するartifactを次へ分類する。


- normative specification
- requirement / decision evidence
- tests / test model
- implementation source
- Interface / schema / configuration
- generated artifact
- unknown provenance


### 2. 規範的仕様世界を復元する


規範的仕様から、対象sliceについて次を内部的に整理する。


- Process境界
- PI / 仕様状態
- Trigger
- Condition領域
- Effect / 許容結果
- 共通規則
- Process接続
- 観測能力
- 作用能力
- 領域別仕様
- 実装制約


未記載の意味を補完しない。複数解釈が成立する箇所は `Unknown` または違反候補として保持する。


### 3. 仕様内部を検査する


参照整合性、Condition coverage、overlap、contradiction、reachability、不要要素、閉包、閉世界上の不変対象、Process接続、観測/作用能力の整合を確認する。


### 4. 仕様とTestModel/Testを比較する


特に次を探す。


- 仕様にあるがTestModel/Test側で失われた意味。
- TestModel/Testが仕様にない期待値を追加している箇所。
- 許容結果を不当に狭めている箇所。
- 到達可能性を失っている箇所。
- 不変対象を変更可能として扱う箇所。
- 実InterfaceからTestModel上の抽象分類への意味写像が欠落している箇所。


### 5. 仕様と実装を比較する


実装構造そのものを仕様と比較しない。境界から観測可能なInterface、状態差、Triggerに対する結果、観測能力、作用能力、領域別制約だけを比較する。


class分割、関数名、framework、algorithm、thread、lock、ORM、SQL、内部wrapper等は、それ自体では違反にしない。仕様上の観測可能差を生む場合だけ対象にする。


### 6. 必要に応じてテストと実装を照合する


テストが仕様由来の期待値を実装へ正しく検査しているかを確認する。テストと実装が一致していても、両方が仕様から逸脱している場合は適合としない。


既存テストの実行は、証拠解消に必要で、かつside effectが合理的に小さい場合だけ行う。dependency追加、snapshot更新、code generation、formatterによる書換え等は行わない。


### 7. Evidence化する


findingには可能な限り `file:line`、symbol、section、schema path、test name等を付ける。


不在をfindingにする場合は、検索scope、pattern、関連artifactを示し、「未発見」と「存在しないことを確認した」を区別する。


## Non-CAT診断指数


`Non-CAT` は形式証明値ではなく、レビューした証拠に基づく**診断指数**である。0が検出された非適合なし、100が対象scopeにおけるCAT基準の広範な破綻を表す。


次の7 dimensionを使用する。


| Dimension | Weight |
| --- | ---: |
| Process boundary & PI | 15 |
| TCE behavior semantics | 20 |
| Closure & internal consistency | 15 |
| Process links & capabilities | 10 |
| Specification -> test semantic preservation | 15 |
| Specification -> implementation conformance | 20 |
| Traceability, domain rules & constraints | 5 |


各dimensionについて、十分な証拠がある場合のみ `r_i` を次から選ぶ。


- `0.00`: 検出された非適合なし。
- `0.25`: 局所的な曖昧さ・欠落・軽微な逸脱。中核意味は保存されている。
- `0.50`: 複数の欠落または部分的な意味喪失があり、到達可能なsliceへ影響する。
- `0.75`: 広い不整合、意味保存の破綻、または単独のCritical違反がdimensionへ影響する。
- `1.00`: dimensionの中核条件が成立しない、または複数のCritical違反で広範に破綻している。


適用対象外dimensionは `N/A`、証拠不足は `Unknown` とし、Non-CAT計算から除外する。


```text
Non-CAT = 100 * Σ(weight_i * r_i) / Σ(weight_i for assessed applicable dimensions)
```


小数は必要な精度で示す。整数へ丸める場合は、dimension表の値から再計算できるようにする。


### Review Coverage


Non-CATと別に `Review Coverage` を出す。


```text
Review Coverage = 100 * Σ(weight_i for assessed dimensions) / Σ(weight_i for applicable dimensions)
```


Coverageは「良さ」ではなく、判定できた範囲を表す。高いNon-CATと低いCoverage、低いNon-CATと低いCoverageを同じ意味に扱わない。


## 違反Severity


- `Critical`: 規範的仕様との直接矛盾、到達可能な中核振る舞いの仕様外結果、未宣言Interface、未宣言能力による振る舞い差、またはCATの正本関係を成立不能にする破綻。
- `Major`: 到達可能なCondition/Effect/接続の欠落、意味保存変換の明確な欠落、hidden state問題等、CAT適合性を実質的に損なうもの。
- `Minor`: 局所的曖昧さ、冗長・到達不能要素、由来不足等。現時点で規範的意味の直接矛盾までは確認できないもの。


推測だけの項目はSeverityを付けた違反にせず、`Suspected / Unknown` として分離する。


違反IDは内容に応じて次のprefixを使う。


- `NC-PROC-*`
- `NC-PI-*`
- `NC-TCE-*`
- `NC-CLOSE-*`
- `NC-LINK-*`
- `NC-CAP-*`
- `NC-TEST-*`
- `NC-IMPL-*`
- `NC-HSTATE-*`
- `NC-CONSTRAINT-*`


## CAT状態


総合判定はAccept/Rejectではなく `CAT状態` を一語で示す。


CATが十分に成立しているほど、実装という「容器」を交換しても仕様上の意味を保存しやすい。この交換可能性を、猫の流動性から固化までの物性になぞらえて表す。`CAT状態` はレビューUI上の補助ラベルであり、CAT理論上の形式的な状態分類ではない。


| 条件 | CAT状態 | 解釈 |
| --- | --- | --- |
| Non-CAT 0-5 | `液体` | 実装形態を変えても仕様上の同一性を高い確度で保存できる。 |
| Non-CAT 6-20 | `粘性` | 概ね交換可能だが、一部に実装依存または意味固定が残る。 |
| Non-CAT 21-40 | `ゲル` | 交換可能性は残るが、実装固有の形を相当に保持している。 |
| Non-CAT 41-70 | `半固体` | 仕様と実装の結合が強く、交換には意味の再構成が必要になる。 |
| Non-CAT 71-100 | `固体` | 実装構造がプロダクトの意味を大きく担い、CAT的交換可能性がほぼ成立しない。 |


ただし次を優先する。


- Review Coverageが70%未満、規範的仕様の所在が確定できない、未解決の規範競合がある、または未確認事項によって総合結論が反転し得る場合: `シュレディンガー`。
- confirmedなCritical違反が1件ある場合: score上の状態がそれより流動的でも最低 `半固体`。
- confirmedなCritical違反が複数ある、または主要Processの規範関係が広範に成立しない場合: `固体`。


`シュレディンガー` はNon-CATが高いことを意味しない。観測済みの証拠だけではCAT状態を確定できない、固化度とは直交した判定不能状態である。


`CAT状態` の値自体には説明文を混ぜず、一語だけを出す。理由は後続項目で示す。


## 出力形式


次の順序を基本とする。違反がないsectionは省略してよい。


```markdown
# CAT Conformance Review


CAT状態: ゲル
Non-CAT: 28/100
Review Coverage: 92%
Scope: <reviewed slice>
Normative basis: <CAT basis + product specification sources>


## Violations


### NC-TCE-001 — <short title>
Severity: Major
Affected: Specification -> Test
Evidence:
- path/to/spec.md:120-136
- path/to/test.ts:44-71
CAT rule: <violated rule>
Finding: <what is inconsistent or missing>
Conformance condition: <what condition would have to hold for this finding not to be a CAT violation>


## Dimension assessment


| Dimension | Weight | r_i | Status | Basis |
| --- | ---: | ---: | --- | --- |
| ... | ... | ... | ... | ... |


## Unknown / Not assessable


- <missing evidence or unresolved authority>


## Conforming observations


- <material CAT properties that were actually confirmed>
```


`Normative basis` には、本Skill内蔵基準を使った場合はその旨を明示し、外部CAT規範やプロダクト仕様を使った場合はその出典も示す。


## 証拠要件


各違反には可能な限り `file:line` または明確なsymbol/rangeを付ける。行番号を取得できないartifactでは、section、test name、symbol、schema path等で一意に参照する。


「存在しない」ことを違反証拠にする場合、検索したscope、pattern、関連artifactを示し、単なる見落としとの区別をつける。


`Conforming observations` は実際に確認できたCAT上重要な性質だけを書く。違反が少ないことを一般的な品質保証へ拡張しない。


## 禁止事項


- コードやテストを望ましい仕様の正本として扱わない。
- CATが要件の完全性まで保証すると主張しない。
- 有限個のテスト成功を実装の完全な正しさの証明としない。
- framework、design pattern、命名、folder構成等をCAT固有の要求として追加しない。
- 観測できない内部実装差を、仕様上の差異であるかのように扱わない。
- 証拠のない違反をNon-CATへ加点しない。
- 形式化されていないheuristic判断を形式証明として表現しない。
- 外部CAT理論文書が存在しないことを理由にレビュー不能としない。
- 特定projectのパスやartifact構成を、Skill利用の必須条件にしない。
- ユーザーが依頼していない修正実装、refactor、仕様変更を行わない。