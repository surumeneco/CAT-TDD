---
name: cat-test-model
description: "Derive a human-readable CAT TestModel from confirmed Process/PI/TCE/domain-rule artifacts while preserving reachable state partitions, transitions, allowed outcomes, invariants and test oracles. Use before concrete test frameworks, fixtures or case-combination techniques."
---

# CAT specification → TestModel

1. confirmedの仕様IDと版を固定し、状態クラス、Trigger、Condition領域、許容結果集合を抽出する。
2. Effect後の仕様状態、次Triggerへの遷移、Process間の関連をモデル化する。親の外部契約は子のテストを足すだけで代替しない。
3. 変更される作用先だけでなく、閉世界上で不変の宣言済み作用先も判定関係へ含める。
4. 各モデル行にsource PI/TCE/Rule IDとoracleの由来を添付し、コードから期待結果を補完しない。
5. 元仕様の区別が欠落した場合はblocked。仕様にない区別・結果を追加した場合は仕様へ差し戻す。
6. モデル生成後にだけ、有限な具体値/順序/組合せとテスト技術を選択する。

出力の標準は`TestModel.md`。JSON TestModelは内部連携・デバッグ用の派生物であり、人間向け正本にしない。

## 決定論的コンパイル優先

`semantic_contract: markdown-v2`のProcess/PI/TCE/(DomainRule)が機械変換範囲なら、`scripts/cat_compile_v2.py model ... -o TestModel.md`を使用する。コンパイラはMarkdownを内部`cat-machine/v2` IRへ正規化し、述語・式・許容結果をsymbolicに保持する。有限enum/bool上のみ被覆・重複を証明可能で、整数guardや一般状態遷移は未証明として残す。

自由記述から形式表・式へ意味を移す工程自体は仕様化作業であり、人間の意味確認を要する。AIが不足意味を推論して埋めない。`confirmed`以外は`--allow-draft`の試験に限る。

旧`markdown-v1`と`semantic_contract: machine-only` + `cat-machine/v2`は互換入力としてのみ扱う。新WorkでJSON ASTを作成しない。

## Workからの呼出し

対象`Work.md`の`Compilation`に確認済み入力があるときは`python scripts/cat_flow.py compile --work <Work.md> --kind model --check`を優先する。入力未対応・Draftのみ・意味未確定なら成功に見せず、AIでモデル候補を起草して独立レビューするか意味決定へ戻す。

詳細は`.cat-system/docs/機械的変換.md`を参照。
