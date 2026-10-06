---
name: tech-java
description: "Implement or test Java code with project-defined JDK, build, null/error, concurrency, resource, and API constraints while preserving CAT PI/TCE behavior."
---

# Java implementation / diagnostics

1. Confirm the JDK/release level, build tool, module/package structure, encoding, dependency management, and build/test commands from project files and technical documents.
2. Map PI input/output/absence/null/error semantics to Java types, Optional usage where already adopted, exceptions, conversions, and serialization boundaries. Static types do not replace runtime validation.
3. Preserve public API, exception, interruption/cancellation, transaction, concurrency, and resource-lifetime semantics required by TCE. Do not change them as incidental cleanup.
4. Run the project-approved compiler/build, static analysis, and test commands through the adopted Maven/Gradle/project entry point and record the executed scope.
