---
name: tech-pytest
description: "Generate, review, and execute pytest tests from approved CAT TestModels while preserving parameter coverage, fixture isolation, plugin boundaries, and TDD evidence."
---


# pytest test realization


1. Confirm pytest version, configuration, plugins, markers, async support, test command, and result-report path from project files and technical documents.
2. Map TestModel partitions and TCE cases to tests/parametrized rows with expected outcomes derived from confirmed CAT artifacts, not from implementation output. Preserve CAT traceability where the project supports it.
3. Keep fixture scope, autouse behavior, temporary files, environment changes, and shared state isolated; do not create hidden ordering dependencies.
4. Use async/database/framework plugins only when adopted by the project and required by the tested boundary. Mark mocked versus real external dependencies explicitly in the evidence.
5. Record Red/Green/regression with the project-approved command and JUnit XML/results when configured, including the exact selected test scope.