---
name: cycle-management
description: "Manage Issue/Task/Work lifecycle, deterministic dependency ordering, flow handoffs and read-only Git state without conflating these mechanics with specification semantics."
---

# Cycle management

人間はIssueを入口としてよい。`cycle-scope-divider`が意味的にTask/Workへ分解し、Workへ`flow / work_kind / parent / depends_on`を記録する。

AIが発見した懸念の採否は`cycle-scope-divider`の課題候補の判断に従い、ユーザー要求と自発的な仮説を混同しない。採用していない懸念や、保証対象外と決定した状態の差異を、機械的にTask/Workへ追加しない。既存Issueにある受入条件と依存関係は維持し、scope-order Scriptには採否・仕様解釈を委譲しない。

## 機械処理

- Lifecycle state移動: `scripts/cat_lifecycle.py`
- parent / depends-on cycle検出、depth、readyな最深scope: `scripts/cat_scope_order.py`
- branch/base/diff/allowed paths: `scripts/cat_flow.py git`
- structured handoff: `scripts/cat_flow.py handoff --stage ...`

scope-order Scriptは依存関係の意味を発明しない。与えられたgraphだけを順序化する。cycle時はblocked。

read-only Git inspectionはScriptで行い、`cycle-git-manager`はcommit境界やmulti-repo統合等の意味判断が必要な場合だけ起動する。CI / merge / deploy状態はproviderを正とする。

## Runtime enforcement

標準`Lifecycle/Works/{state}/<work>/Work.md`配置では、書込みAgentのhandoff前guardが全active Workからscope-orderingを再計算し、deepest-readyでないWorkのAgent起動をblockedにする。Lifecycle外で`parent / depends_on`を持つWorkは全graphを検証できないためfail closedとする。
