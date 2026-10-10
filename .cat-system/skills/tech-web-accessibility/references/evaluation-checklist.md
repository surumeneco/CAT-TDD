# Webアクセシビリティ評価チェックリスト

この文書は検査観点の候補集であり、対象Workに未採用の規範を自動的に要求するものではない。対象component、規範と検査対象状態、支援技術・ブラウザ環境は当該プロジェクトの規範文書・現行実装に従う。

| 対象 | 技術的な観測対象 | 観測手段・限界 |
| --- | --- | --- |
| 構造と意味 | document language、title、見出し階層、landmark、リスト、表header、読み順 | 実DOM＋アクセシビリティツリー＋読み順の人手確認 |
| 名前・説明・状態 | link/button/inputのaccessible name、label、help/error、required/invalid/expanded/selected、状態変化 | role/nameベースの検査、アクセシビリティツリー、必要に応じ支援技術 |
| キーボード・フォーカス | Tab/Shift+Tab、Enter/Space、矢印キー等のpattern、focus trap、focus return、visible focus、スクロール時の被覆 | 実キーボード操作。ARIA付与のみでは動作保証しない |
| 動的UI | dialog/menu、SPA遷移、非同期更新、フォーム送信結果、ステータスメッセージ | UI状態遷移＋手動支援技術確認。ARIA live regionの有無だけで読み上げ保証を宣言しない |
| 視覚・操作 | テキスト/非文字コントラスト、ズームとreflow、テキスト間隔、色依存、pointer/dragging代替、target size、reduced motion | 実表示条件・対象要素を固定。自動検出だけでは見落としがある |
| 非テキスト・メディア | 画像の用途別代替、アイコンボタン、装飾、字幕・音声解説・書き起こし | 内容の同等性と目的は人手判断が必要 |
| 入力・認証 | 入力目的、説明とエラー、修正案内、重複入力回避、認証方法、パスワードマネージャーと貼り付け | 手動操作と仕様照合。機能要件そのものの変更は規範側で判断 |

## 自動検査を組み込む場合

Playwright + `@axe-core/playwright` が**既に採用または採用承認済み**の構成なら、[Playwright公式のaccessibility testing](https://playwright.dev/docs/accessibility-testing)に従い、対象ページと**検証したいUI状態**でaxeを実行する。静的な初期表示だけを検査してdialog等の遷移状態を検査済みにしない。依存パッケージを追加する場合はプロジェクトの導入・変更権限に従う。違反件数ゼロとWCAG適合認定を同一視しない。

```ts
// Example only, not a replacement for adopted project fixtures or test oracle.
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('documented UI state: automatically detectable violations', async ({ page }) => {
  await page.goto('/'); // Replace with the project's approved test route and state.
  const scan = await new AxeBuilder({ page }).analyze();
  expect(scan.violations).toEqual([]);
});
```

実際のテストでは観測対象状態を再現するfixtureと実行環境、axeのルール対象外、実行・未実行の範囲を明記する。自動検査結果は技術上の証拠であり、仕様oracleや未承認規範の代用ではない。

## 報告単位

- 対象: component/画面/状態/viewport/ブラウザ/支援技術
- 根拠: 指定規範の版・レベル・該当基準、または規範未指定
- 検査: automatic / manual / source review と実行コマンド・再現操作
- 結果: observed-pass / observed-fail / inconclusive / not-run
- 証拠: DOM/accessible name、実際の出力・表示、失敗箇所、観測時点
- 残存範囲: 自動検査で判定不能な項目、未観測状態、環境未再現

## 一次資料

- [W3C WAI: WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/)
- [W3C WAI: Evaluating Web Accessibility](https://www.w3.org/WAI/test-evaluate/)
- [W3C WAI: Selecting evaluation tools（自動検査の限界）](https://www.w3.org/WAI/test-evaluate/tools/selecting/)
- [W3C WAI: ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/)
- [W3C WAI: Developing a Keyboard Interface](https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/)
- [Playwright: Accessibility testing](https://playwright.dev/docs/accessibility-testing)
