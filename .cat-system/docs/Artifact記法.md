---
title: CAT Artifact形式契約
status: trial
version: '1.0'
---

# CAT Artifact記法

## 1. 基本原則

CATの人間向け正本はMarkdownとする。新規の意味Artifactは `semantic_contract: markdown-v2` を使用し、Process / PI / TCE / CommonRule / DomainRule / DomainSpecを、人間が振る舞いと境界を直接読める形で記述する。

機械処理ではMarkdownを `cat-machine/v2` 相当の型付きIRへ正規化してよい。IRはコンパイラ内部・cache・debug用の派生物であり、意味の正本ではない。同じ意味をMarkdownとJSONへ二重入力しない。

旧 `semantic_contract: markdown-v1` と `machine-only` は互換入力として読み込めるが、新規作成の標準ではない。

### Artifactの二群

**Semantic Artifacts**はプロダクトの意味を保持する。

- `process`
- `pi`
- `tce`
- `common-rule`
- `domain-rule`
- `domain-spec`
- `test-model`

**Lifecycle / Evidence Artifacts**は開発作業・証拠を保持する。

- `candidate`
- `work`
- `gate`
- vectors / binding / execution evidence

Git branch、JUnit、command、framework等は後者に置いてよいが、Process / PI / TCEの意味定義へ混入させない。

## 2. 共通front matter

front matterは識別・索引・出典用の小さな機械メタデータに限定する。keyはtooling互換のため英語固定とする。本文は `language` に応じた日本語/英語表記を使用できる。

~~~yaml
---
cat_version: '0.3'
kind: tce
id: xplay.spot.save
status: confirmed
process: xplay.spot
source_refs:
  - https://drive.google.com/file/d/EXACT_ID/view
decision_ref: user-decision-or-normative-url
refs:
  - xplay.spot.pi.input
base_revision: commit-or-revision-when-applicable
semantic_contract: markdown-v2
language: ja
---
~~~

`language` は `ja / en`。`confirmed`では `decision_ref` を必須とする。Artifact ID / Process IDは参照安定性のためASCII安定IDを推奨する。一方、本文中のTrigger、field、state、observation、action、DomainRule parameter等はPython identifier互換のUnicode識別子と `.` による階層表現を使用できる。

## 3. 多言語表記

`markdown-v2`では少なくとも日本語と英語の次の見出しを同義として扱う。

| English | 日本語 |
| --- | --- |
| Contract | 契約 |
| Interfaces | 境界 |
| State | 仕様状態 |
| Observations | 観測能力 |
| Actions | 作用能力 |
| Triggers | 起点 |
| Boundary | 境界 |
| Fields | 項目 |
| Operations | 操作 |
| Constraints | 制約 |
| Behaviors | 振る舞い |
| Definitions | 定義 |
| Evidence | 証拠 |
| Scope | 範囲 |
| Technologies | 技術 |
| Repositories | リポジトリ |
| Checks | 検査 |
| Gates | ゲート |
| Compilation | 変換 |

日本語と英語は別仕様ではなく、同じ内部IRへ正規化される表示aliasである。

## 4. Process

Processは実装componentではなく、仕様上区別するブラックボックス境界である。`markdown-v2`では、境界、内部仕様状態、観測能力、作用能力、Triggerを第一級構文で宣言する。

~~~md
# Process: xplay.spot

## 契約
閉世界: 真

## 境界
| PI |
| --- |
| xplay.spot.pi.input |

## 仕様状態
| ID | Domain |
| --- | --- |
| 状態.保留 | 真偽 |

## 観測能力
| ID | 情報源 | Domain |
| --- | --- | --- |
| 観測.現在時刻 | システム時刻 | 整数[0..] |

## 作用能力
| ID | 対象 | Domain |
| --- | --- | --- |
| 作用.監査通知 | 監査通知先 | 真偽 |

