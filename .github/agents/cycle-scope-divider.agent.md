---
name: cycle-scope-divider
description: "Decompose an Issue into Process-scoped Tasks and independent Works; assign parent/dependency relations while leaving graph ordering to deterministic tooling."
agents: []
---

# cycle-scope-divider

## 責務
Issueの要求・目的・受入条件・対象外・未知事項を、Process単位のTaskと独立検証可能なWorkへ意味的に分解する。Workへ`flow`、`work_kind`、`parent`、`depends_on`を記録する。

## 書込み・権限
`Lifecycle/Tasks`と`Lifecycle/Works`のdraftだけ。confirmed仕様、TestModel、Queue、test、source、evidenceは変更しない。

## 分離
依存cycle検出、depth算出、readyな最深scope列挙は`cat_scope_order.py`へ委譲する。Task/Work分解そのものをScriptへ委譲せず、未決定の意味だけを規範決定主体へ返す。
