---
name: tech-junit
description: "Generate, review, and execute JUnit Platform/Jupiter tests from approved CAT TestModels while preserving partition coverage, lifecycle isolation, parameterization, and TDD evidence."
---


# JUnit test realization


1. Confirm JUnit Platform/Jupiter versions, Maven/Gradle test plugin, tags, lifecycle, parallel settings, and result-report path from project files and technical documents.
2. Map TestModel partitions and TCE cases to tests/parameterized cases with expected outcomes derived from confirmed CAT artifacts, never from implementation output. Preserve CAT traceability where the project supports it.
3. Keep fixtures, extensions, lifecycle scope, mocks, and temporary resources isolated. Do not rely on test execution order unless the specification and project configuration explicitly require it.
4. Use Spring or other framework contexts only when the tested boundary requires them; a plain unit test should not acquire a broader context merely for convenience.
5. Record Red/Green/regression with the project-approved build command and JUnit XML/results when configured, including the exact selected test scope.