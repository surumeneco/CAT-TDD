---
name: tech-mysql
description: "Design, migrate, query, and test MySQL persistence against approved PI/TCE constraints, including schema, null/default, transaction, locking, and migration behavior."
---

# MySQL persistence boundary work

1. Confirm the MySQL version, storage engine, SQL mode, schema/migration tool, ORM or SQL layer, test database, and application role from project technical documents and current configuration.
2. Map PI type/null/default/unique/reference constraints and TCE persistence effects to schema and query behavior. Identify which invariants are enforced by the database and which remain application-level.
3. For migrations, account for existing data, defaults/backfills, constraints/indexes, compatibility, rollback/recovery, and deployment order. Do not use production data destructively as a test mechanism.
4. When TCE depends on concurrency or atomicity, test transaction, isolation, locking, and autocommit behavior under the project's actual database configuration rather than assuming defaults.
5. Record migration execution, database-backed tests, and target database/version separately; schema application success does not by itself prove application conformance.

## DB性能・I/O・競合のレビュー

DBアクセス・クエリ・大量書込み・Migration・性能改善を扱うWorkでは、[共通の8観点と実測・例外規則](../../../.cat-system/docs/DB性能設計・検証.md)を適用する。COMMIT頻度とバルク投入、並列writerの競合、索引維持コスト、identity/UUIDとクラスタ索引、selectivityとskew、ホット行UPDATE、テーブル幅、JOIN/WHERE/GROUP BY pushdownとORMのN+1を、実際のワークロードに照らす。いずれも一律禁止ルールではない。
InnoDBではクラスタ化PKとセカンダリ索引のサイズ、gap/next-key lockと分離レベル、redo/flushと`LOAD DATA`の運用条件を検証する。MySQL版が対応する場合に`EXPLAIN ANALYZE`、利用可能なPerformance Schema/`sys`の観測を使う。暗黙COMMITを伴うDDL、metadata lock、online DDL対応は実際の版/設定で確認する。整合性・復旧要件と測定結果を分離し、未測定の性能やCAT Gateを成功とみなさない。
