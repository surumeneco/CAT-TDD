---
name: tdd-execution
description: "Run deterministic CAT-TDD execution from confirmed TestModel through a lifecycle-only Queue, one current executable test, Red/Green evidence and minimal implementation. Use for normative TDD cycles without introducing a second specification."
---

# Model → Queue → Current Test → Red → Green

## Queue

`cat_compile_v2.py queue`はconfirmed TestModelとconcrete vectorsから`cat-tdd-queue/v1`を生成する。Queue itemが保持できるのは`id / model_ref / vector_ref / order / status / evidence_ref`だけで、Scenario、Expected Result、Oracle、Condition、Effectを記述しない。

`scripts/cat_queue.py`だけが`pending / current / done / blocked`を遷移させる。`current`は最大1件。

## Executable test

`cat_compile_v2.py tests --queue ...`はQueueのcurrent item 1件だけをframework testへrenderする。normative pathではQueue無しのtest generationを禁止する。Renderer非対応をAI-written testで回避せず、renderer/binding改善Workへ分離する。

## Red / Green

Red/Green/回帰の事実は`cat_flow.py run`がexecution evidenceとして記録する。Greenと回帰のpassにReviewer Agentは不要。

Red対象が失敗した事実は機械判定し、失敗理由の意味だけが確定不能な時に`tdd-checker`へ限定委譲する。

## Implementation

標準cycleで通常起動するLLM Agentは`tdd-implementer`だけとする。current itemと固定oracleを満たす最小production変更だけを許可し、spec / TestModel / Queue / test / evidenceを変更させない。

Green後はQueue State Managerがcurrentをdoneにし、次のpendingをcurrentにする。Refactorはこのcycleの必須後段ではない。
