---
cat_version: '0.3'
kind: domain-spec
id: cat-tdd.spec-test-sync.routing-contract
status: draft
process: cat-tdd.spec-test-sync
source_refs:
  - https://drive.google.com/file/d/1l73dJkpggDA96MT4st9Ha-NIwdEXNLSW/view
refs: []
semantic_contract: markdown-v2
language: ja
---

# spec-test-sync のフロー・権限境界（Draft）

## 対象
| Ref | Aspect |
| --- | --- |
| cat-tdd.routing | 第5フローの独立した選択・stage構成 |
| cat-tdd.issue-work | test-maintenance Workからのhandoff |
| cat-tdd.test-sync | 規範テスト生成とTDD実装を分離する権限 |

## 規則
| ID | 条件 | 要求 | 検証 |
| --- | --- | --- | --- |
| STS-ROUTE-01 | confirmed仕様に対するテスト整備 | spec-test-syncを独立flowとして選択 | routingに独立したentryとstagesが存在する |
| STS-ROUTE-02 | issue-workでwork_kind=test-maintenance | spec-test-syncへhandoff | issue-workの既存kindを維持し新しいkindのみ追加 |
| STS-ROUTE-03 | spec-test-syncのstage列 | closure→model→conformance→vectors→suite-plan→sync→validate→run→result | Red・implementation・Green・queue-state・integrationを含めない |
| STS-PERM-01 | test-syncの実行権限 | confirmed source、model、vectors、binding、既存testを読む | production-sourceとTDD Queueの書込みを禁止 |
| STS-PERM-02 | テストの再生成 | generated-test専用パスとManifestのみ書込み可 | 手書きtest、confirmed仕様、source、他stage evidenceの変更を禁止 |
| STS-RESULT-01 | 既存コードが生成テストにGreen | 同期成功と実行Greenを別結果として記録 | Redを要求せず、TDD Queueのdoneを生成しない |
| STS-RESULT-02 | 生成テストがRedまたは未実行 | 同期の成否と実行結果を分離 | 実装変更・oracle修正を自動実行しない |
| STS-REGRESS-01 | 既存4フローを利用 | spec-implementationのRed→Green/current=1を維持 | 既存routingとguardの回帰テストを実行 |

## 適用境界
本書は採用済み設計の実装準備用Draftであり、Confirmed昇格やCAT機械Gate通過の証拠ではない。既存4フローの動作を変更せず、ChatGPT Chatモード固有の実行手順は本リポジトリに追加しない。機械的なsuite plan・Manifest・同期実装は別工程で検証する。
