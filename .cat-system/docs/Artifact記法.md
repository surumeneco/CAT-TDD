---
title: CAT Artifact形式契約
status: trial
version: '1.1'
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
  - Docs/Constraints/approved-requirements.md
decision_ref: user-decision-or-normative-url
refs:
  - xplay.spot.pi.input
base_revision: commit-or-revision-when-applicable
semantic_contract: markdown-v2
language: ja
---
~~~

`source_refs` は適用先プロジェクトが保持する出典参照であり、上例は利用側ワークスペース内の架空パスである。本パッケージに特定の私有ストレージへの接続を要求しない。実際の `confirmed` Source では、そのプロジェクトで検証可能な実在参照と承認根拠を指定する。

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

PresenceはCATとして有効な意味であり、Domainの`nullable`とは独立している。`optional` の欠落、`absent`、`undefined`、`null`、空文字列、0、falseを同一値に変換しない。

### 非required Presenceを条件で扱う機械的表現

入力Presenceは `required / optional / absent / undefined`、Domainの `nullable` は独立する。非required入力を読むConditionは、値の通常参照に暗黙の既定値を設定しない。

| 条件式 | 意味 |
| --- | --- |
| `is_missing(input.x)` | PI入力のキーが存在しない場合のみ真 |
| `is_undefined(input.x)` | PI入力が明示的なundefined状態の場合のみ真 |
| `is_present(input.x)` | キーが実在する値である場合のみ真。`null` も値として存在するため真 |

これらの関数には**直接のPI入力フィールド参照1個のみ**渡せる。Conditionは`and`/`or`を左から短絡評価するため、例えば `is_present(input.x) and input.x > 0` は値欠落時に通常参照を行わない。`is_missing`による欠落と`nullable`による`null`は別状態である。欠落/undefinedを通常演算で読む場合はClosureを`unproven`とし、TestModelの正本合格を認めない。

正規Compilerは、閉じた有限Domainの`optional`に欠落＋各値、`absent`に欠落のみ、`undefined`に明示undefinedのみ、`required`に各値を割り当てる。単一の受付Operationに対する操作別Presenceも適用する。受付Operationが曖昧な場合、出力のnonrequired Presence、無限・列挙上限超のDomain、nonrequired入力を直接読むEffectなどはまだ完全証明しない。

決定論的Vectorsでは欠落をキー省略、undefinedを `{"$cat_presence":"undefined"}` として区別する。undefinedをVitestで伝送する場合は、実装側のDriver Bindingに`undefined_transport: "js-undefined/v1"`を明示した場合だけ生成を許可する。生成されたテストはJSONの一時マーカーを**実際のJavaScript `undefined`**に変換してDriverへ渡し、Driverの`undefinedTransport`属性が同じプロトコルを申告することを実行時に確認する。未設定・別プロトコルはblockedを維持し、nullや通常値への置換を認めない。この契約は**Driverが実際に外部境界まで同値転送した証明ではなく**、正規の実テスト実行・Implementation Conformanceが別途必要。

PI全体の既定Presenceと操作別の例外を区別する場合、必要な行だけ`## 操作別存在`（英語:`## Operation presence`）に宣言する。

| 操作 | 項目 | 存在 |
| --- | --- | --- |
| save | 入力.x | 必須 |

操作IDと項目IDは同じPIに属していなければならず、重複した組を宣言してはならない。Compilerはこの表をTestModelの`operation_presence`へ出典PI付きで保存し、独立したModel Conformanceで照合する。

明示的なテストベクトルでは、受付操作を`operation`で特定し、任意項目の欠落は`input`のキーを省略し、`undefined`は`{"$cat_presence":"undefined"}`と表す。提供操作に応じた出力Presenceがある場合は、所有PIごとに一意に定まる全提供Operationを特定する。単一なら`output_operation`、異なる複数PIで当該Triggerに明示的に束縛される複数なら`output_operations`（重複なしのOperation ID配列）を使う。両者の同時指定、欠落・余剰・別Triggerの操作IDは拒否する。配列の順序は処理順を意味せず、決定論的selectorはIDをソートする。これらは値の同一性の規則であって、実装の動作確認結果ではない。

現行`rule-witness/v1`は非必須Presenceの全組合せを自動選択しない。対応不能な範囲は`BLOCKED / inconclusive`として残し、`draft / partial`を自動的にConfirmedへ昇格させない。単一の出力操作が明示されたVectorsは従来のDriver Binding `output_operation_transport: "js-driver-provide/v1"`を使用できる。生成VitestはDriverの`outputOperationTransport`と`triggerProvidedOperation(operationId, triggerId, input)`の実在を検証する。複数PIの出力を含む場合は`js-driver-provides/v1`を明示し、`triggerProvidedOperations(operationIds, triggerId, input)`で**1回の論理Trigger実行**からOperation ID→そのPIの観測出力項目record（全出力不在の場合も空record）の写像を受け取る。同Bindingでは単一提供操作も同じ写像で扱う。生成テストは全Operation IDの完全一致・各出力の所有PIを検査した後、一つの許容Outcomeとして全state/outputを照合する。操作毎の別実行・別Outcomeの結果の合成を認めない。このDriverはテストアダプターであり、製品の公開API・呼出方式・同期／非同期・出力順を指定するものではない。宣言がない・未知の方法・曖昧な提供操作はblockedを維持する。`undefined`入力も明示的な`js-undefined/v1` Bindingがなければ拒否する。**これらのBindingは検査可能なDriver契約であり、現実の外部送信や複数Processの相互作用の証明ではない。**補助Probeの成功は規範的なTCE vectors、Queue、実行テストの代替ではない。

