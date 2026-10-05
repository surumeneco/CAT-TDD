# CAT-TDD

CAT / Cycle / TDD を使って任意の開発対象を運用するためのワークスペーステンプレートです。

## 最短の開始手順

```bash
git clone https://github.com/surumeneco/CAT-TDD.git
cd CAT-TDD
git clone <target-repository-url> Room0/<repository-name>
```

その後、この **CAT-TDD ルート**を VS Code / Copilot で開きます。開発対象のソースコードは `Room0/<repository-name>/` に置き、CAT-TDD 側の Lifecycle / Docs / TestModels と分離して扱います。

`Room0/*` と `RoomN/*` は親 CAT-TDD リポジトリの Git 管理対象外です。対象リポジトリはそれぞれ自身の `.git` で管理し、CAT-TDD の commit に混入させません。

## 主な配置

```text
.github/                  Copilot が直接探索する共通 Agent / Skill
.cat-system/              CAT runtime・文書・全 Skill pool
Lifecycle/
  Issues/{New,InProgress,Blocked,Completed,Cancelled}/
  Tasks/{New,InProgress,Blocked,Completed,Cancelled}/
  Works/{New,InProgress,Blocked,Completed,Cancelled}/
  CAT/{Candidates,Draft,Reviews}/
  TDD/Results/
  REF/Scopes/
Docs/
  Constraints/
  Processes/
TestModels/
Room0/                    開発対象 repo。親 Git では完全に ignore
RoomN/                    作業用 worktree。親 Git では完全に ignore
```

Lifecycle 状態の正本は Issue / Task / Work の配置フォルダです。ID は移動しても変更しません。

## Git 境界

CAT-TDD 自身の変更はルートで Git 操作します。開発対象の Git 操作は必ず対象 repo / worktree を明示します。

```bash
git status
git -C Room0/<repository-name> status
git -C RoomN/<worktree-name> status
```

通常の `git add .` を CAT-TDD ルートで行っても `Room0/*` / `RoomN/*` の内容は追加されません。強制追加 (`git add -f`) はこの分離を破壊するため使用しないでください。

## Skill の扱い

共通 Skill は最初から `.github/skills` に配置されています。技術固有の `tech-*` Skill は `.cat-system/skills` の pool に保持し、Work で採用技術が確定した後に `.cat-system/scripts/cat_install.py` が選択導入します。未採用技術の Skill を最初から Copilot の探索対象へ混在させません。

詳細な契約は `.cat-system/docs/` を参照してください。
