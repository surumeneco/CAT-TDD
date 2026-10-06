---
cat_version: '0.3'
kind: work
id: demo.process.work
status: candidate
process: demo.process
source_refs:
  - https://example.org/spec
decision_ref: ''
refs:
  - demo.process.tce
entry: issue
mode: shadow
issue_ref: issue-demo
project_entry_ref: https://example.org/project
spec_status: candidate
---
# Work: demo.process.work

## 証拠
| 参照 |
| --- |
| https://example.org/evidence |

## 範囲
| プロセスID | 変更ID | 保持ID |
| --- | --- | --- |
| demo.process | demo.process.tce | demo.process.pi |

## 技術
| 技術 |
| --- |
| TypeScript |
| Vitest |
| PostgreSQL |

## リポジトリ
| 名前 | パス | 基準ref | ブランチ規則 | 許可パス |
| --- | --- | --- | --- | --- |

## 検査
| ID | 工程 | 実行形式 | 作業場所 | コマンド | テストID | 入力 | 出力 | タイムアウト |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |

## ゲート
| ゲート | 状態 | 証拠 |
| --- | --- | --- |
| semantic-review | 未実行 | — |
| test-oracle-review | 未実行 | — |
| red-review | 未実行 | — |
| pr-review | 未実行 | — |
| ci | 未実行 | — |
| merge | 未実行 | — |
| deployment | 未実行 | — |
| real-use | 未実行 | — |

## 変換
| プロセス | PI | TCE | ドメイン規則 | モデル | 具体値 | 接続 | テスト | Draft許可 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Process.md | PI.md | TCE.md | — | Model.md | — | — | — | 真 |
