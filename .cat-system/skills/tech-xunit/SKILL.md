---
name: tech-xunit
description: "Generate, review, and execute xUnit.net tests from approved CAT TestModels while preserving partition coverage, fixture isolation, async/error semantics, and TDD evidence."
---


# xUnit.net test realization


1. Confirm the xUnit.net version, target framework, runner, project test command, parallelization settings, and result-report format from project files and technical documents.
2. Map TestModel partitions and TCE cases to Facts/Theories and data rows without deriving expected values from the implementation under test. Keep CAT IDs traceable in test names, metadata, or adjacent mapping when the project supports it.
3. Keep fixture/class/collection state and parallel execution compatible with the intended isolation boundary. Shared fixtures must not silently make tests order-dependent.
4. Test asynchronous completion, exceptions, cancellation, and boundary values with the project's established xUnit idioms; do not replace integration evidence with mocks.
5. Record Red/Green/regression using the project-approved command and machine-readable result when configured. A passing xUnit project proves only the executed test boundary.