複数の提供操作のうちどのOperationに紐付くかが決まらない場合、機械的に操作を選ばない。`## Operation presence`等で所有PIごとの提供Operationと`required`・`optional`・`absent`の全結果frameが局所証明された範囲に限り、決定論的Vectorsの出力操作を導出する。同一PI内の複数提供操作は下記の明示フレームがない限り未証明。未束縛の提供操作、`undefined`出力は未対応。JUnitのscalar transportは明示 `java-driver-provides/v1` により対応可能な値域で出力Operation identityを扱う。

### Outcomeごとの提供出力フレームと評価断面

同じPIで正常・例外等の提供Operationが排他的である場合、または提供Operationの送信と受信の評価Triggerが異なる場合に、`## 提供出力フレーム`（`## Output frames`）を明示できる。例（`request`は受付、`ok`・`fail`は同じPIの提供操作）:

| 起点 | 振る舞い | 結果 | 操作 | 活性 |
| --- | --- | --- | --- | --- | --- |
| lookup | found | 1 | ok | one |
| lookup | not-found | 1 | fail | one |

英語列は `Trigger / Behavior / Outcome / Operation / Mode`。Outcome番号はTCEの1始まりの番号。活性は `one`（必ず一つ）、`zero-or-one`（零または一つ）、`none`（非活性）。非活性は操作列を `—` とする。同じPI・Triggerでは同一Modeで全Behavior/Outcomeを一度ずつ宣言する。他PIの操作、受付操作、未宣言Trigger、重複・欠落、Modeに反する活性を拒否する。各提供操作は1個の出力評価Triggerに活性として現れ、宣言済み提供操作の入力評価Triggerも表の対象に含める。他のTriggerでは当該PIの提供出力は非活性。既存のOperation Triggerは受信項目を評価できる起点を保持し、送信項目の評価Triggerだけをこの表から導く。分割cutの送信引数を終端で再送しない。

操作別Presenceは活性な提供Operationの送信項目に適用し、非活性なPIの送信項目は不在を要求する。全結果に対して required 欠落、absent 出力、他PI/非活性の出力を検査する。この限定契約は同一PIで同時に複数の提供Operationを要求する世界や、同じOperationを複数の出力cutで活性化する世界を表す一般契約ではない。そのような表現は未対応として扱う。処理方式・時間順序・実配送・同じ要求の相関を証明するものではなく、PI/Trigger/Outcomeの仕様上の帰属を保存する。

`output_frames`を持つTestModelからは、Vectorの`output_operations`に選択Behaviorの全許容Outcomeで活性になり得る操作の和集合（空も可）を保持する。展開された各許容Outcomeには当該Outcomeの操作集合を保持する。生成テストは1回の実行で観測したOperation ID集合・所有PI・state/outputを同じ許容Outcomeへ照合する。未知・欠落・余剰・別Outcomeからの合成を拒否する。Vitestは`js-driver-provides/v1`、JUnitは`java-driver-provides/v1`の明示Bindingが必要。Driverに渡す操作ID集合は観測候補であって、実装への操作発動指示ではない。

### 必須input recordの型付きmember参照

`markdown-v2`のPI制約／TCE Condition・Effectでは、例えばPIが`input.request : record<id:string,expected_version:integer[1..]>`をrequiredで宣言した場合、`input.request.expected_version == state.version`や`input.request.id == state.target_id`と記述できる。既存の完全なField IDが一致する場合はそのFieldを優先する。そうでなければ、末尾の1要素を親recordの宣言済みrequired memberに束縛し、IRの`{"op":"member","args":[{"ref":"input.request"},{"literal":"expected_version"}]}`として保持する。Markdown TestModelでは`member[input.request, "expected_version"]`と表示する。親record自体とmemberのDomain・Presence、所有PI・当該受付Operationを元Sourceから独立に検査し、親の実値から読み取る。新しいPI Fieldやwire項目を追加する意味はない。

初期契約は一段のrequired・非nullable scalar member（boolean/integer/real/string/enum）と一意の受付Operationに限定する。未宣言member、非required親／member、Operation別の非required上書き、他PI入力、曖昧な操作、未解決型、型違いの比較、hidden DomainRule、複数段や提供応答の射影は拒否する。Effectの直接member参照は宣言Domain包含を独立検査する。比較式を許すことと全域証明・Effect全域証明は別であり、判定不能な式は閉包を証明しない。旧whole-recordの参照・型・wire表現は変更しない。

### 複数peerに対するOperationの明示対応

同一PIの`## 境界 / ## Boundary`に複数の相手Processを宣言する場合は、各`## 操作 / ## Operations`に`相手Process / Peer process`列を追加し、**固定Process IDまたは動的な`実行元Process`を明示**する。単一peerのPIでは従来どおり列を省略できる。`実行元Process`の機械表現は`@execution-origin`であり、特定のProcess IDではない。

~~~md
## 境界
| 相手Process | 方向 |
| --- | --- |
| xplay.launcher | 双方向 |
| xplay.command-source | 双方向 |

