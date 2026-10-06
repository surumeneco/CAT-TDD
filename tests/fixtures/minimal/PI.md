---
cat_version: '0.3'
kind: pi
id: demo.process.pi
status: draft
process: demo.process
source_refs:
  - https://example.org/spec
refs:
  - demo.process.contract
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# PI: デモ境界

## 境界
| 相手Process | 方向 |
| --- | --- |
| demo.user | 双方向 |

## 項目
| ID | 方向 | Domain | 存在 |
| --- | --- | --- | --- |
| 入力.有効 | 受信 | 真偽 | 必須 |
| 出力.受理 | 送信 | 真偽 | 必須 |

## 操作
| ID | 方向 | 起点 |
| --- | --- | --- |
| 送信要求 | 受付 | 送信 |
| 結果提供 | 提供 | — |

## 制約
| 式 |
| --- |
