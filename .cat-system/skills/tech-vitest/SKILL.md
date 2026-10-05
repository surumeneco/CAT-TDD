---
name: tech-vitest
description: "Generate, run and review Vitest unit or integration tests from approved CAT TestModels with deterministic fixtures, mocks and observed Red/Green results. Use only for components that adopt Vitest and Work that needs Vitest tests."
---

# Vitest test execution

1. `package.json`等の現行設定、テスト配置・setup・実行コマンドを技術構成文書とrepoから確認する。未導入なら勝手に追加しない。
2. TestModelのstate partition、Trigger、許容結果、不変対象をテスト名・入力・assertionへ対応付ける。実装値を期待値として複写しない。
3. mock/fixtureは観測境界と副作用の範囲を明示し、実際のAPI/DB/ブラウザ契約まで検証したとみなさない。asyncと時計の制御はプロジェクト設定に従う。
4. 定義済みコマンドでRedとGreenを実測し、失敗理由・実行時点・scopeを報告する。VitestのpassだけでE2Eや本番確認済みにしない。

## CAT v2でのコード生成

`cat-test-model/v2`からのVitestコード生成は`scripts/cat_compile_v2.py tests`を利用する。driverは`prepare(pre,input)`で実状態を成立させ、`trigger(name,input)`で操作して宣言出力を返し、`observeState()`で宣言したstateを前後とも観測する。生成コードの`allowed`は仕様由来。実装内部の期待値を写さず、既存テストと独立したfixture由来を検証する。`driver.stub.ts`は`BINDING_NOT_IMPLEMENTED`を投げる未接続例である。`--allow-draft`で生成した証拠用コードを本番テストのoracleとして採用しない。


## JUnit evidence adapter

Workの`checks`に、現行Vitestの対象テストを実行し`{report}`へJUnit XMLを書き出す**実際に検証したargv配列**を定義する。`cat_flow.py run --id <check-id> --execute`はテスト名を一意照合し、欠損・skip・error・対象外失敗を区別する。Redにおける失敗理由の同一性は機械だけでは確定しない。実WebAppで実行する場合はDocker/DB fixture・本番データ非破壊を正本文書とTESTING.mdで確認する。
