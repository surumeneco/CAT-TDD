---
name: tech-typescript
description: "Apply TypeScript-specific typing, compile diagnostics and typed boundary checks to TypeScript source or tests. Use only when the component's technology document declares TypeScript and the Work changes TypeScript code."
---

# TypeScript implementation / diagnostics

1. 採用版、`tsconfig`、package manager、対象packageと型検査コマンドを技術構成文書・現行manifestから確認する。型検査の結果を仕様の根拠にしない。
2. PIが要求する入力・出力・不在・null・エラーの区別を境界の型定義へ対応させる。TypeScript上の型は実行時検証の代わりにしない。
3. JSON、UI、DB、外部APIなど型保証が消える境界は、実行時の検証・変換・契約テストの必要性を確認する。
4. プロジェクトで認められた型検査・lint・testを実行し、実行コマンド・結果・未実行範囲を記録する。型の追加でテストoracleを変更しない。

## Implementation conformance

`scripts/cat_typescript_conformance.py`はTypeScript実装のうち、静的に判定可能な公開Interfaceと既知の外部能力使用をCAT仕様へ照合する。AIによるコード読解をGateの通常経路に置かない。

Workの`Compilation / Conformance binding`は`cat-typescript-conformance-binding/v1` JSONを参照する。bindingは少なくとも次を宣言する。

- `repository`: Workで宣言済みのrepository名。
- `source_globs`: 検査対象TypeScript source。
- `public_entrypoints`: 外部公開境界として扱うentrypoint。
- `interface_symbols`: export symbol → PI operation ID。
- `capabilities`: `environment / network / filesystem / clock / random / timer` → Process Observation/Action ID。

既知能力の使用に対応bindingがない、binding先のObservation/Actionが仕様に存在しない、公開exportがPI operationへ結び付かない場合は`blocked`とする。wildcard exportや必須PI operationの公開symbol対応を機械的に閉じられない場合は`inconclusive`とし、passへ推測補完しない。

このInspectorはTypeScript AST全体や任意ライブラリの副作用を完全証明するものではない。宣言された検査能力の範囲を超える意味はImplementation Conformance Obligationとして`inconclusive`に残す。
