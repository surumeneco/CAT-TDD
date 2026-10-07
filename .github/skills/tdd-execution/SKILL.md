---
name: tdd-execution
description: "Run deterministic CAT-TDD execution from confirmed TestModel through a lifecycle-only Queue, one current executable test, Red/Green evidence and minimal implementation. Use for normative TDD cycles without introducing a second specification."
---

# Model → Queue → Current Test → Red → Green

## Queue

`cat_compile_v2.py vectors`はconfirmed TestModelから`rule-witness/v1`でdeterministic vectorsを生成し、`cat_compile_v2.py queue`がそれを`cat-tdd-queue/v1`へ変換する。normative Queue/test生成ではvector再生成一致を必須とし、手入力追加やTestModel ruleの欠落を拒否する。boolean/enum以外の非有限領域は代表値を推測せずselector改善Workへ分離する。Queue itemが保持できるのは`id / model_ref / vector_ref / order / status / evidence_ref`だけで、Scenario、Expected Result、Oracle、Condition、Effectを記述しない。

`scripts/cat_queue.py` / `cat_flow.py queue-state`だけが`pending / current / done / blocked`を遷移させる。`current`は最大1件。normative done遷移には、現在のQueue hashとcurrent item IDへ結び付いたpassed Green evidenceを要求する。

## Executable test

`cat_compile_v2.py tests --queue ...`はQueueのcurrent item 1件だけをframework testへrenderする。normative pathではQueue無しのtest generationを禁止する。Renderer非対応をAI-written testで回避せず、renderer/binding改善Workへ分離する。

## Red / Green

Red/Green/回帰の事実は`cat_flow.py run`がexecution evidenceとして記録する。Greenと回帰のpassにReviewer Agentは不要。

Red対象が失敗した事実は機械判定し、失敗理由の意味だけが確定不能な時に`tdd-checker`へ限定委譲する。

## Implementation

標準cycleで通常起動するLLM Agentは`tdd-implementer`だけとする。current itemと固定oracleを満たす最小production変更だけを許可し、spec / TestModel / Queue / test / evidenceを変更させない。

Green後は`cat_flow.py queue-state --evidence <green-evidence>`がcurrentをdoneにし、次のpendingをcurrentにする。Green時点からQueueが変わっていればstaleとして拒否する。Refactorはこのcycleの必須後段ではない。
