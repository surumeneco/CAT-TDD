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

## Deterministic CAT v2 JUnit generation (bounded adapter)

`cat_compile_v2.py tests --framework junit --queue ...` selects a JUnit Jupiter source renderer while retaining the same confirmed TestModel, deterministic vectors, one-current-item Queue and source-bound oracle. Its `cat-junit-driver-binding/v1` declares `process`, `test_package`, `test_class`, and `driver_class`. The explicit driver class supplies public `prepare`, `observeState`, and `trigger` methods, checked by Java compilation, and must observe actual behavior rather than return the specification expectation. Generated classes include a deterministic vector-ID digest in the Java class name. The class is package-private (allowed by JUnit Jupiter), so an explicitly chosen `--output` Java filename need not equal the generated class name. **Use a distinct output file for each current Queue vector**; class-name uniqueness alone does not prevent overwriting files when the caller reuses one `--output` path. Naming the file after the generated class also works.

The current adapter accepts only required boolean/enum/64-bit integer scalar fields with Java map transport. It **blocks**, rather than infers or silently ignores, Presence/nullable/structured/temporal/set domains, capability fields and output-operation identity. This is a renderer limitation, not a restriction of CAT-TDD or JUnit itself. Red/Green and formal implementation-conformance still require the ordinary Work-declared checks and Script-owned evidence.
