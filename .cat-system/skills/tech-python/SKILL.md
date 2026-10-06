---
name: tech-python
description: "Implement or test Python code with project-defined runtime, typing, exception, async, resource, serialization, and packaging constraints while preserving CAT PI/TCE behavior."
---

# Python implementation / diagnostics

1. Confirm the Python version, environment/package manager, dependency manifest, type/lint configuration, package layout, and test commands from project files and technical documents.
2. Map PI input/output/absence/None/error semantics to runtime data shapes, exceptions, async behavior, and serialization boundaries. Type annotations do not replace runtime validation.
3. Preserve exception, cancellation, context-manager/resource, mutability, and data-shape semantics required by TCE. Validate dynamic external inputs at the boundary established by the project.
4. Run the project-approved interpreter/type/lint/test commands in the declared environment and record the actual target and environment as evidence.
