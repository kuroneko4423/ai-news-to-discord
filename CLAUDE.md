# CLAUDE.md

このファイルは Claude Code (claude.ai/code) がこのリポジトリで作業する際に参照するガイドラインです。

---

## プロジェクト概要

複数のRSSフィードからAI関連ニュースを取得し、Claude Code GitHub Actions で要約して Discord に自動投稿するワークフロー。

- **実行基盤**: GitHub Actions (毎日 09:00 JST)
- **要約**: `anthropics/claude-code-action@v1` を使用 (Claude Max サブスクリプション認証)
- **投稿**: Discord Webhook 経由で **Embed 形式**

詳細は [README.md](./README.md) と [docs/](./docs/) 配下の各ドキュメントを参照。

---

## アーキテクチャ概観

3ジョブのパイプライン。各ジョブは GitHub Actions のアーティファクト経由で疎結合に連携する。

```
fetch-news (Python)         summarize (Claude Code Action)         notify-discord (Python)
news_fetcher.py        →    news.json → summary.json         →    discord_notifier.py
RSS → news.json             (Embed投稿用の構造化要約)               summary.json → Discord Embed
```

### 主要モジュール

| ファイル | 役割 |
|---|---|
| [news_fetcher.py](./news_fetcher.py) | RSS取得・カテゴリ分類・news.json出力。RSS定義は `RSS_FEEDS` 定数 |
| [discord_notifier.py](./discord_notifier.py) | summary.json を Discord Embed に変換して送信。`build_embed()` / `batch_embeds()` / `DiscordNotifier.send_summary_json()` |
| [main.py](./main.py) | ローカル統合実行用。Anthropic SDK でフォールバック要約 |
| [.github/workflows/post-news.yml](./.github/workflows/post-news.yml) | 3ジョブ構成のワークフロー定義 |

### summary.json スキーマ

Claude が出力する要約データの形式。`discord_notifier.py` がこれを Embed に変換する。

```json
{
  "date": "2026-05-07",
  "count": 12,
  "items": [
    {
      "category": "general" | "research" | "vendor",
      "title": "...",
      "url": "https://...",
      "source": "ITmedia AI+",
      "region": "jp" | "global",
      "summary": "日本語1〜2文の要約"
    }
  ]
}
```

スキーマを変更する場合は **3箇所を同期** する：
1. `.github/workflows/post-news.yml` のプロンプト
2. `main.py` の `SUMMARY_PROMPT_TEMPLATE`
3. `discord_notifier.py` の `build_embed()` が読むキー

### Discord Embed 設計

| カテゴリ | 色 (10進) | 色 (16進) |
|---|---|---|
| general | 3447003 | `#3498db` (青) |
| research | 10181046 | `#9b59b6` (紫) |
| vendor | 3066993 | `#2ecc71` (緑) |

Discord仕様の制約：
- 1メッセージあたり最大 **10 embeds** / 合計 **6000文字**
- title 256文字 / description 4096文字 / footer.text 2048文字

→ `batch_embeds()` が自動で複数メッセージに分割する。

---

## 開発ワークフロー

### ローカル動作確認

```bash
python -m venv venv
source venv/bin/activate  # Windowsは venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # .env を編集 (ANTHROPIC_API_KEY, DISCORD_WEBHOOK_URL)
python main.py
```

ローカル実行は Anthropic API キーで動作する簡易フォールバック。本番動作の確認は GitHub Actions の `workflow_dispatch` を使う。

### よく行う変更

- **RSSフィードの追加/削除**: [news_fetcher.py](./news_fetcher.py) の `RSS_FEEDS` 定数を編集
- **要約プロンプトの調整**: [.github/workflows/post-news.yml](./.github/workflows/post-news.yml) の `prompt:` ブロック (本番) と [main.py](./main.py) の `SUMMARY_PROMPT_TEMPLATE` (ローカル) を**両方**変更
- **取得件数の調整**: ワークフローの `PER_FEED_LIMIT` / `TOTAL_LIMIT` 環境変数
- **Embedの見た目調整**: [discord_notifier.py](./discord_notifier.py) の `CATEGORY_COLORS` / `build_embed()`

### 認証方式

GitHub Actions では **Claude Max サブスクリプション** の OAuth トークンを使用：

- Secret 名: `CLAUDE_CODE_OAUTH_TOKEN`
- 取得方法: ローカルで `claude setup-token` を実行
- API キー従量課金に切り替えたい場合は、ワークフローの該当行をコメントアウトされた `anthropic_api_key` 行に差し替える

---

## コミット規約

