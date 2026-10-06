---
name: cat-specification-gate
description: "Validate CAT artifact syntax and the independent process-closure, model-conformance and implementation-conformance gates. Use deterministic validators first and escalate only inconclusive semantics to the corresponding reviewer."
---

# CAT gates

## Artifact lint

`scripts/cat_artifact_lint.py`は構文・参照形式・機械契約を検査する。lint passは意味承認ではない。

## process-closure

assembled confirmed specificationの到達可能領域を閉じているか検査する。現行compilerが単一Process・有限guard範囲で証明できる場合はValidatorだけでpass/failを確定する。multi-Process compositionや非決定論的意味で判定不能なら`inconclusive`とし、`cat-reviewer`がその箇所だけを審査する。

## model-conformance

TestModelをcurrent confirmed sourceから完全再生成し、一致、source hash、source semantic mapを検査する。欠落/余分な意味が機械的に確定すればfail。構造上判定不能な意味だけ`cat-model-reviewer`へ委譲する。

## implementation-conformance

`cat-implementation-obligations/v1`でInterface / Capability / Behavior / Invariant / Cross-process / Domain / implementation-constraintを独立obligationとして集約する。Green/CIをGate代替にしない。全categoryがpassed evidenceを持てばpass、failedがあればfail、未実行/判定不能はinconclusiveとして`cat-implementation-reviewer`へ限定委譲する。

Reviewerは対象Artifactを修正せず、failedをpassへ上書きしない。
