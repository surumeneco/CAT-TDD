---
name: cat-specification-gate
description: "Validate CAT artifact syntax and the independent process-closure, model-conformance and implementation-conformance gates. Use deterministic validators first and escalate only inconclusive semantics to the corresponding reviewer."
---

# CAT gates

## Artifact lint

`scripts/cat_artifact_lint.py`は構文・参照形式・機械契約を検査する。lint passは意味承認ではない。

## process-closure

assembled confirmed specificationの到達可能領域を閉じているか検査する。単一Process・有限guard範囲でも、網羅要求が`closed`かつ全Triggerが`proved`の場合だけ機械的にpassとする。`partial`、multi-Process composition、非決定論的意味などは`inconclusive`として限定レビューへ渡す。

## model-conformance

TestModelをcurrent confirmed sourceから完全再生成し、一致、source hash、source semantic mapを検査する。欠落/余分な意味が機械的に確定すればfail。構造上判定不能な意味だけ`cat-model-reviewer`へ委譲する。

## implementation-conformance

`cat_flow.py obligations`でconfirmed assembled specificationから検査obligation骨格を決定論的に生成できる。生成時点は`not-run`であり、実測証拠によってのみ状態を進める。

`cat-implementation-obligations/v1`でInterface / Capability / Behavior / Invariant / Cross-process / Domain / implementation-constraintを独立obligationとして集約する。各obligationは`source_ref`と検証`method`を持ち、passed/failedはevidence、not-run/inconclusiveはreasonを持つ。Green/CIをGate代替にしない。Technology Skillが決定論的Inspectorを提供する場合は同Gateから直接使用する。TypeScriptでは公開exportとPI operation、既知の外部能力使用とObservation/Actionを照合し、仕様外Interface/能力をblockedにする。

Validator結果は`.cat-flow/conformance/`のScript所有証拠へ保存し、Work本文の`passed`だけではGateを成立させない。Reviewerは対象Artifactを修正せず、deterministic verdictが`inconclusive`の場合だけ独立Review evidenceで閉じる。failed / blocked / stale / not-runをpassへ上書きしない。CommonRule / DomainSpecが宣言されているのにdeterministic mapping / verifierが無い場合はnormative pathをblockedにする。

## Implementation obligation evaluation

`implementation-conformance`ではobligation skeletonをconfirmed sourceから再生成して一致を確認してから評価する。各obligationは`source_ref / method / status / limitation`を持ち、passed/failedはScript/Provider evidence、not-run/inconclusiveはreasonを必須とする。Aggregatorで確定不能な項目だけconditional reviewerへ渡す。
