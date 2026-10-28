# CAT-TDD for VS Code GitHub Copilot

Read `AGENTS.md` for the common CAT-TDD contract. The shared procedural source is `.cat-system/docs/`, the stage authorization source is `.cat-system/config/routing.json`, and actual checks/guards run through `.cat-system/scripts/`.

Copilot discovers scoped roles in `.github/agents/` and applicable skills in `.github/skills/`. Only Work-selected technology skills and explicitly selected adapters may be installed; do not discover or apply all technologies by default. Use one of four independent CAT-TDD flows; let deterministic executors own TestModel, Queue, tests and evidence. Agent guidance alone does not enforce permissions.
