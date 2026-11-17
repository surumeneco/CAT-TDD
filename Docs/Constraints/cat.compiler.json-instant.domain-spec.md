---
cat_version: '0.3'
kind: domain-spec
id: cat.compiler.json-instant
status: confirmed
process: cat.compiler
source_refs:
  - https://github.com/surumeneco/CAT-TDD/pull/86
decision_ref: Docs/Decisions/CAT31-json-instant-approval-20261118.md
refs: []
semantic_contract: markdown-v2
language: ja
---

# CAT-TDD Compiler：JSON構造・時点型の確定意味契約

## 対象

| 参照 | 観点 |
| --- | --- |
| cat.compiler | 明示Domainのparse/validate/contains/format/subtyping/名前付き解決/Model出典 |
| cat.compiler.binding | 型付き比較とローカル検証codec。製品wire受理の自動拡張ではない |

## 規則

| ID | 条件 | 要求 | 検証 |
| --- | --- | --- | --- |
| JT.domains | 明示Domainをparseする | json/JSON値、json-object/JSONオブジェクト、instant/瞬間値を区別し、型付きIRへ保存する。既存の型参照名JSON/時点を宣言なしに解決しない | 正負Parser、IR validate、formatの英日往復、名前付きRegistry、未宣言と重複の拒否 |
| JT.json-tree | JSON値またはJSON objectのmembership | null/真偽/文字列/有限数値/順序列/文字列キーobjectの有限木を保持。object根はnull/array/scalar不可。key欠落とnullを区別し、循環・undefined・非有限数値・非文字キーを拒否。固定深度やbinary64への規範縮退なし | 入れ子・共有参照・循環・深い有限木・数値/Presenceの正負例 |
| JT.json-equality | JSON型の同値 | objectキー順を無視しarray順を保持。JSON数値の値同値により1/1.0・0/-0は等しく、boolと数値は異なる。既存の型なしsame全体を変更しない | 型付き同値APIと実JSONB結果、桁落ち反例、null/欠落、順序、deep tree |
| JT.instant | instantの値と同値・順序 | 瞬間を厳密な有理数の内部値で保持し、同じ瞬間の同値と前後を比較する。無制約stringを瞬間と認めず、未知の形式/naive日時を暗黙変換しない。精度/epoch単位を製品APIへ強制しない | 明示codecによるoffset同値・sub-ms差・並び・invalid/naive、内部値と外部wireの分離 |
| JT.typed-comparison | 複合型を比較する | ref/nullable/record/sequence/setの型を辿りJSON/instantの同値を適用する。Presence、他のscalar型の同一性、集合の順序非依存/重複禁止を保存する。型付きsetへの追加・削除は操作前に既存集合全体の型所属・型付き同値に基づく重複禁止を検証し、違反時はDomainErrorで拒否する | JSON/instantを内包するrecord/set、bool/0、既存集合内のJSON数値1/1.0の重複、操作前後の不変条件、未解決型はfail closed |
| JT.codec | losslessな検証bindingを使用する | JSON数値は丸めを避けて解析/再出力する。例示offset日時codecは西暦0001〜9999年、ASCII数字、既知UTC offset、閏秒なしを対象とし、未知offsetの-00:00とnaive日時を拒否する。抽象instant値域にcodecの範囲制限を課さず、失われた既定JS精度を復元したとはしない。製品保存データや全HTTP形式の保証ではない | 大整数/小数/Unicode/深い構造の往復、日時codecのASCII以外の数字・未知offset・閏秒の拒否、型付き内部carrierの往復。raw DB観測は独立した外部検証として扱う |
| JT.inclusion | 新Domainの包含を判定する | json-objectはjsonへ包含。同一instantは包含するがstringへの暗黙変換をしない。任意JSONを閉じたrecordやscalarへ包含しない。未解決参照・不正Domain・不正循環について真の包含証明を返さない | subtypeの正負・JSON record/collectionとの構造関係・不正Domainの負例・既存全回帰 |
| JT.source-model | Registry/Modelへ接続する | 新構造と宣言Source ID/SHAを保存して全依存を解決し、Compilerと独立Model Conformanceで照合する。解決をClosureや自由文Rule同値証明へ転用しない | 名前付き型の独立Source→Model照合、stale/改竄負例、未承認Sourceのstrict Gate停止。製品固有の件数は本契約の普遍的受入条件にしない |
| JT.fail-closed | 新意味の演算を既存経路で扱う | 型付き比較と旧型なし比較を混同しない。型付き意味が必要な未対応AST/rendererは拒否または未証明を保持し、代表fixtureの成功で全域passedにしない | 新型を含む式の反例と明示停止、既存演算の回帰、正式/診断Gateを別記 |
| JT.authority | 技術契約と製品型を採用する | 本Sourceは利用者の承認を得たCAT-TDD本体の技術契約。新業務規範・数値上限・全日時精度・TTLは追加しない。実装案/回帰成功だけでConfirmedや正式Gateへ昇格しない | 具体SHA・差分・採否文書・正規promoter・fresh Gateを分離 |

## 適用境界

CAT-TDD本体の新しい構文/IR/APIだけを対象とする確定技術契約。製品固有の型宣言、wire、権限、実Provider観測、正式Process Closureは本Artifactに従属しない独立の規範・証拠を要する。既存の誤った型/未知frame/Provider自己申告を真にする検査緩和は行わない。

本Sourceは、利用者の明示承認に基づき正規promoterでConfirmedへ昇格した。承認済み技術仕様の存在と、実装がその全規則を機械的に証明したことは別である。CI成功を正式Gateのpassedとみなさず、必要なGateはこのConfirmed SourceのID・SHAで検証する。

## 由来と変更理由

- CAT31固定候補 `cat.compiler.json-instant` から、CAT-TDD本体に属する意味契約のみを切り出した。旧候補の製品作業パスは本体では存在しないため正本依存にしない。
- 独立レビューで再現された既存set全体の妥当性検査漏れを `JT.typed-comparison` の前提条件に明文化した。
- 明示offset codecがASCII数字のみを受理する修正とその負例を `JT.codec` に反映した。
- 不正Domainから正の包含証明を発行しないW06修正の判定境界を `JT.inclusion` に明記した。
- 本体候補実装はPR #86（https://github.com/surumeneco/CAT-TDD/pull/86）。規範承認は本書の`decision_ref`で参照する利用者の採用決定に基づく。製品の採用Decisionは本体の技術契約を承認する根拠ではない。
