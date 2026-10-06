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