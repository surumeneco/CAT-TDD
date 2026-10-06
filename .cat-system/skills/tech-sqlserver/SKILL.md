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
