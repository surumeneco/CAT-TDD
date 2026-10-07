---
title: CAT×TDD AI実行契約
status: trial
version: '1.0'
---

# CAT×TDD AI実行契約

## 原則

CAT-TDD runtimeはDeterministic Executor、Semantic AI、Normative Authority、External Evidence Providerを区別する。Roleは責務境界、Invocationは実際に起動する実行主体であり、Roleが存在するだけでLLMを起動しない。

実行順は原則として次のとおり。

~~~text
deterministic executor
  ├ passed / failed → 確定
  └ inconclusive → conditional reviewer

意味決定が必要 → normative authority
外部事実が必要 → provider
~~~

AIはScript / Compiler / Validator / Providerを推測で代替しない。機械検査の`failed`をAI reviewでpassへ上書きしない。

## Orchestrator

orchestratorはrouter / permission brokerであり、成果物作成者ではない。flow、ready scope、executor、permissions、on_resultを選び、構造化resultから次遷移を決める。

orchestrator自身にはSemantic Artifact、TestModel、Queue、tests、production source、evidence、Git integration stateの書込み権限を与えない。複数Roleのwrite setの和集合を持たせない。

## 実行権限

各stageは`routing.json`で最低限次を宣言する。加えて`evidence_policy`でexecution evidenceの所有主体、Agentによる直接編集禁止、external factのprovider必須性を機械可読に保持する。conditional Agentではexecution evidence ownerを`none`としてReview/Interpretation参照だけを許す。

| 項目 | 意味 |
| --- | --- |
| read | 参照可能なArtifact / repo / evidence |
| write | 変更可能なArtifact / source scope |
| commands | 実行可能なmechanical operation |
| authority | draft / review / implementation / integration等の権限 |
| prohibited | 明示的な禁止対象 |

Agentはroutingで与えられた権限を拡張しない。書込みを持つAgent stageは`cat_flow.py handoff`からのみ開始し、handoffがpre snapshotを作成する。conditional Reviewerも例外ではなく、`--conditional inconclusive`を指定したhandoff/guardの内側でのみ起動する。Agent終了後は`cat_flow.py guard --phase finish`を必須とし、write set外変更があればblockedとする。pending/blocked guardを再開始してbaselineを捨てることも禁止する。標準`Lifecycle/Works`配置ではguard開始時にscope-orderingを再計算し、deepest-readyでないWorkのAgent起動を拒否する。

confirmed promotion、merge、deploy等の高権限操作は通常の設計・実装Agentから分離する。confirmed promotionは明示されたnormative decisionを入力に専用authority executor `cat_promote.py`が行い、Reviewer自身は昇格しない。

## Evidence

execution evidenceはRunner / Validator / Providerが生成する。AI Agentはevidence本文を書き換えない。意味解釈が必要ならReview / Interpretation Artifactからevidenceを参照する。

`passed`は実行した検査だけに有効であり、別Gateへ伝播しない。特にGreen、CI、merge、deployment、real-useは互いに独立する。process-closure / model-conformance / implementation-conformanceはScript所有のconformance evidenceを基準とし、Work本文に`passed`と記載しただけでは成立しない。deterministic verdictが`inconclusive`の場合だけ独立Review evidenceで閉じる。

## 4つのflow

### spec-implementation

confirmed assembled specificationを入口とする。process-closure、model-conformance、implementation-conformanceを独立Gateとして扱う。

TestModelはCompiler所有、具体vectorはdeterministic test-selector所有、TDD Execution QueueはQueue Compiler / State Manager所有、generated testはRenderer所有であり、AIが直接補正しない。normative pathでは`rule-witness/v1`の再生成結果とvectorが一致しなければQueue/test生成を拒否する。機械変換不能な意味をAIでproduction oracleへ補完せずblockedとする。対象仕様にCommonRule / DomainSpecが含まれる場合も、対応するdeterministic mapping / verifierが無ければ同様に停止する。

current Queue item 1件ごとの標準TDD cycleで、原則必須のLLM invocationは`tdd-implementer`だけとする。Green evidenceはcurrent item IDとQueue hashへ結び付け、`cat_flow.py queue-state`だけがdone化と次current選択を行う。Red理由が機械判定不能な時だけ`tdd-checker`を起動する。

### issue-work

Issueの意味的Task/Work分解は`cycle-scope-divider`が行う。graphのcycle検出・depth・ready算出はScriptが行う。work kindにTDD不要なanalysis / documentation / verificationを含められる。

### code-to-spec

`cat-reverser`はCandidateと証拠だけを書く。confirmed昇格・production変更を行わない。

### refactor

`ref-scoper`が保存意味と変更範囲を決め、production変更前に`refactor-baseline`を実測する。`ref-refactor`のwrite guard開始時にbaseline evidenceと現在source contextを再照合し、staleなら起動を拒否する。`ref-refactor`はproduction sourceだけを書ける。testsと仕様は固定し、behavior change要求は別flowへ返す。

## GateとReviewer

Gate ContractとGate Executorを分離する。Gateは必須でもReviewer Agentは必須とは限らない。

- process-closure: Validator → inconclusive時だけ`cat-reviewer`
- model-conformance: Validator → inconclusive時だけ`cat-model-reviewer`
- generated test: Renderer/validator。legacy/handwritten等のinconclusive時だけ`tdd-reviewer`
- Red reason: signature等で確定できればScript。不能時だけ`tdd-checker`
- implementation-conformance: deterministic obligation skeletonの再生成一致を確認後、Queue/technology/model-conformance evidenceをAggregatorが評価 → inconclusive項目だけ`cat-implementation-reviewer`。各obligationは`method / evidenceまたはreason / limitation`を保持する

## Git / CI / integration

branch/base/diff/allowed path等のread-only Git inspectionは`cat_flow.py git`が担当する。`cycle-git-manager`を毎回起動しない。

CI / merge / deployの状態はproviderから再取得する。AIが「成功したはず」と認定しない。外部証拠をローカルevidenceへ偽装しない。

## Handoff / context

Agent切替時は全資料を毎回再読させない。`handoff`が少なくともWork/scope ID、flow/stage、normative ref + revision/hash、current Queue item、permissions、unresolved decision、必要なevidence ref、stale/changed input、next permitted actionを返す。

hash/revisionが不変なら同一実行内の全文再取得を必須にしない。外部正本の最新性が境界条件ならprovider metadataを再取得し、変更時だけ本文を更新する。

## 失敗状態

- `failed/blocked`: 契約を満たさない。Reviewerで上書きしない。
- `inconclusive`: 決定論的判定不能。定義されたconditional reviewerへ限定委譲できる。
- `decision-required`: 望ましい意味の決定が必要。Normative Authorityへ返す。
- `not-run`: 必要な環境・証拠がない。成功に昇格させない。
- `stale`: 入力・生成元・実行contextが変化した。再生成・再実行する。
