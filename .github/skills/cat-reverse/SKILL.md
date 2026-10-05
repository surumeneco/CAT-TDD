---
name: cat-reverse
description: "Reconstruct present-day behavior as source-linked CAT Candidates from code, tests, logs and runtime evidence. Use for current-to-specification reverse engineering, bug forensics or brownfield onboarding; never canonize observed code by itself."
---


# Current → CAT Candidate

1. 対象sliceとGit commit/branch、Driveの規範版、実行環境を記録。対象が複数repoなら接続先の実体を確認。
2. コード、テスト、DB migration、API schema、ログ、ユーザ操作・外部連携を、誰が何を観測した証拠か分けて取得する。
3. `Observation`に現在の事実、`Candidate`にProcess/PI/TCE候補、`Question`に望ましい振る舞いの未決定部分を記す。コード上の現在値から望ましさを推論しない。
4. 規範文書と一致すればその出典を紐付ける。矛盾するなら`conflict`、規範が無ければ`candidate`を維持。
5. 未観測・検索不十分と、十分に探索して確認した不在を区別。失敗ログの「実際の振る舞い」は本来のEffectではない。
6. 意味の選択がユーザに委任されている場合は選択肢と影響を示し、明示された範囲を決定記録化する。委任外は承認待ち。

出力: `CAT/Candidates/<id>.md`の候補、証拠台帳、欠落した規範のリスト。確定Draft生成は`cat-artifacts`へ移す。過去の検証生成物を候補の規範として参照しない。
