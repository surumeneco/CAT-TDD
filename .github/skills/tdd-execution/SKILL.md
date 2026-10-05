---
name: tdd-execution
description: "Transform approved CAT TestModels into framework-independent test cases, independently review oracles, measure Red/Green and regression evidence, and coordinate applicable technology-specific skills. Use for test generation, TDD gates and implementation across technology stacks."
---

# Model → Test → Red → Green

1. confirmedな仕様とTestModelのsource ID・許容結果・観測境界を固定する。
2. Workの観測境界に必要な`tech-*` Skillをプロジェクト技術構成から選び、未採用frameworkを推測しない。
3. 同値類、境界値、状態遷移、異常、Process間契約を元モデルから必要な範囲で具体化する。
4. テスト期待値はモデルから生成し、実装の実際値を写さない。
5. Processを跨ぐ変換は入口と出口の双方を確認し、単一関数mockだけで統合動作を確認したことにしない。
6. Redは実行コマンド、exit code、失敗テストを機械証拠として記録し、意味上期待した失敗理由の承認はWorkの`red-review` Gateへ分離する。
7. Greenは最小実装後に対象テスト、関連回帰、制約lint、必要な統合検証を別チェックで実行する。
8. 実装都合でoracleを変えない。観測差が追加されたらCAT仕様へ戻す。

## モデルからの固定コード生成

`cat-test-model/v2`の人間向け標準表現は`TestModel.md`。具体値は別の`cat-test-vectors/v2`へ置く。`scripts/cat_compile_v2.py tests`にはTestModel、vectors、bindingだけでなく生成元Process/PI/TCE/(DomainRule)も渡し、再コンパイル一致を必須とする。

JSON IRやvectors/bindingは機械用の派生物として残してよいが、CAT意味正本として編集しない。旧JSON TestModelも互換入力として利用できる。

## テスト実行証拠はCLIへ委譲

機械対応時は`cat_flow.py compile --work <Work.md> --kind tests --check`で原本との再生成一致を確認する。Red/Green/回帰は`mode: implementation`のWorkでのみ`cat_flow.py run --work <Work.md> --id <check-id> --execute`を実行し、`status/handoff`で証拠を照合する。`exit-zero`だけでRed/Green、CI、deploy、人間実動作を成功と呼ばない。

詳細は`.cat-system/docs/機械的変換.md`。
