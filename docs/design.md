# AI News to Discord — システム設計書

## 1. システム概要

### 1.1 目的
複数の国内外RSSフィードからAI関連ニュースを取得し、Claude Code GitHub Actions で日本語に要約し、Discord チャンネルへ自動投稿する。

### 1.2 主要機能
- 7つのRSSフィードからの並列取得・URL重複排除・カテゴリ分類
- Claude Code GitHub Actions による日本語要約(Markdown)
- Discord Webhook による Embed/Markdown 投稿(2000文字制限の自動分割対応)
- 毎日定刻 + 手動トリガーによる実行

## 2. モジュール設計

### 2.1 `news_fetcher.py`

| 項目 | 内容 |
|---|---|
| 役割 | RSS取得・正規化・JSON出力 |
| 入力 | 環境変数 `NEWS_OUTPUT_PATH`, `PER_FEED_LIMIT`, `TOTAL_LIMIT` |
| 出力 | `news.json` |
| 主要クラス | `NewsFetcher`, `NewsItem` (dataclass) |
| 主要メソッド | `fetch_all(per_feed_limit, total_limit)`, `group_by_category(items)` |

設定可能なRSSフィードは `RSS_FEEDS` 定数で定義。各フィードは `name / url / region / category` を持つ。

### 2.2 `discord_notifier.py`

| 項目 | 内容 |
|---|---|
| 役割 | Markdown本文を Discord Webhook へ投稿 |
| 入力 | 環境変数 `DISCORD_WEBHOOK_URL`, `SUMMARY_PATH`, `DISCORD_HEADER`(任意) |
| 出力 | Discord メッセージ |
| 主要クラス | `DiscordNotifier` |
| 主要メソッド | `send_markdown(markdown_body, header, username)` |

仕様:
- 2000文字制限を考慮し `MAX_CONTENT_LENGTH = 1900` で切り出し
- 改行位置を優先してチャンク分割し、改行が見つからなければ強制カット
- 429 受信時は `retry_after` 秒待ってリトライ(最大3回・指数バックオフ)
- `allowed_mentions: {parse: []}` で `@everyone` などの誤爆を防止

### 2.3 `main.py` (ローカル統合実行スクリプト)

本番では使われないが、ローカル動作確認用に3ステップ統合スクリプトを提供。要約ステップは `claude-code-action` がGitHub Actionsランナー専用のため、Anthropic API SDK を直接呼ぶ簡易実装でフォールバックする。プロンプト本文は GitHub Actions ワークフローの `prompt:` と揃えてあるので、ローカル動作と本番動作の差異は最小化される。

## 3. データフロー

```
RSS Feeds (7 sources)
        │
        ▼
┌────────────────────┐   news.json (artifact)
│  fetch-news Job    │ ───────────────────────┐
│  Python 3.11       │                        │
└────────────────────┘                        │
                                              ▼
                              ┌─────────────────────────────┐
                              │  summarize Job              │
                              │  claude-code-action@v1      │
                              │  prompt: news.json を読んで  │
                              │  summary.md を Write         │
                              └─────────────────────────────┘
                                              │
                                              │ summary.md (artifact)
                                              ▼
                              ┌─────────────────────────────┐
                              │  notify-discord Job         │
                              │  Python 3.11                │
                              │  Discord Webhook へ POST    │
                              └─────────────────────────────┘
```

## 4. JSON スキーマ (`news.json`)

```json
{
  "fetched_at": "2026-05-07T00:00:00+00:00",
  "count": 12,
  "categories": {
    "general":  [ /* NewsItem... */ ],
    "research": [ /* NewsItem... */ ],
    "vendor":   [ /* NewsItem... */ ]
  },
  "items": [
    {
      "title": "...",
      "link": "https://...",
      "summary": "...(最大300文字)...",
      "published": "Wed, 07 May 2026 09:00:00 +0900",
      "source": "ITmedia AI+",
      "region": "jp",
      "category": "general",
      "fetched_at": "2026-05-07T00:00:00+00:00"
    }
  ]
}
```

## 5. プロンプト設計 (`claude-code-action` 入力)

要約プロンプトは GitHub Actions ワークフロー (`.github/workflows/post-news.yml`) の `Generate summary with Claude Code Action` ステップに記述。要点:

1. **役割**: 「日本のビジネス読者向けAI編集者」
2. **入力**: ワーキングディレクトリの `news.json`
3. **タスク**: Read → 理解 → Discord用Markdown作成 → `summary.md` に Write
4. **出力フォーマット**: 1行ヘッダ + カテゴリ別セクション + 各記事Markdown
5. **制約**: タイトル/URL改変禁止、JSONにない情報の創作禁止、2000〜3500文字目安

`claude_args` で `--allowedTools Read,Write,Bash` `--max-turns 10` を指定。Read/Writeを許可することでファイル操作を可能にしている。

## 6. エラーハンドリング

| ジョブ | エラー | 挙動 |
|---|---|---|
| fetch-news | 個別RSSの取得失敗 | 警告ログ → 当該フィードはスキップして処理継続 |
| fetch-news | 全0件 | `outputs.has_news=false` を出力 → 後続ジョブをスキップ |
| summarize | API失敗 / プロンプト失敗 | `claude-code-action` がジョブを失敗させる |
| summarize | `summary.md` 未生成 | 検証ステップで `exit 1` → 後続をスキップ |
| notify-discord | 429 (レート制限) | `retry_after` 秒待機 → リトライ |
| notify-discord | 5xx / ネットワーク | 指数バックオフで最大3回リトライ |

## 7. 環境変数仕様

### 7.1 ローカル実行 (`.env`)

| 変数 | 必須 | 用途 |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | ✅ | Discord 投稿先 |
| `ANTHROPIC_API_KEY` | ✅ | ローカル要約用 (本番は GitHub Secret) |
| `ANTHROPIC_MODEL` | — | デフォルト `claude-sonnet-4-5` |
| `NEWS_OUTPUT_PATH` | — | デフォルト `news.json` |
| `PER_FEED_LIMIT` | — | デフォルト 3 |
| `TOTAL_LIMIT` | — | デフォルト 15 |
| `SUMMARY_PATH` | — | デフォルト `summary.md` |
| `DISCORD_HEADER` | — | 投稿先頭に付けるヘッダ |

### 7.2 GitHub Actions Secrets

| Secret | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | `claude-code-action@v1` の認証 |
| `DISCORD_WEBHOOK_URL` | `notify-discord` ジョブの投稿先 |

## 8. 拡張ポイント

| 拡張 | 変更箇所 |
|---|---|
| RSSフィード追加 | `news_fetcher.py` の `RSS_FEEDS` |
| 取得件数調整 | `.github/workflows/post-news.yml` env |
| 要約フォーマット変更 | ワークフローの `prompt:` 本文 |
| 投稿先プラットフォーム追加 | `xxx_notifier.py` を新規作成し、Job 3 のスクリプトを差し替え |
| 実行頻度の変更 | ワークフローの `schedule.cron` |
| カテゴリ追加 | `RSS_FEEDS` の `category` 値とプロンプトの見出し列挙を更新 |
