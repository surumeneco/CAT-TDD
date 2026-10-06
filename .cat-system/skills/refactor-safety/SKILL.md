---
name: refactor-safety
description: "Run behavior-preserving refactoring as an independent flow using fixed CAT semantics, deterministic dependency ordering and unchanged test oracles."
---

# Refactor safety

Refactorはimplementation flowの必須後段ではなく、commit/diff/明示範囲を起点とする独立flowである。

1. `ref-scoper`が保存すべきconfirmed PI/TCE/制約と変更範囲を決める。
2. dependency / hierarchy graphから`cat_scope_order.py`でreadyな最深scopeを選ぶ。
3. 変更前Green / regression baselineを確保する。
4. `ref-refactor`はproduction sourceだけを変更し、spec / TestModel / Queue / tests / evidenceを固定する。
5. 同じoracleでregressionを機械実行する。
6. 外部観測意味の変更が必要なら停止し、specification/Issue flowへhandoffする。