## 操作
| ID | 方向 | 起点 | 相手Process |
| --- | --- | --- | --- |
| startup_sync | 受付 | startup_sync | xplay.launcher |
| manual_sync | 受付 | manual_sync | xplay.command-source |
~~~

- CompilerはOperationとpeerの対応を出典PI付きIRへ保持し、TestModelのJSON・Markdown両方で独立照合する。静的な指定を全peerへ自動展開したり、別peerの同名Operationで代用したりしない。`実行元Process`はこの例外として明示的に宣言された場合だけ実行時に束縛する。
- 複数の静的Peerに対する対応先の未指定、境界外の固定peer、重複した境界peerは規範上の曖昧さとして拒否する。動的指定がなければ、旧単一peerの暗黙対応だけを維持する。合成では送受双方のPI／Operation／相手Processを同一接続ごとに検査し、一部のOperationが接続できても別Operationの接続証拠を代用しない。
- **動的相手の記法**：PIの`境界`行の相手、および`操作`行の相手として`実行元Process`（英語・内部表現は`@execution-origin`）を指定できる。境界に指定した場合、個々の開始元を事前に有限個列挙する必要はない。同じOperationに指定した場合、相手は各実行の開始Processに解決され、別実行の開始Processを代用しない。既知の静的Peer集合のPIでも、その集合内の実行元へ共通Operationを返す用途で動的指定が可能。静的に型が一致しただけでは配送先の実行時相関は証明できず、Compositionは`inconclusive`を保持する。提出Traceの実行IDとpeerの一致は形式整合性であり、実配送・Provider真正性・規範Gateの`passed`を保証しない。
- `xplay.command-source`のような論理actor識別子を、実在する独立サービスやHTTP境界として捏造しない。対象Processが組立て集合外なら外部境界として`inconclusive`を維持する。型付き接続が成立しても外部Effect/配送/時系列の証明とは別である。

**実行元を事前列挙しないPIの例**（受付・提供の双方で実行元を参照する場合）：

~~~md
## 境界
| 相手Process | 方向 |
| --- | --- |
| 実行元Process | 双方向 |

## 操作
| ID | 方向 | 起点 | 相手Process |
| --- | --- | --- | --- |
| request | 受付 | request | 実行元Process |
| reply | 提供 | — | 実行元Process |
~~~

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
| JSON構造値 | json | JSON値 |
| JSON属性object | json-object | JSONオブジェクト |
| 瞬間の抽象値 | instant | 瞬間値 |
| 文字列 | `string` | `文字列` |
| 安全な整数文字列 | `string<safe-signed-integer>` | `文字列<安全符号付き整数>` |
| 列挙 | `enum{draft, published}` | `列挙{下書き, 公開}` |
| 集合 | `set<string>` | `集合<文字列>` |
| 順序列 | `sequence<integer>` | `列<整数>` |

null / undefined / optionalの一般的な値意味を、コンパイラ都合で無理に別Domainへ縮約しない。Presenceまたは領域別仕様として意味を保持し、機械変換非対応ならその事実を明示する。

### JSON・時点の明示Domain

jsonは有限のJSON木、json-objectはそのobject根を表す。null、真偽、文字、有限数値、array順と文字列キーobjectを保持し、循環、undefined、非有限数値、非文字キーを拒否する。深度上限やbinary64上限を型の規範へ追加しない。名前付き型JSONを使用する場合も、DomainSpecの明示宣言が必要で、名前から自動推定しない。

instantは内部の厳密な瞬間carrierを表し、無制約stringや推測した日時精度ではない。明示codecの対象形式/暦範囲と抽象値域を区別し、各APIのwire形式・timezone・epoch単位を統一しない。サブmsの区別を内部で保持できても、既にJS Date等で失われた精度を復元したとはみなさない。

型付き値比較はsemantic_types.same_in_domain / compare_in_domain、ownerが選ぶ日時bindingはbind_in_domainで明示する。JSONではobjectキー順を無視、array順を保持し、数値1/1.0と0/-0を同値とするが真偽と数値は区別する。既存の型なしsameは変更しない。nullable/record/sequence/setと名前付き参照を辿り、曖昧なunion比較やbindingは推測せず拒否する。

semantic_json_instantは大整数/小数を保持するJSON解析・出力、明示offset/aware datetimeのcodecと型付き瞬間transportを提供する。codecの受理は製品入力の認可/書式許可ではない。データ形状以外のowner規則・Provider真正性は別に検証する。

JSON/instantは非有限Domainであり、代表値からfinite coverageを生成しない。現在の型なしAST比較/DomainRule呼出しとVitest rendererにはこれらの意味を暗黙接続せず、明示的な対応bindingがない経路はblockedを維持する。新Domainの登録・構造的包含・Model再生成成功は、自由文規則の意味同値やProcess Closureの合格ではない。

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
| レコード値 | `{"id": input.id, "name": ""}` | `{"id": 入力.ID, "name": ""}` |
| 列末尾追加 | `sequence_append(s, x)` | `列追加(s, x)` |
| 列位置交換 | `sequence_swap(s, i, j)` | `列交換(s, i, j)` |
| 列要素の項目更新 | `sequence_replace_member(s, i, "key", x)` | `列項目更新(s, i, "key", x)` |

レコード値のkeyは重複のない文字列literalとし、宣言済み閉じたrecordの必須・任意・不在・undefinedを区別する。値にliteral、直接参照等の仕様式を置ける。

