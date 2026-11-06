# CAT Compiler semantic extension — implementation evidence

This branch is based on CAT-TDD commit `60284c440ababea93e915eec4056f8cc2fbdc4a1`.

## Verification contract

- The canonical Compiler must retain every declared Process, PI, TCE, CommonRule and DomainSpec as hashed inputs.
- Typed records, sequences, sets, unions, byte sequences and nullable values must not be coerced to strings.
- Presence and nullability are independent. Missing, explicit null, undefined and actual values are not interchangeable.
- Partial or open-world contracts are never promoted to full Process closure.
- A CommonRule or DomainSpec author-authored verifier contract is not execution evidence.
- External capabilities (DB, DOM, Discord, BlueMap) must be attributed to the correct verifier; a DOM check cannot establish Discord delivery.
- Independent Model Conformance must compare source semantics with the generated TestModel and distinguish semantic inventory correspondence from complete closure.
- Downstream vector generation must fail closed when a test oracle or typed representation is unsupported.

## revision9 validation boundary

The MineCraftXPlayWebApp revision9 Assembly has 84 selected Artifacts across 12 Processes, including unpromoted Candidates. Read-only testing may use `--allow-draft` to produce a provisional model. Such a model is not Confirmed, and its process-closure or implementation-conformance Gate cannot be reported as passed solely because compilation succeeds.

The product repository and ChatGPT-specific adapters are out of scope.
