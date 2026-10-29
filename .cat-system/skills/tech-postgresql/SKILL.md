---
name: tech-postgresql
description: "Review and test PostgreSQL schema, SQL, migrations and transaction boundaries against approved CAT data and behavior contracts. Use only for Work involving a documented PostgreSQL component; follow its selected database tooling."
---

# PostgreSQL data-boundary verification

1. 使用DB版、migration/ORM/SQL実行方式、テストDB、ロール権限、適用手順を技術構成正本と現行repoから確認する。
2. PIの型・null/欠損・一意性・参照整合性とTCEの永続化Effectを、schema・SQL・API境界へ対応付ける。DBでしか保証できない不変条件を抽出する。
3. migrationは既存データ、backfill、default、制約追加、rollback可否、複数componentへの波及を確認。実データを勝手に消去しない。
4. transaction/競合/失敗後の状態を、規範に含まれる場合にテストする。実DBとmockの検証範囲を混同しない。
5. 実行したmigration/testと対象DBを証拠化する。成功したschema変更だけでアプリ全体の仕様適合とみなさない。

## DB性能・I/O・競合のレビュー

DBアクセス・クエリ・大量書込み・Migration・性能改善を扱うWorkでは、[共通の8観点と実測・例外規則](../../../.cat-system/docs/DB性能設計・検証.md)を適用する。逐次COMMIT対COPY/バルク処理、並列writerの競合、索引数とwrite amplification、sequence対UUIDとB-tree局所性、selectivityと統計・値の偏り、ホット行UPDATE、行の幅、DB側JOIN/WHERE/GROUP BYとORMのN+1を**当該Workで関連する範囲に限って**調査する。
PostgreSQL固有の検証には安全なDBでの実行計画・`EXPLAIN (ANALYZE, BUFFERS)`、索引統計、`pg_stat_activity`/ロック待ち、利用可能なら`pg_stat_statements`を用いる。`EXPLAIN ANALYZE`は変更SQLを実際に実行すること、`CREATE INDEX CONCURRENTLY`の制限、VACUUM/更新負担、トランザクション内の`TRUNCATE`がロールバック可能なこととロック・MVCC上の制約を混同しない。実測条件と規範上の整合性・失敗復旧要求を別々に記録し、性能改善だけをCAT Gate成功としない。