列末尾追加は既存順序と全要素を保持し、要素xを末尾に1個追加する。列位置交換は0始まりの整数位置i,jが共に範囲内ならその2要素のみを交換し、どちらかが範囲外なら列全体を変更しない。同じ位置の交換も不変。列要素の項目更新は範囲内の位置iにあるrecordの宣言済み必須member一つのみを更新し、範囲外では不変。いずれも元の値を変更せず、新しい列値を表す。IDの一意性、採番、選択位置と業務IDの対応、追加上限等はこの演算の保証ではない。

相異なる2個の直接数値参照の和・差を整数定数と大小比較する限定断片では、受け取った有限の数値の正確な値を比較し、中間結果を浮動小数点に丸めない。一般の算術式や数値Effect値の評価とは区別し、型区別付き等値を大小比較の等値に読み替えない。閉包証明の適用範囲は機械的変換の `two-reference-linear-order-partition/v1` を参照する。

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

### nullable参照の等値Guard分割

`nullable-reference-equality-partition/v1` は同一の非null基底Domain（制約なしstringまたは同じ整数区間）のrequired参照とそのnullable参照の直接 `==` / `!=` に限定する。Boolean結合の下で、参照比較による連結成分ごとに最大5参照、少なくとも1つnullable参照を含む場合、全比較定数・null（nullableのみ）・参照数以下の相異なる非null代表を用いて全等値パターンを保存する。有限基底区間は実在値を超えて代表を作らない。nullableの単独参照と非null定数の比較も同じ分割で扱う（既存のnullのみの文字列分割は維持）。別連結成分は独立に分割し、通常の証明予算を適用する。これは任意のIDや改訂値の具体列挙ではない。optional/absent/undefinedとの混同、異種基底型間比較、順序・加工・非対応関数の混在はこのprofileでは証明しない。独立Source検査が同じ許容真理値類を再導出する。局所Guardの証明に限定し、観測元の真正性、Effectの全域適合、任意の外部作用、到達可能性を証明しない。

### CommonRule / DomainSpecで証明できる機械規則の限定語彙

任意の自然言語Ruleを機械証明へ変換しない。規範Artifactを正当にConfirmedにした上で、次の**完全一致の表現**だけを `cat:intrinsic-model/v1` の意味として扱う。これはあくまで**組み立て済みCATモデルに関する性質**であり、外部システムが実際に送信・反映・表示を行った証明ではない。

~~~md
## Rules
| ID | Condition | Requirement | Verification |
| --- | --- | --- | --- |
| declared.effects | assembled-process | @cat:effect-targets-declared/v1 | cat:intrinsic-model/v1 |
| declared.triggers | assembled-process | @cat:tce-triggers-declared/v1 | cat:intrinsic-model/v1 |
| resolved.domains | assembled-process | @cat:field-domains-resolved/v1 | cat:intrinsic-model/v1 |
| response.presence | fresh-output example.pi reply submit output.result | @cat:declared-outcome-output-presence/v1 | cat:intrinsic-model/v1 |
| state.agreement | initial-state-equality state.left state.right | @cat:all-trigger-state-equality-preservation/v1 | cat:intrinsic-model/v1 |
| state.invariant | initial-state-relation state.visible == (state.status == "published") | @cat:finite-state-guard-invariant/v1 | cat:intrinsic-model/v1 |
~~~

| Requirement | 厳密な判定対象 |
| --- | --- |
| `@cat:effect-targets-declared/v1` | 組み立て済みTCEの全Effect作用先がProcess/PIで宣言済みのstate/output/actionであること |
| `@cat:tce-triggers-declared/v1` | 組み立て済みTCEの全TriggerがProcessに宣言済みであること |
| `@cat:field-domains-resolved/v1` | 組み立て済みモデルの全フィールドDomainが再帰的に解決済みであること |
| `@cat:declared-outcome-output-presence/v1` | 指定の提供Operation・Triggerの全宣言Outcomeで、指定出力の値域および有効Presenceに反しないこと |
| `@cat:all-trigger-state-equality-preservation/v1` | 明示された初期状態の等値関係が全宣言Trigger・全許容Outcomeで帰納的に保存されること |
| `@cat:finite-state-guard-invariant/v1` | 明示された有限State初期関係の非空性と全宣言Outcomeでの帰納的保存に基づく有効Guard領域 |
| `@cat:trigger-observation-relation/v1` | 明示Triggerで利用可能な有限観測とStateの入力関係の非空性・全Stateへの射影 |
| `@cat:finite-transition-relation/v1` | 指定Operation・Trigger・peerにおける全許容Outcomeの有限射影と、明示したbefore/after関係の完全一致 |
| `@cat:observed-transition-relation/v1` | 同一実行の宣言済み取得観測を含む有限before/afterの許容結果関係の完全一致 |
| `@cat:finite-structural-transition-relation/v1` | 厳密に有限列挙できる型付き構造のbefore/after射影と全許容結果関係の完全一致 |
| `@cat:structural-copy-relation/v1` | 同一型のrequired構造値の任意長sequence/record・最上位setおよび最上位JSON/instantについて、全許容Outcomeの直接等値射影を象徴的に証明 |
| `@cat:collection-relation/v1` | 同一型のrequired record集合/列の条件選択、整数keyによる安定整列を全長で象徴的に証明 |