## 起点
| ID | 由来 |
| --- | --- |
| 保存要求 | xplay.spot.pi.input/save |
~~~

### 意味

- `境界 / Interfaces`: このProcessに接続するPI Artifact ID。
- `仕様状態 / State`: 後続の振る舞いを変える内部仕様状態。実装上の一時変数は置かない。
- `観測能力 / Observations`: PI入力・仕様状態以外にConditionが読める仕様上の情報源。
- `作用能力 / Actions`: PI出力・仕様状態更新以外にEffectとして保証できる外部作用。
- `起点 / Triggers`: TCEを評価する起点。

PIの受信項目・Processの仕様状態・明示観測能力が、Conditionから参照可能な集合を構成する。PIの送信項目・仕様状態・明示作用能力が、Effectの作用可能集合を構成する。

## 5. PI

PIはProcess間の境界状態空間であり、実装上の型定義そのものではない。Process内部状態をPIへ混ぜない。

~~~md
# PI: xplay.spot.pi.input

## 境界
| 相手Process | 方向 |
| --- | --- |
| xplay.user | 双方向 |

## 項目
| ID | 方向 | Domain | 存在 |
| --- | --- | --- | --- |
| 入力.x | 受信 | 文字列<安全符号付き整数> | 必須 |
| 入力.z | 受信 | 文字列<安全符号付き整数> | 必須 |
| 出力.x | 送信 | 整数 | 必須 |
| 出力.z | 送信 | 整数 | 必須 |

## 操作
| ID | 方向 | 起点 |
| --- | --- | --- |
| save | 受付 | 保存要求 |

## 制約
| 式 |
| --- |
| `入力.x != "" または 入力.z != ""` |
~~~

### 境界方向

| English | 日本語 | 意味 |
| --- | --- | --- |
| receive | 受信 | 相手からProcessへ入る境界 |
| send | 送信 | Processから相手へ出る境界 |
| bidirectional | 双方向 | PI全体が双方向 |

### 項目Presence

| English | 日本語 |
| --- | --- |
| required | 必須 |
| optional | 任意 |
| absent | 不在 |
| undefined | 未定義 |

PresenceはCATとして有効な意味である。現行決定論コンパイラが扱えないPresenceを、別Domainへ縮約して通してはならない。production TestModel生成では `BLOCKED / unsupported` とし、Compiler / schema改善Workへ分離する。AIがproduction oracleへ補完しない。

### 操作方向

| English | 日本語 |
| --- | --- |
| accept | 受付 |
| provide | 提供 |

受付操作がTCEの起点になる場合はTrigger IDを明示する。

## 6. Domain記法

| 種別 | English | 日本語 |
| --- | --- | --- |
| 真偽値 | `boolean` | `真偽` |
| 整数 | `integer`, `integer[0..100]` | `整数`, `整数[0..100]` |
| 文字列 | `string` | `文字列` |
| 安全な整数文字列 | `string<safe-signed-integer>` | `文字列<安全符号付き整数>` |
| 列挙 | `enum{draft, published}` | `列挙{下書き, 公開}` |
| 集合 | `set<string>` | `集合<文字列>` |
| 順序列 | `sequence<integer>` | `列<整数>` |

null / undefined / optionalの一般的な値意味を、コンパイラ都合で無理に別Domainへ縮約しない。Presenceまたは領域別仕様として意味を保持し、機械変換非対応ならその事実を明示する。

## 7. TCE

人間向け正本では、Trigger → Condition → Effectを**振る舞い単位**で同じ行に置く。旧 `Rules / Effects` の二表分割は `markdown-v1` の互換入力に限る。

~~~md
# TCE: xplay.spot.save

網羅要求: closed

## 振る舞い
| ID | 起点 | 条件 | 結果 | 効果 |
| --- | --- | --- | ---: | --- |
| save.valid | 保存要求 | `入力.x != "" かつ 入力.z != ""` | 1 | `出力.x = 整数化(入力.x); 出力.z = 整数化(入力.z); 状態.保留 = 偽` |
| save.invalid | 保存要求 | `入力.x == "" または 入力.z == ""` | 1 | `状態.保留 = 真` |
~~~

