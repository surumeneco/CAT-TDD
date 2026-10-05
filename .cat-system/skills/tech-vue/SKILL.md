---
name: tech-vue
description: "Implement or test Vue component reactivity, form bindings, emitted events and UI state transitions against approved PI/TCE contracts. Use only for a component documented as using Vue and for Work touching Vue UI behavior."
---

# Vue UI boundary work

1. コンポーネント構成、Vue版、使用するrouting/state管理/フォーム部品を採用技術文書と現行ソースから確認する。特定ライブラリの存在を仮定しない。
2. PIの入力表現とUI state、props、emits、API payloadを別々に記述する。`v-model`などの入力は、DOMから実際に渡る値・空欄・型変換を確認する。
3. TCEのTrigger→Condition→Effectを、ユーザ操作と観測結果へ対応させる。hidden stateやCSS構造を仕様へ勝手に追加しない。
4. 採用済みUIテストの技術Skillを併用し、コンポーネント単体では見えないブラウザ→API等の境界は必要な統合観測で検証する。