- 最初の3述語の `Condition` は **`assembled-process`**、`Verification` は **`cat:intrinsic-model/v1`**、`Requirement` は上表の対応する値と完全一致する必要がある。本文の自然言語要求や他のVerifier契約をこの文字列に置き換えて無断で意味変更してはならない。
- 出力Presence述語の `Condition` は厳密に `fresh-output <PI ID> <provide Operation ID> <Trigger ID> <output Field ID>` とする。これは当該応答の出力を各Outcome開始時に未生成とする明示的な規範宣言であり、永続状態・以前の応答・外部配信を初期化する意味ではない。所有PI内の提供Operationを一意に解決でき、所有PI・Trigger・Fieldが一致し、Domainが解決済みで、全宣言Outcomeについて代入が高々1回かつ型／値域証明済みである場合だけ証明する。Operation別Presence（なければ基本Presence）が required なら全Outcomeで代入、absent なら全Outcomeで非代入、optional なら両方を許す。undefined、曖昧な提供Operation、宣言Outcomeが空のものは未証明とする。非代入は当該fresh outputの不在に限り、外部送信・到達可能性・Guardの網羅性は別に検査する。
- 状態等値保存述語の `Condition` は厳密に `initial-state-equality <State ID> <State ID>` とする。これは規範上の初期状態を等値に限定する明示宣言であり、実装が初期化を行った証拠ではない。同一Processの相異なるStateで、同じboolean/integer/string/enum Domainを持つ2項に限定する。全宣言TriggerにOutcomeが存在し、各Outcomeについて型・値域証明済みの直接参照または定数を代入するか、非代入ならFrameでbefore値を維持し、両項のafter値がbefore等値の下で一致することを証明する。Effectの読取りは同時代入前の値であり、Guardによる例外・演算式による等値・未知の初期条件を推測しない。この証明をGuardの有効領域縮小には使用せず、実行相関・到達可能性・実Providerの検証とも分離する。
- 有効Guard領域述語の `Condition` は `initial-state-relation <CAT boolean expression>`。同一ProcessのConfirmed Domain Specificationから、参照がStateのみで有限直積4096組以下、関係を満たす初期状態が非空、全Outcomeの関連代入が型・値域証明済みで関係内のbefore値のみを参照し、全関係内状態で同時代入後も関係が成立する場合に限り有効領域を制限する。未代入StateはFrameに従う。Guardに依存した例外や未宣言初期条件を推測しない。Compilerと独立Source検査で再計算し、`guard_invariant_rule_ids` をCoverage証拠に記録する。選択・展開するVectorにも関係を適用する。初期化実装、任意の実行経路、外部観測の真正性は証明しない。複数の関係の共通領域が空ならClosureは未証明とする。
- 観測領域述語の `Condition` は `observation-relation <Trigger ID> <CAT boolean expression>`。同一ProcessのConfirmed Domain Specificationが、指定Triggerに明示的に `Available on` を持つ観測とStateのみを参照して有効な観測値領域を定義する。有限直積4096組以下で、同じTriggerの全宣言観測関係を結合しても、全State値組に対して少なくとも1つの観測値組が存在することをCompilerと独立検査で証明する。これにより実到達Stateを観測値の矛盾で勝手に排除しない。成立した関係だけ当該TriggerのGuard領域に適用し `observation_relation_rule_ids` を記録する。将来観測・時点未宣言・未知関係は利用しない。観測値の実Provider真正性や技術別観測Vector/Driverは別責務であり、この証明によるテスト生成の無断補完は禁止する。
- 有限遷移関係述語の `Condition` は `transition-relation <JSON object>`。必須キーは `trigger`, `pi`, `operation`（accept）, `peer`（固定相手）, `when`（CAT boolean式）, `fields`（after射影対象IDの配列）, `relation`（CAT boolean式）。outputを射影する場合に限り `provide`（同じPI・相手・Triggerの一意なprovide Operation ID）を追加する。`when` はbeforeのState/当該受付のrequired Inputのみ、`relation` はそれらに加えて `after.<field ID>` を参照できる。例：

~~~text
transition-relation {"trigger":"receive","pi":"example.pi","operation":"accept-request","peer":"example.client","when":"true","fields":["state.request"],"relation":"after.state.request == input.request"}
~~~

- 同一ProcessのConfirmed Domain Specification、boolean/enum/有限integerの完全なbefore×after領域、または制約なしstringのbefore/after最大5参照の厳密な等値類（直接等値・不等値、文字列定数、コピー代入に限定、全体で最大65536組）、有効PI制約・証明済み有限初期不変条件、型・値域証明済みEffectを前提に、指定 `when` の非空な各状態で一意なTCE Ruleの全Outcomeを同時代入・非代入Frameで計算し、`relation` が許容する全射影結果の集合と両方向に一致することを検査する。許容される値を1つだけ列挙すること、または過大なFrameで独立した作用まで禁止することは集合欠落として未証明となる。複数Triggerの相関は、明示State上の相関IDと順序を各Triggerの関係で保持する。実際の相関ID、実Provider、全実行の進行性・公平性、限定等値類以外の無界ID関係や未来観測は証明しない。独立Source検査が同じ関係を全域で再構成し、出典SHAとScopeが一致したときだけ正式Gateが受理する。対象を明示せず自由文や部分fixtureを渡す契約ではない。
- `@cat:observed-transition-relation/v1` は `observed-transition-relation <JSON object>` とし、上記有限遷移関係のキーに `observations`（参照するObservation IDの重複なし非空配列）を追加する。Observationはboolean/enumで、Processの `Available on` が当該Triggerのみ、`Source` が `same-execution-observation <JSON object>` であることを要求する。Source objectのキーは `trigger`, `pi`, `operation`, `peer`, `cut`（`trigger-entry`）, `source`（空でない意味上の観測元）。前4項は規範関係のScopeに一致させる。例：

