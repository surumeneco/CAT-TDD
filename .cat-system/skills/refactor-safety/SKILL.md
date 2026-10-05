---
name: refactor-safety
description: "Scope and perform behavior-preserving source refactors under confirmed CAT PI/TCE/domain rules, unchanged test oracles and regression evidence. Use after Green for code simplification or technology migration without specification changes."
---


# Refactor with observable meaning preserved

1. confirmedのProcess/PI/TCE/Rule、対象変更範囲、既存テスト、観測差の禁止範囲を固定。
2. ref-scoperは子から親へ影響し得る依存関係とshared codeを追跡し、書込み対象と順序を定める。
3. 実装内の不要な分岐・重複・抽象化・依存を意味保存の範囲で簡約。オッカムの剃刀は外部意味を省略する規則ではない。
4. 既存test oracle・PI・TCE・DB移行意味を変更しない。同じテストが通っても未観測の領域は未検証として扱う。
5. Green、関連回帰、静的制約、適切な場合は性能・セキュリティ・外部契約を検証し、実行証拠を保存。
6. 観測振る舞いを変える修正案が必要になれば、Refactorを止め仕様変更Workへ分離する。

出力: Refactor scope、コード差分、変更されない仕様ID、実行結果と残る未検証範囲。


## 再現可能な保存チェック

変更前の仕様ID・テストファイル・入力・観測境界をWorkへ固定し、`cat_flow.py git`で差分scope、`run`でGreen/回帰のJUnit証拠を取り直す。TestModelとテストのoracleは変更しない。実行証拠のhashが古ければ`stale`として再実行し、テスト成功だけでは同値性を証明しない。
