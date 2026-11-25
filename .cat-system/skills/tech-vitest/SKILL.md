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

`cat-test-model/v2`からのVitestコード生成は`scripts/cat_compile_v2.py tests`を利用する。共通compilerはモデル・具体ケースを扱い、Vitest固有のTypeScript描画は本Skillの`scripts/cat_vitest_renderer.py`へ委譲する。rendererをCAT意味の決定や具体値選択に使わない。driverは`prepare(pre,input)`で実状態を成立させ、`trigger(name,input)`で操作して宣言出力を返し、`observeState()`で宣言したstateを前後とも観測する。生成コードの`allowed`は仕様由来。実装内部の期待値を写さず、既存テストと独立したfixture由来を検証する。Operation別出力Presenceを観測する場合、単一の`js-driver-provide/v1`または明示的な`js-driver-provides/v1` Bindingを使用する。後者のDriver `triggerProvidedOperations(operationIds, triggerId, input)`は一回の論理Trigger実行に対応するOperation ID→観測出力項目recordの写像（空frameも明示）を返す。全操作identityと所有PIを検査し、全結果を単一の許容Outcomeと比較する。これはテストDriverの射影であって、製品側の実装API、実行順・同期方式・外部配送真正性を指定または証明しない。`driver.stub.ts`は`BINDING_NOT_IMPLEMENTED`を投げる未接続例である。`--allow-draft`で生成した証拠用コードを本番テストのoracleとして採用しない。


## JUnit evidence adapter

Workの`checks`に、現行Vitestの対象テストを実行し`{report}`へJUnit XMLを書き出す**実際に検証したargv配列**を定義する。`cat_flow.py run --id <check-id> --execute`はテスト名を一意照合し、欠損・skip・error・対象外失敗を区別する。Redにおける失敗理由の同一性は機械だけでは確定しない。実WebAppで実行する場合はDocker/DB fixture・本番データ非破壊を正本文書とTESTING.mdで確認する。

実装適合の採用技術制約は `cat_test_technology.py` が全current-itemの独立Queue証拠と、再生成したテスト、Driver/Binding、宣言入力、実runner/HEAD・named JUnitの一致を確認する場合に限り充足できる。単なる成功終了やQueue doneを証明として扱わない。
