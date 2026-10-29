---
name: tech-oracle-db
description: "Design, migrate, query, and test Oracle Database persistence against approved PI/TCE constraints, including schema, sequence/identity, transaction, locking, and migration behavior."
---


# Oracle Database persistence boundary work


1. Confirm Oracle Database version, schema/user model, migration tool, ORM or SQL layer, test database, session settings, and application role from project technical documents and current configuration.
2. Map PI type/null/default/identity-or-sequence/unique/reference constraints and TCE persistence effects to schema and query behavior. Identify which invariants the database actually enforces.
3. For migrations, account for existing data, sequence/identity behavior, defaults/backfills, constraints/indexes, deployment order, and the actual DDL recovery characteristics of the chosen migration path. Do not claim transactional rollback without observing that path.
4. When TCE depends on concurrency or atomicity, test transaction, isolation, locking, deferred-constraint behavior, and relevant session state under the project's actual configuration.
5. Record migration execution, database-backed tests, and target database/session configuration separately; successful DDL is not application conformance evidence.

## DB性能・I/O・競合のレビュー

DBアクセス・クエリ・大量書込み・Migration・性能改善を扱うWorkでは、[共通の8観点と実測・例外規則](../../../.cat-system/docs/DB性能設計・検証.md)を適用する。逐次COMMIT、書込並列度、過剰索引、sequence cache・Right Growing Index・UUIDのトレードオフ、selectivityとskew、ホット行UPDATE、巨大行、DB側JOIN/WHERE/集計とN+1を、実際のOracle版と構成に照らして検証する。
Oracle固有には`DBMS_XPLAN`・実行統計・利用可能な待機/セッション統計を用い、SQL Monitor/AWR等は提供状況とライセンス条件を確認する。RAC利用時のsequence cacheと並列書込競合、parallel DML・direct path・NOLOGGINGの性能対redo/耐久性/復旧の交換条件、DDLの暗黙COMMITを確認する。記事のOracle寄り経験則を他製品や全ワークロードへ無条件適用せず、検証結果とCAT Gateを区別する。
