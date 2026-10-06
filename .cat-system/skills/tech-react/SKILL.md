---
name: tech-react
description: "Implement or test React component state, props, effects, and user-visible transitions against approved PI/TCE contracts. Use only for a component documented as using React and Work that touches React UI behavior."
---

# React UI boundary work

1. Confirm the adopted React version, rendering setup, router/state/form libraries, and build/test entry points from project technical documents and current source. Do not introduce conventions that the project has not adopted.
2. Map PI input/output/absence/null/error semantics to props, component state, context, and external payloads. React state and props are implementation boundaries, not replacements for runtime validation at external boundaries.
3. Map TCE Trigger -> Condition -> Effect to user events and observable render/output changes. Keep render calculation free of externally observable side effects and use the project's established effect/event boundary for synchronization.
4. Separate component-level evidence from browser, API, and persistence evidence. Combine this skill with the adopted unit/E2E/data skill for the boundary actually exercised, and record what was observed.
