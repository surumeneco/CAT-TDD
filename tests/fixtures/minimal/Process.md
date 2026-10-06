---
cat_version: '0.3'
kind: process
id: demo.process.contract
status: draft
process: demo.process
source_refs:
  - https://example.org/spec
refs: []
decision_ref: ''
semantic_contract: markdown-v2
language: ja
---
# Process: デモ処理

## 契約
閉世界: 真

## 境界
| PI |
| --- |
| demo.process.pi |

## 仕様状態
| ID | Domain |
| --- | --- |
| 状態.準備 | 真偽 |

## 観測能力
| ID | 由来 | Domain |
| --- | --- | --- |

## 作用能力
| ID | 対象 | Domain |
| --- | --- | --- |

## 起点
| ID | 由来 |
| --- | --- |
| 送信 | demo.process.pi |
