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

既知能力の使用に対応bindingがない、binding先のObservation/Actionが仕様に存在しない、公開exportがPI operationへ結び付かない場合は`blocked`とする。wildcard export、実際には観測されないBinding先symbol、必須PI operationの公開symbol対応を機械的に閉じられない場合は`inconclusive`とし、passへ推測補完しない。public entrypointは検査対象source内でなければならない。

このInspectorはTypeScript AST全体や任意ライブラリの副作用を完全証明するものではない。宣言された検査能力の範囲を超える意味はImplementation Conformance Obligationとして`inconclusive`に残す。

### 限定された能力閉集合の証明

任意のTypeScriptを静的に完全解析する代わりに、Bindingに任意項目 `capability_analysis: "primitive-pure-functions/v1"` を指定できる。閉世界Processで追加のObservation/Actionが存在せず、`source_globs`が明示的なファイル一覧で`public_entrypoints`と完全一致し、全ファイルが限定純粋関数構文に収まる場合のみ`capability.closed-set`をcoverage IDに加える。

限定構文は公開関数宣言、primitive型または文字列literal unionの引数、単一return、引数とliteral、否定・短絡論理・厳密等値・条件式、静的キーのobject literal（`as const`可）に限る。全tokenを認識する。未解釈のimport・呼出し・property access・外部変数・初期化・その他の構文は`inconclusive`とし、未検出を閉包と扱わない。`capability_analysis`の証拠には検査scopeと各source SHAを含める。

この証明は指定されたsource module本体の能力使用に限る。呼出元、loader、build transform、任意のTypeScript型検査、PIの型意味の同値、他Processへの伝達や外部Providerは証明しない。既知能力の規範外使用は引き続き`blocked`。この限定検査の未証明は、既存の個別Interface検査結果と分離して報告する。

採用済みstrict型検査は、`Compilation.technology_constraints` の `cat-project-typecheck/v1` を使って独立の実装制約として実行できる。実際のnpm lockfileとコンパイラ、対象ソース包含を検査する。型検査成功はPI・観測/作用能力・実行時挙動の証明ではない。詳細は `docs/機械的変換.md`。
