---
name: tech-sqlserver
description: "Design, migrate, query, and test Microsoft SQL Server persistence against approved PI/TCE constraints, including schema, transaction, isolation, locking, and migration behavior."
---

# SQL Server persistence boundary work

1. Confirm SQL Server version/compatibility level, schema/migration tool, ORM or SQL layer, test database, application role, and relevant database options from project technical documents and current configuration.
2. Map PI type/null/default/identity/unique/reference constraints and TCE persistence effects to schema and query behavior. Identify database-enforced invariants explicitly.
3. For migrations, account for existing data, defaults/backfills, constraints/indexes, compatibility, recovery, and deployment order. Do not treat a migration script as reversible unless the actual deployment path proves it.
4. When TCE depends on concurrency or atomicity, test transaction, isolation, locking or row-versioning behavior under the project's actual database settings rather than assuming server defaults.
5. Record migration execution, database-backed tests, and target server/database configuration separately from application-level tests.

## DB性能・I/O・競合のレビュー

DBアクセス・クエリ・大量書込み・Migration・性能改善を扱うWorkでは、[共通の8観点と実測・例外規則](../../../.cat-system/docs/DB性能設計・検証.md)を適用する。逐次COMMITとbulk insert、並列write競合、索引/INCLUDEの読取利益と更新コスト、identity/sequence/UUID PK、selectivity・skew、集計行のUPDATE競合、幅広いテーブル、DBでのJOIN/絞込/集約とN+1を検討し、無関係な観点は必須化しない。
SQL Serverでは利用可能なQuery Store、actual execution plan、`SET STATISTICS IO/TIME`、DMV等で実行計画・読み取り量・待機・ログ/ロックを観測する。row versioningとtransaction isolation、lock escalation、online index操作の製品版・edition・設定依存性を確認する。性能閾値や採否は承認済みSLOと測定条件を基準とし、migration/復旧の正しさを性能から推測しない。
