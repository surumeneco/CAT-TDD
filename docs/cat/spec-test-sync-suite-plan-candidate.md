---
cat_version: '0.3'
kind: domain-spec
id: cat-tdd.spec-test-sync.suite-plan-prototype
status: candidate
process: cat-tdd.spec-test-sync
source_refs:
  - https://drive.google.com/file/d/1l73dJkpggDA96MT4st9Ha-NIwdEXNLSW/view
  - https://drive.google.com/file/d/1RsJI_z4C3QBI5iPZy0v1vFiKRXM37zWB/view
  - https://drive.google.com/file/d/1FaXcWNoBd2WRzkhHc16rSKREGVDwtdh4/view
refs: []
semantic_contract: markdown-v2
language: ja
---

# spec-test-sync: pure suite plan semantics (Candidate)

## Scope and authority

This is a **non-normative Candidate for the pure planner algorithm**, now called by the separately guarded `cat_spec_test_sync.py` implementation on a feature branch. It is not a Confirmed CAT Semantic Artifact or a test oracle. The original four flows retain their Red/Green contract and TDD Queue unchanged. Actual synchronization requires current Confirmed source, process-closure/model-conformance evidence, safe file ownership and a pinned repository revision; none is granted by the planner itself.

The companion `cat_suite_plan_candidate.py` is a pure function returning an ordered **proposal** from caller-supplied metadata. It never reads or changes the filesystem or Git, never invokes a renderer, and cannot execute tests. Consequently its caller must separately prove that the input source/model/vector hashes, confirmed specification, Git revision, and observed disk hashes are authentic and fresh before any future authorized sync.

## Candidate decisions for review

| ID | Candidate | Direct test |
| --- | --- | --- |
| STS-SP-01 | A target path absent on disk and in Manifest is `create`; an owned generated file with matching recorded hash and all pinned source/renderer hashes is `unchanged`. | `test_empty_owned_namespace_creates_no_files_or_tdd_queue`, `test_matching_owned_generated_test_is_unchanged` |
| STS-SP-02 | A generated-owned file whose disk hash still matches the Manifest but expected output differs is an `update` proposal only; it is not automatically overwritten. | `test_owned_hash_change_proposes_update_without_touching_disk` |
| STS-SP-03 | Unknown/manual ownership and local modification or deletion of recorded owned files are `blocked` rather than overwritten or silently recreated. | `test_unowned_path_cannot_be_replaced_even_if_hash_matches`, `test_modified_owned_file_and_missing_owned_file_are_blocked` |
| STS-SP-04 | Old generated records outside the current desired selection are retained, never deleted as a side effect of plan construction. | `test_stale_generated_unselected_files_are_retained_not_deleted` |
| STS-SP-05 | Duplicate desired IDs/paths and duplicate Manifest IDs across **generated and handwritten** owners are rejected. A handwritten record retaining a test ID at another path blocks generated creation under that ID; malformed hashes, forged oracle fields, unsafe paths, and unknown ownership also fail closed. | `test_duplicate_test_ids_paths_and_oracle_fields_fail_closed`, `ManifestIdentityCollision` (4 regressions), `test_absolute_parent_and_backslash_paths_fail_closed`, `test_invalid_hash_and_ambiguous_manifest_owner_fail_closed` |
| STS-SP-06 | Entries are sorted deterministically and caller collections are unmodified; there is no Queue or test-execution status in the proposal. | `test_sorted_results_independent_of_input_order`, other tests |
| STS-SP-07 | Planner target paths, observed disk paths, Manifest keys, and generated namespace prefixes containing ASCII control codes (U+0000–U+001F, U+007F) are rejected before emitting any proposal. Ordinary nested Unicode paths remain valid. This is an *inactive Candidate guard*, not a confirmed path policy or active renderer change. | `CandidateControlPathBoundary` (5 methods, including negative subtests) |

## Deliberately unresolved

The Manifest field names, source provider and Vitest compiler/renderer integration are implemented by `cat_spec_test_sync.py` and `cat_suite_manifest.py`; this pure planner alone still neither proves semantic closure nor produces CAT Gate evidence. It does not claim conformance to authoritative Process/PI/TCE or validate a confirmed oracle. Future implementation must use the existing TestModel/compiler/vector selector rather than creating a second independent source of semantics. Handwritten tests and existing TDD Queue must remain protected. A green planner unit test alone never authorizes normative promotion, Green status, develop merge or production-code edits.

## Evidence classification

A local `python -m unittest -v test_suite_plan_candidate` Red->Green run characterizes this candidate implementation. Even if the isolated Python unit tests pass, normative CAT Gate and full `spec-test-sync` acceptance remain `not-run` until separately executed and verified.