~~~text
same-execution-observation {"trigger":"receive","pi":"example.pi","operation":"accept-request","peer":"example.client","cut":"trigger-entry","source":"declared-result"}
observed-transition-relation {"trigger":"receive","pi":"example.pi","operation":"accept-request","peer":"example.client","provide":"reply","when":"true","fields":["output.result"],"observations":["observation.received"],"relation":"after.output.result == observation.received"}
~~~

  当該Triggerに適用される証明済み観測領域・初期不変条件・有効PI制約と `when` の非空な共通領域で、全許容Outcomeと規範関係の双方向一致を厳密に検査する。未取得・未来・別実行・別受付・別peerを同じ値として補完しない。これは取得済み値の**仕様上の評価断面**を宣言する契約で、実Providerからの取得、同期的な呼出し、永続相関ID等を実装に要求または証明するものではない。
- `@cat:finite-structural-transition-relation/v1` は `finite-structural-transition-relation <JSON object>` とし、既存有限遷移関係のScope・Frame・required Presenceを維持した上で、既存型registryが完全列挙できるrecord/nullable/union/resolved reference/nullを認める。recordの不在とnullを区別し、項目順は意味上の差としない。既存のrequired scalar member記法を関係式中の `after.<field ID>.<member>` にも使用できる（Scope内のrequired after値のみ）。全record等値と、全required memberの等値を表す同値な関係は同じ許容結果集合で判定する。optional memberを省略した不完全な関係、未定義member、無限Domain、任意長sequence、未束縛型は証明しない。構造値のEffectは既存の型・値域証明を経る。
- `@cat:structural-copy-relation/v1` は `structural-copy-relation <JSON object>` とし、有限遷移関係と同じScopeキーを使用する。初期profileでは、固定peer・一意accept/provide・同一Trigger、解決済み同一Domainのrequired before/after、`when: "true"`、制約なしの1個の無条件Ruleと非空の全Outcomeを対象とする。`relation` は各対象afterとbeforeの直接等値（等式の左右は任意）の論理積で、各after対象が一意に定義されることを要求する。少なくとも1対象はsequence、record、最上位set、最上位JSON/instantであり、入れ子型のrecord Presence・nullable・boolean・integer・string・enum・null・解決済み参照を保持する。全Outcomeで型／値域証明済みの同一before参照か、Stateの明示された不変Frameを照合する。任意長sequenceの空列・順序・重複は値として保存し、有限長の列挙や入力同型のみで証明しない。最上位set（解決済み参照を含む）は既存要素型の集合等値（順序非依存、要素の欠落・余剰・重複を許さない）を保存する。最上位JSON（json/json-object）はkind別の構造等値（objectのkey順不問、array順・重複、数値同値、nullとmember不在の区別）、最上位instantは厳密な瞬間値の等値を保存する。入れ子set・構造型内のJSON/instant・未知型・条件付き／演算付き関係はこのprofileでは未証明とする。JSON変換・時刻順序・codecや製品実装の正しさをこの直接等値だけで証明しない。これは観測可能な値の関係であり、実装でのコピー関数、メモリ表現、同期方式を要求しない。Compilerと独立Source検査は各Outcomeから関係を再構成し、出典SHAを保持する。
- `@cat:collection-relation/v1` は `collection-relation <JSON object>` とし、直接等値と同じScope（単一対象、required同一Domain、無条件Rule、固定peer/操作）を使用する。`after.output.items == filter_by(input.items, "enabled", true)` は宣言済みrequired scalar memberと型適合定数の等値に合う全要素のみを保持し、列の相対順序と多重度、集合の要素同一性を保持する。`after.output.items == stable_sort_by(input.items, "id", "asc")` はrequired integer keyに対する非減少順の安定順列（同keyの相対順序保持）を表し、`"desc"` は非増加順を表す。全Outcomeの式が同じ関係を表す場合に限り証明し、欠落/余剰、別入力、誤Scopeを受理しない。任意述語・複合key・null順序・観測依存・別Domainへの写像は対象外。製品側の実装関数やアルゴリズムは規定しない。
- 上記の有限observed/structural profileは厳密な有限before×after領域（最大65536組）を対象にし、Compilerと独立Source検査がそれぞれ同じ規範関係を再構成する。有限性や証明予算は検査器の対応範囲であって、プロダクト仕様の値域を狭める要件ではない。実装の関数・class・SQL/ORM・同期方式・データ配置は、明示された仕様上の差や実装制約がない限り検証条件にしない。証明できないものは未証明とし、意味を保存する別の健全な証明方式を排除しない。既存有限遷移関係v1の記法・意味は維持する。
- 正当にConfirmedとなった規範Artifactの出典ID・SHA-256と決定根拠が揃い、モデル条件が実証された場合だけ、Compilerが `intrinsic_rule_proofs` を生成する。独立 `model-conformance` は元Artifactから同じ性質を再検査し、結果・出典を比較する。
- 未承認Artifact、未知の述語、条件の変更、自由記述、外部通信・DOM・データベース・Discord送信等の実装・複数実行に関するRuleは**未証明**である。登録済みfixtureやrunnerの単なる `passed` を自然言語要求の証明に代用しない。
- この限定語彙を超える意味は、別の規範上の意味定義・Verifierの責任範囲・正当な承認と結合した機械証明手段が成立するまで `inconclusive/blocked` のまま扱う。


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

