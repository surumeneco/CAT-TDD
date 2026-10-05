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
