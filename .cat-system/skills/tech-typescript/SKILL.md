---
name: tech-typescript
description: "Apply TypeScript-specific typing, compile diagnostics and typed boundary checks to TypeScript source or tests. Use only when the component's technology document declares TypeScript and the Work changes TypeScript code."
---

# TypeScript implementation / diagnostics

1. 採用版、`tsconfig`、package manager、対象packageと型検査コマンドを技術構成文書・現行manifestから確認する。型検査の結果を仕様の根拠にしない。
2. PIが要求する入力・出力・不在・null・エラーの区別を境界の型定義へ対応させる。TypeScript上の型は実行時検証の代わりにしない。
3. JSON、UI、DB、外部APIなど型保証が消える境界は、実行時の検証・変換・契約テストの必要性を確認する。
4. プロジェクトで認められた型検査・lint・testを実行し、実行コマンド・結果・未実行範囲を記録する。型の追加でテストoracleを変更しない。
