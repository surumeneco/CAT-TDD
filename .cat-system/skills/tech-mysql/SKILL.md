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