`結果 / Outcome`は同一Conditionに複数の許容結果がある場合に番号を分ける。同じOutcome内のEffectsは同時に成立する。

Effectの `target = expression` は命令ではない。左辺が最終的に成立すべき仕様状態・境界出力・外部作用、右辺がその値または関係である。SQL、Repository呼出し、COMMIT、HTTP client等の実装手順を書かない。

書き込まれない宣言済みstateはTestModelで `unchanged`、書き込まれないoutput/actionは不在として導出する。

### 網羅要求と網羅検証を分ける

`網羅要求 / Coverage requirement` は仕様側の要求である。

- `closed`: 到達可能なTrigger/状態領域を仕様が閉じることを要求する。
- `partial`: 意図的に部分仕様として扱う。

`closed`と書くだけで閉包済みにはならない。機械判定可能ならTestModel生成時に `proved / uncovered / unproven` を導出する。一般Condition等で証明できない場合は `unproven` のままとする。`--allow-draft`を明示した調査用変換では未証明状態を保持した`draft` TestModelを生成できるが、normative compileでは全Triggerが`proved`でなければ停止する。必要なら独立レビュー証拠へ接続し、TCE正本へ「検証済み」として逆流させない。

## 8. 式記法

式は任意コードではなく、限定された仕様式である。日本語/英語aliasは同じASTへ正規化する。

| 分類 | English | 日本語例 |
| --- | --- | --- |
| literal | `true`, `false`, `null` | `真`, `偽`, `なし` |
| 論理積 | `a and b` | `a かつ b` |
| 論理和 | `a or b` | `a または b` |
| 否定 | `not(x)` / `not x` | `否定(x)` |
| 比較 | `==`, `!=`, `<`, `<=`, `>`, `>=` | 同左 |
| 算術 | `+`, `-`, `*`, `/` | 同左 |
| 長さ | `length(x)` | `長さ(x)` |
| 整数化 | `to_int(x)` | `整数化(x)` |
| 連結 | `concat(a, b)` | `連結(a, b)` |
| 集合追加 | `set_add(s, x)` | `集合追加(s, x)` |
| 集合削除 | `set_remove(s, x)` | `集合削除(s, x)` |

文字列literal内の日本語をkeyword変換しない。式はPython風の外観を利用してもPythonコードとして実行しない。

## 9. Domain Rule

式として再利用できる領域規則を定義する。

~~~md
# Domain Rule: xplay.rectangle

## 定義
| ID | 引数 | 式 |
| --- | --- | --- |
| 長方面積 | 幅, 奥行 | `幅 * 奥行` |
~~~

DomainRuleは式関数であり、DOM、視覚、統計、複数実行間の関係等を無理に押し込まない。

## 10. Common Rule

`kind: common-rule` は複数PI/TCEへ横断適用される**プロダクト固有**の共通規則を保持する。CAT理論そのもののClosed-world規則を各プロジェクトへ複製しない。

~~~md
## 規則
| ID | 適用対象 | 要求 | 検証 |
| --- | --- | --- | --- |
| ownership.visible | xplay.asset.* | 所有者変更後は全参照境界で同じ所有者が観測される | integration model |
~~~

`Verification`はその規則をどのTestModel・静的検査・領域別検証へ接続するかを示す。

## 11. Domain Specification

`kind: domain-spec` はPI/TCE単体では自然に保持しにくいが、プロダクト適合判定には必要な構造・複数実行関係を保持する。

~~~md
## 対象
| Ref | Aspect |
| --- | --- |
| xplay.notice.form | accessibility |

## 規則
| ID | 条件 | 要求 | 検証 |
| --- | --- | --- | --- |
| label.link | form表示時 | 各入力は意味上のlabelと対応する | accessibility tree |
~~~

