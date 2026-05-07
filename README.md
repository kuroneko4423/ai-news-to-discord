# AI News to Discord

複数のRSSフィードからAI関連ニュースを取得し、**Claude Code GitHub Actions** で要約して **Discord** に自動投稿するワークフロー。

## 概要

このリポジトリは GitHub Actions 上で 1 日 1 回(09:00 JST)動作し、以下のフローを実行します。

```
┌──────────────────┐    ┌──────────────────────────┐    ┌──────────────────┐
│  fetch-news      │ -> │  summarize               │ -> │  notify-discord  │
│  (Python)        │    │  (Claude Code Action)    │    │  (Python)        │
│  RSS -> news.json│    │  news.json -> summary.md │    │  Discord Webhook │
└──────────────────┘    └──────────────────────────┘    └──────────────────┘
```

各ジョブは GitHub Actions の **アーティファクト** で受け渡しを行うため疎結合です。

## 技術スタック

- **Python 3.11**
- **feedparser**: RSSフィード解析
- **requests**: HTTP通信(Discord Webhook)
- **GitHub Actions**: ワークフロー実行基盤
- **anthropics/claude-code-action@v1**: 要約生成(GitHub Actions上で動作)
- **anthropic** Python SDK: ローカル動作確認時のみ使用

## プロジェクト構造

```
.
├── .github/
│   └── workflows/
│       └── post-news.yml      # 3ジョブ構成のCI/CD定義
├── docs/
│   ├── README.md              # ドキュメント索引
│   ├── architecture.md        # アーキテクチャ説明
│   ├── design.md              # 設計詳細
│   └── deployment.md          # セットアップ・デプロイ手順
├── news_fetcher.py            # ニュース取得 (job 1)
├── discord_notifier.py        # Discord投稿 (job 3)
├── main.py                    # ローカル統合実行スクリプト(任意)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## ニュース取得元

| カテゴリ | フィード | 地域 |
|---|---|---|
| general | ITmedia AI+ | 国内 |
| general | ZDNET Japan AI | 国内 |
| general | TechCrunch AI | 海外 |
| general | The Verge AI | 海外 |
| research | MIT Technology Review (AI) | 海外 |
| vendor | Google AI Blog | 海外 |
| vendor | OpenAI Blog | 海外 |

カテゴリ・フィードは `news_fetcher.py` の `RSS_FEEDS` 定数で容易に追加・変更できます。

## セットアップ

### 1. GitHub リポジトリの Secrets 設定

リポジトリの **Settings → Secrets and variables → Actions** から以下を登録します。

| Secret 名 | 用途 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code Action による要約生成用 (サブスク認証) |
| `DISCORD_WEBHOOK_URL` | Discord 投稿先 Webhook URL |

#### Claude Code OAuth Token の取得
Claude Pro / Max プランのサブスクリプション利用枠で動かすため、APIキーではなくOAuthトークンを使います。

```bash
# Claude Code を最新版にインストール / 更新
npm install -g @anthropic-ai/claude-code

# Pro / Max アカウントでログイン (まだの場合)
claude /login

# 1年間有効な OAuth トークンを発行
claude setup-token
# → ターミナルにトークンが表示される (1度しか表示されないのですぐコピー)
```

> **個人利用前提**: このプロジェクトのOAuthトークン運用は「投稿先のDiscordチャンネルを自分1人だけが見る」前提です。複数人が利用するチャンネルへ配信する場合はAnthropicの利用規約上 APIキー方式 (`ANTHROPIC_API_KEY`) または Team / Enterprise プランへの移行が必要です。

#### Discord Webhook URL の取得
1. 投稿先のDiscordチャンネルを開く
2. 歯車アイコン（チャンネル設定）→「連携サービス」→「ウェブフック」
3. 「新しいウェブフック」を作成し、「ウェブフックURLをコピー」

### 2. ワークフローの確認

`.github/workflows/post-news.yml` がリポジトリにコミットされていれば、自動的に以下のスケジュールで動作します。

- **定期実行**: 毎日 00:00 UTC (= 09:00 JST)
- **手動実行**: GitHub UI の Actions タブ →「Post AI News to Discord」→「Run workflow」

### 3. ローカル動作確認(任意)

ローカルで全フローを試したい場合のみ、以下を行います。

```bash
# 仮想環境
python -m venv venv
source venv/bin/activate

