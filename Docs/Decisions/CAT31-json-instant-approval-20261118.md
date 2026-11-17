---
title: CAT-TDD本体 JSON/instant 技術契約の採用決定
kind: normative-decision
id: CORE-CAT31-20261118-01
status: accepted
scope: surumeneco/CAT-TDD
approved_at: 2026-11-18
candidate_id: cat.compiler.json-instant
candidate_sha256: fe6d7ff63928f5b9a243a2e737b6e6b569f7b7d3ecdd83522f57c85baa7d44fe
---

# JSON構造・時点型のCAT-TDD本体契約：採用記録

## 採用対象と権限の根拠

- 対象はCAT-TDD本体の技術契約 `cat.compiler.json-instant`。承認された候補原文は SHA-256 `fe6d7ff63928f5b9a243a2e737b6e6b569f7b7d3ecdd83522f57c85baa7d44fe`、Git blob `aa8c432a248086d32bdb44be35f5e3a44ed53bd9`。候補原文は[PR #86](https://github.com/surumeneco/CAT-TDD/pull/86)の変更履歴に保存される。
- 利用者は本会話（2026-11-18、日本時間）で、上記SHAのCAT-TDD本体技術契約の正式採用が次工程に必要であることを説明された直後、**「確認しました。問題ありません。」**と明示的に回答した。この返答を当該対象への承認と記録する。承認は**利用者の発言**によるものであり、本書を作成したAI自身が規範権限を取得・代行したわけではない。
- 承認対象は、候補の `JT.domains` 〜 `JT.authority` 10規則に示すCAT-TDD共通Compilerの意味と境界。候補の行政上の未承認表現は昇格と同時に実態へ合わせて修正してよいが、型とcodec、同値、出典、外部作用の技術的意味は変更しない。

## 決定と非決定

**採用する**：上記候補を正規 `cat_promote.py` により `Docs/Constraints/cat.compiler.json-instant.domain-spec.md` へConfirmed昇格し、対応する実装・検証が完了したまとまりを `develop` に統合する。

**今回採用しない**：製品個別のJSON/時点型のSource昇格、任意のwire形式・DB実作用・外部Providerの真正性、自然言語Ruleの自動意味同値、一般的な非有限状態空間の証明、未対応Rendererのpass扱い、`main`へのリリース。製品固有の規範判断・実証と、このCAT-TDD本体の技術契約採用は独立である。

## 検査と出典境界

- 規範採用の証拠は上記の利用者発言と固定候補SHA。PR・テスト成功や本書のAI作成だけを採用根拠にはしない。
- 昇格前の候補SHAと昇格後のConfirmed SHAは別の値。正規promoterが行うstatus/decision_ref/移動と、旧「未承認」等の**状態説明だけ**の変更を区別し、規則の技術的内容が変わらないことを照合する。
- Rule本文の採用と、機械的VerifierがそのRuleの意味を証明したことは別。DomainSpec単体の構文検査・正規読取り・上流全回帰をProcess Closureの正式合格と読み替えない。
