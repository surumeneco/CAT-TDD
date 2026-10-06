---
cat_version: '0.3'
kind: tce
id: demo.process.tce
status: draft
process: demo.process
source_refs:
  - https://example.org/spec
refs:
  - demo.process.pi
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# TCE: デモ処理

網羅要求: closed

## 振る舞い
| ID | 起点 | 条件 | 結果 | 効果 |
| --- | --- | --- | ---: | --- |
| demo.accept | 送信 | `入力.有効` | 1 | `状態.準備 = 真; 出力.受理 = 真` |
| demo.reject | 送信 | `否定(入力.有効)` | 1 | `出力.受理 = 偽` |