# 依存パッケージ
pip install -r requirements.txt

# 環境変数
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY と DISCORD_WEBHOOK_URL を設定

# 実行
python main.py
```

> **Note**: ローカル実行時の要約は Anthropic API を直接呼び出す簡易実装で行います（`claude-code-action` は GitHub Actions ランナー専用のため）。本番動作の確認は GitHub Actions で `workflow_dispatch` を使ってください。

## ワークフローの詳細

### Job 1: `fetch-news`
- `news_fetcher.py` を Python 3.11 で実行
- 7つのRSSフィードを並列取得し、URL重複を除去
- カテゴリ別にグルーピングして `news.json` を生成
- `news-json` という名前でアーティファクトにアップロード
- 取得0件なら後続ジョブをスキップ

### Job 2: `summarize`
- `news-json` アーティファクトをダウンロード
- `anthropics/claude-code-action@v1` を起動 (**サブスクリプション認証**)
- `prompt` 入力でClaudeに「news.jsonを読んで、指定フォーマットでsummary.mdを書け」と指示
- `Read,Write,Bash` ツールを許可することでファイル操作を可能にする
- 生成された `summary.md` を `summary-md` アーティファクトとしてアップロード

### Job 3: `notify-discord`
- `summary-md` アーティファクトをダウンロード
- `discord_notifier.py` で Discord Webhook に投稿
- 2000文字制限を超える場合は改行位置で自動分割
- 429（レート制限）受信時は `retry_after` 秒待機してリトライ

## カスタマイズ

### ニュース取得元の追加
`news_fetcher.py` の `RSS_FEEDS` リストに辞書を追加するだけです。

```python
{
    "name": "新しいフィード",
    "url": "https://example.com/feed.xml",
    "region": "jp",          # "jp" or "global"
    "category": "general",   # "general" / "research" / "vendor" など任意
}
```

### 取得件数の調整
`.github/workflows/post-news.yml` の `Fetch news` ステップの env で調整：

```yaml
env:
  PER_FEED_LIMIT: "3"   # 各フィードからの最大取得数
  TOTAL_LIMIT: "15"     # 全体の最大件数
```

### 要約フォーマットの変更
`.github/workflows/post-news.yml` の `Generate summary with Claude Code Action` ステップ内 `prompt:` を編集します。フォーマット仕様はそこに自然言語で書かれているので、編集者がプロンプトを調整するだけで出力が変わります。

### 実行頻度の変更
`.github/workflows/post-news.yml` の `schedule.cron` を編集：

```yaml
on:
  schedule:
    - cron: "0 0 * * *"   # 毎日 09:00 JST
    # - cron: "0 0 * * 1-5"   # 平日のみ
    # - cron: "0 */6 * * *"   # 6時間ごと
```

## トラブルシューティング

| 症状 | 原因 / 対処 |
|---|---|
| `fetch-news` で取得0件 | 各RSSフィードがリーチャブルか確認。Actions ログのフィード別取得数を確認 |
| `summarize` が失敗 | `CLAUDE_CODE_OAUTH_TOKEN` のSecret登録漏れ、トークン期限切れ(1年)、サブスク利用枠超過 |
| `summary.md` が生成されない | プロンプトの「Write ツールで保存」指示が効いているか、`claude_args` で `Write` 許可が抜けていないか |
| `notify-discord` で 401/404 | `DISCORD_WEBHOOK_URL` が誤り / Webhook削除済み |
| Discord で文字化け | 日本語が UTF-8 で送られていることを確認(本実装では `requests.post(json=...)` で自動対応) |

## 詳細ドキュメント

- [システム設計書](./docs/design.md)
- [アーキテクチャ](./docs/architecture.md)
- [セットアップ・デプロイ手順](./docs/deployment.md)
- [ドキュメント索引](./docs/README.md)

## ライセンス

MIT License