### Record内部のPresence記法

構造Recordのフィールドでは、名前の直後に `[optional]`、`[absent]`、`[undefined]` を明示できる。指定しない場合のPresenceは `required`。外側のPIフィールドPresenceと内側のRecordフィールドPresenceは別々に保持する。

~~~text
レコード<name:文字列,note[optional]:文字列またはnull>
record<id:integer,note[optional]:nullable<string>>
record<x[absent]:boolean,y[undefined]:boolean>
~~~

`note[optional]` はキー欠落を許すが、明示nullを許すかどうかは記述されたDomainで決まる。`[absent]` はキーの不在のみ、`[undefined]` は明示的な未定義状態のみを許す。異なるPresence属性で同一名を2回宣言することも重複として拒否する。ParserはRecord内部のPresenceを型付きIRに保持し、Markdown formatterは同属性を再出力する。JSONでの未定義値のwire符号化や実装テストのtransport証明をこの構文だけで完了とみなさない。 有限Domainとして列挙できるRecordでは、`required`は各Domainの値、`optional`はキー欠落と各Domainの値、`absent`はキー欠落のみを組み合わせる（入れ子Recordも同じ）。有限積が上限を超える場合や要素Domainが無限の場合は列挙せずinconclusiveとし、`undefined`のRecord内部値はJSON標準の値として偽装せず、明示的なtransportがない限り有限列挙を行わない。
### 汎用型参照（明示的に定義されたDomainへの参照）

`型参照<UUID>` / `ref<UUID>` はRecord型への決め打ちではなく、DomainSpecの `## 型定義 / ## Types` 内に同名で宣言されたDomainを引用する**汎用型参照**である。型本体を創作せず、同名の実定義がないときは `resolved: false` を保持して規範完了に進めない。

`null` / `明示null` は値域が `{null}` の**単一null Domain**である。`nullable<T>` はnullとTの値域を結合するが、`null`は他の通常値を一切許可しない。いずれもフィールドPresenceの`absent`（キー欠落）や`undefined`（未定義）と混同しない。`型参照<明示null>`はこのDomainを自動確定せず、正式なDomainSpecの`## Types`で同名を`null`として明示宣言した場合のみ解決する。有限列挙は`null`に対してちょうど1値であり、`nullable<null>`にも二重のnullを発生させない。

~~~md
## Types
| ID | Domain |
| --- | --- |
| UUID | string |
| Edition | enum{JE,BE} |
| Identity | record<edition:型参照<Edition>,username:string> |
~~~

ここで `UUID | string` は**宣言された型が文字列である**という構造上の契約に過ぎず、UUIDの妥当な形式、値の同一性、認可条件やwire表現を保証しない。そのような追加制約は独立した規範RuleやDomainSpecへ明記・証明する必要がある。`型参照<UUID>` のような曖昧な既存仕様を、**自動で** `string` に置き換えてはならない。

Resolverは参照先の構造・宣言Artifact ID・SHA-256を型付きIRへ保持し、独立Model Conformanceでソースから照合する。Unknown/循環参照/宣言重複を証明済みとして扱わない。既存の `record<Name>` 記法は引き続き **Recordの形状のみ**参照可能であり、一般の `型参照<Name>` と混同しない。
### DomainSpec の名前付き構造Domain（宣言のある場合のみ）

DomainSpecでは既存の `## 規則 / ## Rules` に加え、構造Domainを名前で参照するため、`## 型定義 / ## Types` を使用できる。型宣言だけのDomainSpecも有効である。既存の規則のみのDomainSpecとCommonRuleの解釈は変えない。

~~~md
## Types
| ID | Domain |
| --- | --- |
| User | record<name:string,active:boolean> |
| Change | record<owner:record<User>,mode:nullable<enum{A,B}>> |
~~~

- PI/ProcessのDomain欄では `record<Change>`（日本語なら`レコード<Change>`）と参照する。定義の本体は同じProcess、または適用可能な祖先スコープのDomainSpecに置き、実際のCompiler呼出しへ明示的に `--domain-spec` を渡す。
- Resolverは**明示的なDomainSpec内の構造定義だけ**を使用する。未定義の名前からフィールドを推測しない。型名重複、循環する型定義、構造として解決できない宣言はエラーまたは未解決としてfail closedとする。
- 変換後のJSON TestModelには、各参照の実際のフィールド構造と、出典Artifact ID、出典SHA-256を保存する。JSONに対する独立 `model-conformance` はこれらをソースから再解決して比較する。
- 現時点のMarkdown TestModel rendererは型定義の詳細構造・出典を完全表現しないため、**名前付き構造型があるときのMarkdown Model Conformanceを合格証拠としない**。JSONの正式比較を使用する。
- 型定義はデータ構造の形だけを決める。RuleのVerification（自然言語）を機械的にprovedにしたり、非有限ConditionのProcess Closureを自動証明するものではない。
- 構造定義はプロダクト固有の規範入力であるため、そのDomainSpecを `confirmed` に昇格するには通常どおり正当な `decision_ref` が必要である。型宣言があるだけで未承認のプロダクト仕様はconfirmedとならない。

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

