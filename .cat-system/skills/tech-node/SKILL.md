---
name: tech-node
description: "Check adopted Node.js runtime, package engine constraints, executable entrypoints and scoped service tests. Use only for a documented Node.js component."
---

# Node.js runtime constraints

Confirm the adopted Node runtime and package engine requirement from the current technical configuration. Run the actual supported runtime against the scoped implementation and test command; do not equate package installation or TypeScript compilation with runtime success. Verify the named execution report, source and toolchain identity. Use a disposable environment for service/DB tests. `cat_node_service_technology.py` supports the bounded `>=major[.minor[.patch]]` engine contract and the live Node service probe; unknown engine expressions remain inconclusive. This does not prove PI, capability closure, arbitrary Node behavior or provider authenticity.
