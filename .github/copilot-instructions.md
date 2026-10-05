# CAT-TDD workspace instructions

This repository is the CAT-TDD control workspace. The actual product repositories live under `Room0/`; isolated worktrees live under `RoomN/`.

- Do not treat code observed in Room0/RoomN as specification authority. Existing code and tests may produce CAT candidates only until semantic authority confirms them.
- Use `.cat-system/docs/` as the common CAT/Cycle/TDD operating contract.
- Use the common agents and skills already exposed under `.github/`. Technology-specific `tech-*` skills remain in `.cat-system/skills/` until a Work declares that technology and the installer selects it.
- Lifecycle state is the containing directory: `New`, `InProgress`, `Blocked`, `Completed`, or `Cancelled`. Move the entire stable-ID Issue/Task/Work directory when state changes; do not duplicate lifecycle state in front matter.
- Prefer exploration by lifecycle directory: new intake from `Lifecycle/Issues/New/`, resumable work from `Lifecycle/Works/InProgress/`, and external/semantic waits from `Lifecycle/Works/Blocked/`. Do not scan Completed by default.
- CAT semantic authority belongs in confirmed artifacts under `Docs/Processes/` (or an explicitly linked external authority). Draft/candidate material stays under `Lifecycle/CAT/`.
- Keep implementation constraints under `Docs/Constraints/`; do not leak framework/repository mechanics into Process/PI/TCE semantics.
- Root Git is for the CAT-TDD template/runtime only. Project-specific artifacts under `Lifecycle/`, top-level `Docs/`, and `TestModels/`, product code under `Room0/` / `RoomN/`, selected `.github/skills/tech-*` / `*-adapter`, `.cat-system/extensions/`, and `.cat-flow/` are intentionally ignored by the parent repository. For product code, always scope Git to the nested repository/worktree (for example `git -C Room0/<repo> ...` or `git -C RoomN/<worktree> ...`). Never force-add ignored project-local content to CAT-TDD.
- Before implementation, identify or create the relevant Issue → Task → Work, obtain current specification/repository evidence, and follow the gates in `.cat-system/docs/開発フロー.md`.
- Unknown semantic choices must be blocked/escalated rather than inferred from implementation convenience.
