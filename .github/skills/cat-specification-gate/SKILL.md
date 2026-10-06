---
name: cat-specification-gate
description: "Audit and gate CAT Drafts and confirmed specifications for reference closure, PI direction, state provenance, TCE condition coverage/overlap, effects and process links. Use for CAT conformance review or Draft promotion; distinguish semantic review from mechanical lint."
---


# CAT specification gate

1. 規範入力と候補・証拠を分類し、scope、decision_ref、base_revisionを固定する。
2. `python .cat-system/skills/cat-specification-gate/scripts/cat_artifact_lint.py --artifacts <CAT-dir>`でfront matter、ID、参照整合性を検査する。失敗は修正候補、passは意味上の保証ではない。
3. Processの`Interfaces / State / Observations / Actions / Triggers`を確認し、PIの相手Process・direction・presence・operation、Triggerの発生源、Condition参照元、Effect作用先、到達可能な仕様状態の帰属を審査する。Process内部stateがPIへ混入していないことも確認する。
4. TCEは人間向け`Behaviors / 振る舞い`単位でTrigger→Condition→Outcome/Effectを読む。同一TriggerでConditionのcoverage・overlap・矛盾・到達不能を検討する。`Coverage requirement / 網羅要求: closed`は要求であって証明結果ではない。機械証明不能なら`unproven`/`inconclusive`として残し、closed済みへ昇格しない。
5. 閉世界の不変対象と連携相手の受付領域を確認し、CommonRule / DomainSpecが必要な横断規則・構造・複数実行関係・視覚等を自由記述へ取りこぼしていないか、各DomainSpecに検証方式があるか確認する。
6. 違反は出典・対象ID・理由・修正条件を示す。未観測は違反と断定しない。
7. reviewer自身が意味決定を行わない。`decision_ref`が示す承認に限定して`confirmed`化を許す。承認が無ければDraftを維持。

既存の`cat-conformance-review` Skillは別途の非適合度診断として共存する。診断上のscoreを、仕様承認や工程ゲートの代替にしない。


## 形式ゲートはCLIへ委譲

指定したProcess/PI/TCE/(DomainRule)だけを検査するときは`python .cat-system/skills/cat-specification-gate/scripts/cat_artifact_lint.py --files <Process.md> <PI.md> <TCE.md> [DomainRule.md]`。`--artifacts <dir>`はディレクトリ中の**全MarkdownをCAT形式として検査**するため、README/NOTES混在時は`--files`を使う。lintが通っても意味の由来、Conditionの一般被覆、決定refの承認主体を確認したことにはならない。Workでの結果は`cat_flow.py run`で証拠化する。