対象例はDOM構造、視覚、accessibility、統計的性質、複数実行間の関係等。単にTCEへ書きにくい内容を未定義のまま置く分類ではなく、対象・要求・検証方法を持つ。

## 12. Issue / Task / Work

Issue / Task / Workは開発Lifecycleを段階的に具体化するArtifactである。通常運用では**人間が直接入力する開発要求の単位はIssue**とし、人間にTaskやWorkの手作成を要求しない。

- `Issue`: 人間が要求・問題・目的・観測可能な完了条件・対象外・未決定事項を記述する入口。CAT/TDDの用語やProcess分割を知らなくても記述できることを前提とする。
- `Task`: AIの`cycle-scope-divider`がIssueをProcess責務ごとに分解した単位。Process境界と子Workの依存関係を保持する。
- `Work`: AIの`cycle-scope-divider`がTaskを、単独で仕様化・検証できる仕様差分へ分解した実行単位。人間可読なMarkdownであることは、人間による手作成を要求するという意味ではない。

意味上の選択肢が複数ありIssueだけから確定できない場合、AIはその意味を補完せず、該当Task/Workを停止して人間へ判断を返す。Issue→Task→Workの構造化自体はAIの責務であり、人間の意味決定責務とは区別する。

### Work

WorkはSemantic ArtifactではなくLifecycle Artifactである。`Work.md`のfront matterと表を `cat_flow.py` が内部 `cat-work/v1`へ正規化する。front matterは `flow / work_kind / parent / depends_on` を持ち、独立flowとscope graphを明示する。Git、repository、runner、command、JUnit等はここに存在してよい。`cat_flow.py`は作成済みWorkを機械処理するもので、Issue→Task→Workの意味的分解は行わない。

WorkのLifecycle進捗は`Lifecycle/Works/{New,InProgress,Blocked,Completed,Cancelled}/<work>/`という**配置**で表す。同じ情報を`lifecycle_status`としてfront matterへ重複させない。front matterの`status`や`spec_status`はLifecycleフォルダの代替ではない。Work状態を変えるときはWorkディレクトリ全体を移動し、`@work/`相対参照を維持する。

本文の日本語/英語見出し・列名は同義として読める。front matter keyと内部schemaは機械互換のため英語固定とする。

~~~md
---
kind: work
id: notice.publish
entry: confirmed-spec
mode: implementation
flow: spec-implementation
work_kind: implementation
parent: ''
depends_on: []
---

# Work: notice.publish

## 証拠
| 参照 |
| --- |
| repo/path@commit |

## 範囲
| プロセスID | 変更ID | 保持ID |
| --- | --- | --- |
| notice | notice.publish.tce | notice.publish.pi |

## 技術
| 技術 |
| --- |
| TypeScript |
| Vitest |

## ゲート
| ゲート | 状態 | 証拠 |
| --- | --- | --- |
| process-closure | 成功 | validator:process-closure |
| model-conformance | 成功 | validator:model-conformance |
| implementation-conformance | 未実行 | — |
| semantic-review | 成功 | decision:https://example.invalid/decision/123 |
| test-oracle-review | 成功 | review:oracle-42 |
| red-review | 成功 | review:red-17 |
| ci | 対象外 | CI未採用 |
| real-use | 成功 | manual-check:2026-10-05 |
~~~

Gate statusの日本語aliasは `成功 / 対象外 / 未実行 / 停止 / 不確定`。内部では `passed / not-applicable / not-run / blocked / inconclusive`へ正規化する。CAT適合性3 Gateの最終状態はScript所有の `.cat-flow/conformance/` 証拠を基準とし、Work表の `passed` だけでは成立しない。機械判定が `inconclusive` の場合に限り、独立Review evidenceで閉じることができる。

### Compilation

