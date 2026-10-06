# CAT-TDD

CAT / Cycle / TDD を使って任意の開発対象を運用するためのワークスペーステンプレートです。

## 最短の開始手順

```bash
git clone https://github.com/surumeneco/CAT-TDD.git
cd CAT-TDD
git clone <target-repository-url> Room0/<repository-name>
```

その後、この **CAT-TDD ルート**を VS Code / Copilot で開きます。開発対象のソースコードは `Room0/<repository-name>/` に置き、CAT-TDD 側の Lifecycle / Docs / TestModels と分離して扱います。

`Room0/**` と `RoomN/**` に加え、`Lifecycle/**`、トップレベル `Docs/**`、`TestModels/**` は親 CAT-TDD リポジトリの Git 管理対象外です。CAT-TDD はテンプレートと共通実行環境だけを管理し、個別プロジェクトのソースコード・仕様Artifact・Work・TestModel等を commit に混入させません。各ディレクトリ自体は追跡済み `.gitkeep` により clone 直後から存在します。

## 新規開発の入口

通常の新規要求では、人間が与える開発要求の単位は **Issue** です。Issueは `Lifecycle/Issues/New/<issue>/issue.md` に直接記述しても、会話上の要求をAIがIssueとして整理しても構いません。人間にCAT/TDDのProcess分割やTask/Workの手作成を要求しません。

新規Issueを受け付けたAIは、orchestratorから `cycle-scope-divider` へ委譲し、**Issue → Task（Process責務）→ Work（独立して仕様化・検証できる仕様差分）**へ分解します。意味上の選択が不足する場合だけ人間へ判断を返し、分解作業そのものを人間へ差し戻しません。

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

通常の `git add .` を CAT-TDD ルートで行っても、`Room0/**` / `RoomN/**` / `Lifecycle/**` / `Docs/**` / `TestModels/**` のプロジェクト固有内容は追加されません。さらに、プロジェクトごとに選択導入される `.github/skills/tech-*`、`.github/skills/*-adapter`、`.cat-system/extensions/**` も親Gitから除外されます。強制追加 (`git add -f`) はこの分離を破壊するため使用しないでください。

## Skill の扱い

共通 Skill は最初から `.github/skills` に配置されています。技術Skill（自作 `tech-*` および `routing.json` に登録した外部Skill）は `.cat-system/skills` の pool に保持し、Work で採用技術が確定した後に `.cat-system/scripts/cat_install.py` が選択導入します。未採用技術の Skill を最初から Copilot の探索対象へ混在させません。

詳細な契約は `.cat-system/docs/` を参照してください。


## 親CAT-TDDが追跡しないもの

次は個別プロジェクトまたはローカル環境に属するため、CAT-TDDのGit管理対象外です。

- `Lifecycle/**`: Issue / Task / Work、CAT Candidate/Draft/Review、TDD/REF結果
- `Docs/**`: 個別プロジェクトのConstraintsとconfirmed Process仕様
- `TestModels/**`: 個別プロジェクトから導出されたTestModel
- `Room0/**` / `RoomN/**`: 対象repoとworktree
- `.github/skills/<selected-technology-skill>` / `*-adapter`: 個別Workで選択されたCopilot Skill
- `.cat-system/extensions/**`: プロジェクト固有adapter
- `.cat-flow/**`: 実行証拠・一時状態
- `.env*`、仮想環境、cache、coverage、build/temp/log、IDE/OSローカル状態

一方、`.cat-system/skills/` 内の `routing.json` 登録済み技術Skillは利用可能な技術Skillの**テンプレート側pool**なので追跡対象です。個別プロジェクトが実際に採用したものだけが `.github/skills/` へ展開され、その展開結果はignoreされます。
