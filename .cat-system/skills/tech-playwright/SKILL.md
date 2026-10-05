---
name: tech-playwright
description: "Implement and execute Playwright browser end-to-end or UI integration tests, including network payload and browser-state assertions, from approved CAT TestModels. Use only when Playwright is an adopted test technology for the scoped component."
---

# Playwright browser-boundary verification

1. 使用ブラウザ・起動条件・baseURL・認証fixture・テスト実行コマンドを採用技術文書と現行設定から確認する。
2. TestModelの操作を実ブラウザのUI操作に対応付け、DOM表示、送信request、response、必要な永続状態のどこを観測するか区別する。
3. 入力要素が保持・送信する文字列/数値/空欄等の実型、送信しないことの不変条件、時間差・非同期更新を、採用した仕様に沿ってassertする。
4. API mockやネットワーク傍受では担保できない実サーバー・DB・外部連携は別の統合テストで扱い、E2E成功の観測範囲を明記する。
5. Red/Greenの実行結果を報告する。固定sleepやブラウザ依存の偶然に頼らず、プロジェクトの安定化規則を使用する。

## 決定論的生成backend

機械可読TestModelに対しては`.cat-system/docs/機械的変換.md`の`cat-playwright-binding/v1`を用いる。selector、`fill`/`selectOption`/`click`、captured JSON、認証・APIモックのharnessは**対象プロジェクトの現行技術構成とコードを確認して**明示する。これらはコード生成のbindingであり、仕様oracleの根拠と混同しない。生成器がサポートしない観測・不変条件では自動生成を中断する。

## CAT v2との関係

既存の`cat_compile.py`/`cat-playwright-binding/v1`は代表値先行のlegacy試作。`cat-test-model/v2`からPlaywrightを生成するbackendは未実装。必要ならVitestのDriver契約とは独立したPlaywright実行adapterを追加し、元の条件式と全観測対象を保持する。現時点でv1の成功をv2のPlaywright対応済みと呼ばない。
