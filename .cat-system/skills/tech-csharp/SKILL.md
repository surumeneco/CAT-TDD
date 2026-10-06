---
name: tech-csharp
description: "Implement or test C# code with project-defined language, nullable, async, exception, serialization, and build constraints while preserving CAT PI/TCE behavior."
---

# C# implementation / diagnostics

1. Confirm the C# language version, target .NET SDK/framework, nullable settings, project/solution boundaries, package management, and build/test commands from project files and technical documents.
2. Map PI input/output/absence/null/error semantics to public types, nullable annotations, exceptions, cancellation, async results, and serialization boundaries. Nullable annotations are compile-time diagnostics and do not replace runtime validation.
3. Preserve public API, exception, cancellation, disposal, and asynchronous ordering semantics required by TCE. Do not hide behavioral changes inside type or refactor cleanup.
4. Run the project-approved build, analyzer/lint, and test commands for the affected project/solution and record their scope as evidence. Compiler success is not evidence for external I/O or deployment behavior.