[Conventional Commits](https://www.conventionalcommits.org/ja/) ベース、個人開発向け簡略化版。

### フォーマット

```
<type>: <subject>
```

- **type** は英語小文字 / **subject** は日本語 / 1行目 50文字以内 / 末尾に句読点なし
- 命令形・体言止めで簡潔に

### type 一覧

| type | 用途 |
|---|---|
| feat | 新機能の追加 |
| fix | バグ修正 |
| docs | ドキュメントのみの変更 |
| style | 動作に影響しない整形 |
| refactor | 機能変更を伴わないコード変更 |
| perf | パフォーマンス改善 |
| test | テスト追加・修正 |
| build | ビルドシステム・依存関係 |
| ci | CI/CD 設定変更 |
| chore | その他雑務 |
| revert | コミット取り消し |
| wip | 作業途中 (個人開発用) |

### 迷いどころ

- **feat vs fix**: ユーザー視点で「新しくできること」なら feat、「壊れていたものが直った」なら fix
- **chore vs build**: 依存パッケージ・ビルド設定は build、それ以外の雑務は chore
- **複数 type にまたがる場合**: メイン変更に合わせる。大きすぎるならコミット分割

---

## ドキュメント運用ルール

### Notionページとの同期

プロジェクトの最新仕様および変更履歴を、以下のNotionページに集約する：

**🔗 [AI News to Discord (Notion)](https://www.notion.so/AI-News-to-Discord-359367739cf78170aa64c600be7cacc3)** (ID: `359367739cf78170aa64c600be7cacc3`)

ページは2つの役割を持つ：

- **最新仕様セクション** (アーキテクチャ・データフロー・運用手順): リポジトリ側 (`README.md` / `docs/`) と整合するよう **同期更新**
- **変更履歴セクション** (実装記録): 機能リリース単位で **追記**（過去ログは削除しない）

#### 更新タイミング

以下のいずれかに該当したら更新する：

- **新機能の追加** (例: Embed投稿対応、新規RSSフィード追加、認証方式変更など)
- **アーキテクチャ・データフロー変更** (例: ジョブ構成変更、`summary.json` スキーマ変更)
- **外部仕様変更** (Discord投稿レイアウト、要約プロンプト、Secret名、ワークフロー入力など)
- **運用手順への影響** (デプロイ・トラブルシューティング・必要権限の変化)

逆に、内部リファクタ・タイポ修正・コメント調整など外部から見て変化がない変更ではNotion更新は不要。
**「PR 1 本ごと」では更新しない**（粒度が細かすぎる）。複数PRをまたぐ機能完成のタイミングでまとめる。

#### 更新の進め方

1. **リポジトリ側を先に最新化**
   - `README.md` / `docs/` 配下のMarkdownを変更内容に合わせて更新
   - これがNotion更新の正本（source of truth）になる

2. **対象PRの範囲を確認**
   - Notion 変更履歴セクションの最後のエントリ（`## YYYY-MM-DD — <タイトル>` の最大日付）から、最新マージ分までが追記対象
   - PR一覧: `gh pr list --state merged --limit 30 --json number,title,mergedAt,headRefName --jq 'sort_by(.mergedAt) | .[] | "#\(.number)\t\(.mergedAt[0:10])\t\(.headRefName)\t\(.title)"'`
   - コミット詳細: `git log <prev>..<latest> --oneline`
   - PR本文: `gh pr view <number>`

3. **Notionページを更新**
   - **最新仕様セクション**: 該当箇所をリポジトリ側の最新内容に差分更新（全置換しない）
   - **変更履歴セクション**: 末尾に下記フォーマットで追記（既存エントリは編集しない）

     ```markdown
     ## YYYY-MM-DD — <変更タイトル>

     **対象PR**: #N (#M, #L) / **コミット**: <short-sha>..<short-sha>

     一行サマリ（外部から見て何が変わったか）。

     ### 主な変更
     - 機能・ファイル単位で箇条書き
     - 新規追加 / 仕様変更 / 削除を明記

     ### 設計判断・申し送り（該当する場合）
     - なぜこの実装にしたか（A案/B案で迷った理由など）
     - 既知の制約・想定リスク
     - 次回以降に持ち越したスコープ
     ```

4. **Notion側にしかない情報 (議事録・タスク・関連リンクなど) は壊さない**

5. 大きな変更の場合は、Notion更新の旨を PR 本文や作業ログに記録する

#### 記録に含めるべき情報

PRタイトルから読み取れる表面的な情報だけでなく、**後から「なぜこの実装になったか」を辿れる情報**を残す：

- **設計判断の理由**（複数案から1つを選んだ根拠）
- **ハマった点と解決策**（Discord API の制約、Claude Code Action の挙動など）
- **次回以降への申し送り**（スコープ外として明示的に外したもの）
- **本番動作で確認した挙動**（GitHub Actions 上でしか再現しないもの）

#### Claude Code が自動で更新する場合

ユーザーから「Notionも更新して」「ドキュメントを揃えて」等の指示を受けたとき、Claude は **Notion MCP ツール** (`notion-fetch` / `notion-update-page` 等) を使って上記ページを更新してよい。ただし：

- **更新前に必ず `notion-fetch` で対象ページを読み、構造を把握してから書き換える**
- 既存内容を全置換しない（最新仕様セクションは差分更新、変更履歴セクションは末尾追記）
- 過去の変更履歴エントリは削除・編集しない（履歴として残す）
- 認可エラーが出たら、ユーザーに Notion MCP の権限付与（インテグレーション接続）を依頼する

#### 注意点

- ページの **URL・ID を変更しない**（CLAUDE.md からの参照が壊れる）。ページの移動・リネームが必要な場合はこのファイルの参照も同時更新する
- Notion ID は URL の末尾ハイフン以降のハッシュ部分: `https://www.notion.so/AI-News-to-Discord-XXXX` の `XXXX`
- メモリ (`memory/MEMORY.md`) に保存した知見と Notion 記録の内容は整合させる

---

## やってはいけないこと

- `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` / `DISCORD_WEBHOOK_URL` などの **シークレットを平文で コミット・出力しない**
- `news.json` / `summary.json` を git 管理に含めない (実行成果物のため)
- 要約プロンプトを変更したまま **本番ワークフローとローカル `main.py` の片方だけ更新しない** (常に両方同期)
- ワークフローのプロンプトと `discord_notifier.py` の Embed キー (category/title/url/source/region/summary) を片方だけ変更しない
- `--no-verify` 等で git hook をスキップしない (ユーザーが明示指示した場合を除く)
