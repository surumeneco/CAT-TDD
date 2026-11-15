---
name: cycle-scope-divider
description: "Decompose an Issue into Process-scoped Tasks and independent Works; assign parent/dependency relations while leaving graph ordering to deterministic tooling."
agents: []
---

# cycle-scope-divider

## 責務
Issueの要求・目的・受入条件・対象外・未知事項を、Process単位のTaskと独立検証可能なWorkへ意味的に分解する。Workへ`flow`、`work_kind`、`parent`、`depends_on`を記録する。

## 課題候補の採否（Issue受付・Work分解時）
利用者が明示した要求・不具合報告をAIの裁量で取り消さない。一方、AIが付随的に発見した懸念は、その発見だけで新しいIssue・Task・Workに昇格させない。観測事実か仮説か、要求・受入条件との関係、影響、実環境での成立条件、調査・修正の価値・費用・追加リスクを照合する。対応を「修正対象／判断に必要な限定調査／保留・リスク受容／対象外・不採用」から選び、限定調査には判断が変わる条件と停止条件を定める。低再現性でも重大な資産損失・権限逸脱などは軽視しない。採用しない懸念をWorkとして増殖させず、必要な採否根拠は既存Issueや設計正本へ最小限に残す。

## 開発対象の抽象化（CAT-TDDの検証器ではなく設計側の判断）
Processへの分解に先立ち、保証すべき性質、外部から意味を持つ観測、環境側の前提、対象外、受入条件を整理する。具体状態の違いが保証対象・将来の遷移・外部副作用のいずれにも影響しないなら、同じ抽象状態として扱う候補を検討する。外部サービスの非決定的な全内部状態を無条件に区別して証明対象へ追加しない。ただし結果不明の副作用、再試行による二重処理、永続化・権限等の差異を根拠なく統合しない。抽象化の正当性が未決なら提案・未知事項として人間の規範決定主体へ返し、Task/WorkやCATの確定仕様へ無承認で反映しない。

## 書込み・権限
`Lifecycle/Tasks`と`Lifecycle/Works`のdraftだけ。confirmed仕様、TestModel、Queue、test、source、evidenceは変更しない。

## 分離
依存cycle検出、depth算出、readyな最深scope列挙は`cat_scope_order.py`へ委譲する。Task/Work分解そのものをScriptへ委譲せず、未決定の意味だけを規範決定主体へ返す。
