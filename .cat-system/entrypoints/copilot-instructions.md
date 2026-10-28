# CAT-TDD workspace instructions

This repository is the CAT-TDD control workspace. The actual product repositories live under `Room0/`; isolated worktrees live under numbered workspace directories (`Room1/`, `Room2/`, ...). Each numbered Room may contain worktrees for multiple repositories; `RoomN` is not a literal directory or repository.

- Do not treat code observed in Room0 and numbered Rooms as specification authority. Existing code and tests may produce CAT candidates only until semantic authority confirms them.
- Use `.cat-system/docs/` as the common CAT/Cycle/TDD operating contract.
- Use the common agents and skills already exposed under `.github/`. Technology-specific `tech-*` skills remain in `.cat-system/skills/` until a Work declares that technology and the installer selects it.
- Lifecycle state is the containing directory: `New`, `InProgress`, `Blocked`, `Completed`, or `Cancelled`. Move the entire stable-ID Issue/Task/Work directory when state changes; do not duplicate lifecycle state in front matter.
- Prefer exploration by lifecycle directory: new intake from `Lifecycle/Issues/New/`, resumable work from `Lifecycle/Works/InProgress/`, and external/semantic waits from `Lifecycle/Works/Blocked/`. Do not scan Completed by default.
- CAT semantic authority belongs in confirmed artifacts under `Docs/Processes/` (or an explicitly linked external authority). Draft/candidate material stays under `Lifecycle/CAT/`.
- Keep implementation constraints under `Docs/Constraints/`; do not leak framework/repository mechanics into Process/PI/TCE semantics.
- Root Git is for the CAT-TDD template/runtime only. Project-specific artifacts under `Lifecycle/`, top-level `Docs/`, and `TestModels/`, product code under `Room0/` / numbered `Room1/`, `Room2/`, ..., selected `.github/skills/tech-*` / `*-adapter`, `.cat-system/extensions/`, and `.cat-flow/` are intentionally ignored by the parent repository. For product code, always scope Git to the nested repository/worktree (for example `git -C Room0/<repo> ...` or `git -C Room1/<repo> ...`). Never force-add ignored project-local content to CAT-TDD.
- Select one independent flow from `spec-implementation / issue-work / code-to-spec / refactor`; do not concatenate them into one mandatory lifecycle. A flow handoff starts another flow explicitly.
- For a new human Issue, `cycle-scope-divider` creates Task/Work metadata including `flow / work_kind / parent / depends_on`. Use `.cat-system/scripts/cat_scope_order.py` for cycle/depth/ready ordering instead of reasoning about graph order repeatedly.
- Use `.cat-system/config/routing.json` as the execution contract. If a stage executor is a script/compiler/validator/provider, call it directly rather than invoking an Agent with the same responsibility label.
- Invoke conditional reviewers only for `inconclusive`. Never use AI review to overwrite a deterministic `failed/blocked` result.
- Production TestModel, TDD Queue and current executable test are compiler/state-manager owned. Do not hand-edit them or fill unsupported semantics with AI. Standard current-item TDD should normally invoke only `tdd-implementer`.
- Respect route permissions. Orchestrator is a router/permission broker, not an all-purpose writer. Agents do not edit execution evidence or promote confirmed semantics unless a separate authority explicitly owns that operation.
- Unknown semantic choices must be blocked/escalated rather than inferred from implementation convenience.