決定論的コンパイルを使用するWorkだけ `Compilation / 変換` を追加する。TCEセルは`;`区切りで同一Processの複数confirmed TCEを列挙でき、closure/model生成ではassembled specificationとして扱う。`Conformance binding / 適合接続`は技術固有Inspectorが実装境界を仕様IDへ結び付ける機械設定であり、仕様そのものではない。

~~~md
## 変換
| プロセス | PI | TCE | DomainRule | モデル | 具体値 | キュー | 接続 | テスト | 適合義務 | Draft許可 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| @work/CAT/Process.md | @work/CAT/PI.md | @work/CAT/TCE.md | — | @work/TestModel.md | @work/vectors.json | @work/TDD/Queue.json | @work/binding.json | @work/generated/current.test.ts | @work/implementation-obligations.json | 偽 |
~~~

無印相対パスと `@work/` はWorkディレクトリ、`@workspace/` はworkspace、`@repo:<name>/` は宣言repo、`@package/` はCAT packageを境界とする。絶対パスと `..` 脱出は禁止する。

## 13. TestModelと機械用派生物

TestModelはSemantic Artifactから導出される人間向けMarkdownである。`language: ja` の入力からは日本語見出しを生成できる。

TestModelでは次を明確に分ける。

- Coverage requirement: TCEが要求した `closed / partial`。
- Coverage verification: `proved / uncovered / unproven` 等の検査結果。

内部IR、TestModel JSON、vectors、binding、execution evidenceは機械用派生物としてJSON等を使用できる。これらを人間向け意味正本へ昇格させない。

### TDD Execution Queue

QueueはTestModelから導出されたテスト実行順と進捗だけを保持するLifecycle Artifactであり、第二の仕様書ではない。

~~~json
{
  "schema": "cat-tdd-queue/v1",
  "process": "notice",
  "model_sha256": "...",
  "vectors_sha256": "...",
  "items": [
    {
      "id": "notice.valid",
      "model_ref": "notice.publish.valid",
      "vector_ref": "notice.valid",
      "order": 1,
      "status": "current",
      "evidence_ref": null
    }
  ]
}
~~~

Queue itemにScenario、Expected Result、Oracle、Condition、Effect、input/output値を記述してはならない。`pending / current / done / blocked`の遷移はQueue State Managerが機械的に行い、`current`は最大1件とする。実行可能testはcurrent itemだけから生成する。

### Implementation obligations

`cat-implementation-obligations/v1`は実装適合性GateのLifecycle/Evidence Artifactである。categoryは `interface / capability / behavior / invariant / cross-process / domain / implementation-constraint` を使用する。各obligationは少なくとも `category / source_ref / method / status` を持ち、`passed / failed` は具体的な `evidence`、`inconclusive / not-run` は `reason` を持つ。Green/CIの結果だけを全categoryへ複製しない。

## 14. Candidate・Gate

Candidateは `Observation / Source / Proposed semantics / Unknown / Status` を基本項目とする。Gateは `stage / input revision / checks / executed command / exit code / evidence / verdict / not-run` を基本項目とする。

これらはLifecycle/Evidence側であり、観測されたコード・テスト結果を自動的にSemantic Artifactへ昇格させない。

## 15. 後方互換と移行

- `machine-only`: legacy互換入力。
- `markdown-v1`: 旧人間可読形式。`Rules / Effects`、PI内state等を互換読取する。
- `markdown-v2`: 新規標準。

一回の決定論的compileではsemantic contractを混在させない。新規Artifact・fixture・例はv2を使用する。

コンパイラ非対応の意味要素は、別の意味へ縮約して通さない。Artifactとして保持したまま `unsupported / BLOCKED` とし、production TestModelをAIで作成・補正しない。とくにCommonRule / DomainSpecをWorkが宣言しているのに現在のnormative compiler / deterministic verifierへ写像されていない場合、そのWorkのnormative compileとCAT適合性Gateを停止する。Compiler / schema改善Work、または仕様上定義された領域別検証へ分離する。