決定論的コンパイルを使用するWorkだけ `Compilation / 変換` を追加する。TCEセルは`;`区切りで同一Processの複数confirmed TCEを列挙でき、closure/model生成ではassembled specificationとして扱う。`Conformance binding / 適合接続`は技術固有Inspectorが実装境界を仕様IDへ結び付ける機械設定であり、仕様そのものではない。 `Technology constraints / 技術制約接続` は採用済みのコンパイラ等の実装制約の検査設定への参照であり、PI適合証明とは独立する。 `Runtime constraints / 実行基盤制約接続` は採用済みNode/NestJS/PostgreSQLの限定された実runtime検査Bindingを参照する。 `Runtime boundary binding / 実境界接続` は、実装の両端を起動して実データを観測する限定profileのBindingを参照する。`cat-runtime-boundary-binding/v1` の適用条件・実行証拠・非保証範囲は機械的変換の「実境界の独立観測」を参照する。仕様上の通信方式を追加するものではない。

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

内部IR、TestModel JSON、vectors、binding、execution evidenceは機械用派生物としてJSON等を使用できる。これらを人間向け意味正本へ昇格させない。normative vectorsは`cat_compile_v2.py vectors`のtest-selection ruleから生成される派生物であり、人間やAIが必要ケースを直接追記するTest Listとして扱わない。


### Test Suite Manifest（spec-test-sync）

既存実装向けの規範テスト整備は`flow: spec-test-sync`、`work_kind: test-maintenance`のWorkで実施する。WorkのCompilationにはConfirmed Process / PI / TCE / TestModel / Vectors / 技術Bindingを指定し、TDD Queueは指定・作成しない。Process ClosureとModel ConformanceのScript-owned passed evidenceが必要である。TDDの`current=1`制限はspec-implementationにだけ適用する。

`cat-test-suite-manifest/v1`は同期した生成物の管理用Lifecycleメタデータであり、第二の仕様書ではない。`inputs`はsource/model/vectors/renderer/bindingのhashとselection rule・repo revisionを保持する。`entries`は生成相対パスをキーとしてtest ID、generated/handwritten所有者、ファイル内容SHA-256、由来hash群を保持する。TCEのCondition、Oracle、Expected Result等の意味を書き込まない。既存手書きテストとproduction sourceは不変、未選択の旧生成テストは自動削除しない。

同期結果`test-suite-synced`、試験実行結果`test-execution-passed / failed / not-run`、CAT適合性Gateの証拠は相互に代用しない。詳細は[機械的変換](機械的変換.md)を参照する。

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

Queue itemにScenario、Expected Result、Oracle、Condition、Effect、input/output値を記述してはならない。`pending / current / done / blocked`の遷移はQueue State Managerが機械的に行い、`current`は最大1件とする。done化にはcurrent item IDとQueue hashへ結び付いたpassed Green evidenceを必須とし、古いGreen証拠や別itemの証拠では遷移できない。実行可能testはcurrent itemだけから生成する。

### Implementation obligations

`cat-implementation-obligations/v1`は実装適合性GateのLifecycle/Evidence Artifactである。categoryは `interface / capability / behavior / invariant / cross-process / domain / implementation-constraint` を使用する。各obligationは少なくとも `category / source_ref / method / status / limitation` を持ち、`passed / failed` は具体的な `evidence`、`inconclusive / not-run` は `reason` を持つ。normative Gateでは骨格をconfirmed sourceから再生成して完全一致を確認してから、Script/Provider evidenceで評価する。Green/CIの結果だけを全categoryへ複製しない。

## 14. Candidate・Gate

Candidateは `Observation / Source / Proposed semantics / Unknown / Status` を基本項目とする。Gateは `stage / input revision / checks / executed command / exit code / evidence / verdict / not-run` を基本項目とする。

これらはLifecycle/Evidence側であり、観測されたコード・テスト結果を自動的にSemantic Artifactへ昇格させない。

## 15. 後方互換と移行

- `machine-only`: legacy互換入力。
- `markdown-v1`: 旧人間可読形式。`Rules / Effects`、PI内state等を互換読取する。
- `markdown-v2`: 新規標準。

一回の決定論的compileではsemantic contractを混在させない。新規Artifact・fixture・例はv2を使用する。

コンパイラ非対応の意味要素は、別の意味へ縮約して通さない。Artifactとして保持したまま `unsupported / BLOCKED` とし、production TestModelをAIで作成・補正しない。とくにCommonRule / DomainSpecをWorkが宣言しているのに現在のnormative compiler / deterministic verifierへ写像されていない場合、そのWorkのnormative compileとCAT適合性Gateを停止する。Compiler / schema改善Work、または仕様上定義された領域別検証へ分離する。

## 16. confirmed昇格

Candidate / Draftからconfirmedへの昇格はReview本文の編集ではない。明示されたnormative decisionを入力とする専用authority executorが、既存Artifactの意味本文を変えずにconfirmed配置へ移動し、`status: confirmed`と`decision_ref`を設定する。ReviewerやDesignerはこのpromotion権限を持たない。
