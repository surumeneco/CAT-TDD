---
name: tech-web-accessibility
description: "Implement, audit and test Web UI accessibility, including semantic HTML, ARIA, keyboard/focus, screen-reader output, visual access and WCAG evidence. Use when the documented Work explicitly adopts Web Accessibility and touches accessibility behavior or verification. Combine with the adopted UI/E2E technology skill; do not treat a passing automated scan as full conformance."
---

# Web accessibility implementation and evaluation

## 適用と規範境界

1. 対象component・画面・操作状態、ブラウザ、既存の設計システム、アクセシビリティ要件と規範の出典をプロジェクト文書・承認済みProcess/PI/TCEから確認する。**WCAG 2.2 AAを勝手に要求・宣言しない**。対象規範に指定があれば、その版とレベル、適用除外や検査対象範囲を明記する。
2. このSkillは技術的な実現・検証手順を提供し、未承認の振る舞いをPI/TCEのoracleに追加しない。観測された不具合、推奨改善、仕様上の不足を分けて扱い、仕様変更が必要なら規範側の判断へ戻す。
3. 同じWorkで採用済みのVue/React/Next.js等のUI Skill、Playwright等の実ブラウザ検証Skillを必要な場合だけ併用する。導入されていないライブラリや設定をSkillの都合で追加しない。

## 実装・評価

1. 評価対象をページ単位ではなく、操作前後の状態（初期表示、dialog、メニュー、入力エラー、読み込み中、完了通知、レスポンシブ表示等）で特定する。観測しなかった状態を合格に含めない。
2. HTMLネイティブの意味・操作を優先し、見出しとランドマーク、フォームラベル、accessible name/description、表の見出し、画像の代替表現を実DOMとアクセシビリティツリーで確認する。ARIA role/state/propertyを追加する際はWAI-ARIA APGの該当patternとキーボード契約を参照する。
3. キーボードだけで到達・操作・離脱できるか、フォーカス順・可視性・移動・dialog閉鎖後の復帰・背景操作・ポインタ操作との同等性を、実ブラウザで検証する。フォーカスが視覚的に隠れていないかも確認する。
4. 文字/非文字コントラスト、ズーム・リフロー、テキスト間隔、色以外の情報伝達、タッチターゲット、動き・アニメーション、メディア代替を、Workで必要な画面・表示条件で確認する。見た目だけから支援技術の結果を推測しない。
5. 既存テスト基盤で自動化可能な検査を行う。Playwright採用済みでaxeを利用可能な構成なら`@axe-core/playwright`を選択肢とする。DOM・コントラスト等の機械検出結果と、キーボード操作・スクリーンリーダー等の手動検証結果を別記する。自動検査の成功はWCAG全体の適合証明にならない。
6. 各指摘に対象状態・再現手順・実測/ツール出力・該当基準（確認できた場合）・修正箇所を紐付ける。未検査/未再現/要人手判断をpassに変換しない。テストは既承認の期待結果を参照し、実装から期待値を逆算しない。

詳細な対象状態、観測方法、証拠と限界は [評価チェックリスト](references/evaluation-checklist.md) を参照する。
