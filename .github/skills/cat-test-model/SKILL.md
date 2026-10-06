---
name: cat-test-model
description: "Compile confirmed CAT Process/PI/TCE/domain-rule artifacts into a human-readable TestModel and validate exact source-to-model regeneration. Use for deterministic TestModel production or compiler investigation; never fill unsupported normative semantics with AI."
---

# CAT specification → TestModel

Production TestModelはconfirmed CAT仕様から`scripts/cat_compile_v2.py model`で生成する。AIがproduction TestModel本文を作成・補正しない。

1. Process / PI / TCE / DomainRuleのID、status、refs、source hashを固定する。
2. CompilerがTrigger、field、Condition、Allowed Outcome、frame condition、coverage verificationを保持したsymbolic relationを生成する。
3. `source_semantic_map`で入力Artifactの意味要素と生成要素の対応を保持する。
4. normative compileでunsupported / uncovered / unprovenが残る場合はblockedとし、意味をAIで補完しない。
5. `model-conformance`は現在のsourceからの完全再生成一致をまずValidatorで検査する。Validatorが構造上判定不能な場合だけ`cat-model-reviewer`へ委譲する。

`--allow-draft`はcompiler開発・shadow検証専用であり、production oracleの代替にしない。TestModelは派生物なので手修正せず、欠落があればcompiler/schemaを修正して再生成する。
