#!/usr/bin/env python3
"""
ローカル実行用エントリポイント

本番(GitHub Actions)では以下の3ジョブで実行されます:
  1. fetch-news    : news_fetcher.py が news.json を生成
  2. summarize     : claude-code-action@v1 が news.json を読んで summary.md を生成
  3. notify-discord: discord_notifier.py が summary.md を Discord に投稿

ローカルでも全フローを通したいケース(動作確認用)のため、
要約ステップは Anthropic API を直接呼ぶ簡易実装でフォールバックします。
要約のプロンプトは .github/workflows/post-news.yml と揃えてあります。
"""
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from news_fetcher import main as fetch_news_main
from discord_notifier import DiscordNotifier


SUMMARY_PROMPT_TEMPLATE = """\
あなたはAIニュースを日本のビジネス読者向けに要約する編集者です。
以下のJSONはRSSから取得した直近のAI関連ニュース一覧です。

{news_json}

このJSONを読み、Discordチャンネルへの投稿用Markdownを作成してください。

# 出力フォーマット
- 冒頭に1行で「📅 {today} のAIニュース ({count}件)」と書く
- カテゴリごと(general / research / vendor)にセクションを分ける
  - セクション見出しは ## general / ## research / ## vendor (該当があるもののみ)
- 各記事は次のフォーマット:
  - **[タイトル](URL)** — 出典 / 地域(jp|global)
  - 日本語で1〜2文の要約
- 全体で2000文字程度を目安にする(超えても可)
- 絵文字は控えめに、リンクは必ず保持する
"""


def run_local_summarize(news_json_path: str, summary_path: str) -> bool:
    """
    ローカル動作確認用: Anthropic APIを直接呼んで要約。
    本番(GitHub Actions)では claude-code-action@v1 がこのステップを担う。
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print(
            "❌ anthropic パッケージが必要です: pip install anthropic",
            file=sys.stderr,
        )
        return False

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY が設定されていません", file=sys.stderr)
        return False

    news_json = Path(news_json_path).read_text(encoding="utf-8")
    import json

    news_data = json.loads(news_json)

    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        news_json=news_json,
        today=datetime.now().strftime("%Y-%m-%d"),
        count=news_data.get("count", 0),
    )

    print("🧠 Anthropic APIで要約を生成中...")
    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    summary_text = "".join(
        block.text for block in message.content if hasattr(block, "text")
    )

    Path(summary_path).write_text(summary_text, encoding="utf-8")
    print(f"✅ {summary_path} に要約を保存しました")
    return True


def main() -> int:
    print("=" * 80)
    print("🤖 AI News to Discord (Local Runner)")
    print("=" * 80)

    load_dotenv()

    news_path = "news.json"
    summary_path = "summary.md"

    # Step 1: ニュース取得
    print("\n[1/3] ニュース取得")
    print("-" * 80)
    os.environ.setdefault("NEWS_OUTPUT_PATH", news_path)
    if fetch_news_main() != 0:
        return 1

    # Step 2: 要約 (ローカルではAnthropic API直接呼び出し)
    print("\n[2/3] ニュース要約 (ローカル: Anthropic API直接呼び出し)")
    print("-" * 80)
    if not run_local_summarize(news_path, summary_path):
        return 1

    # Step 3: Discord投稿
    print("\n[3/3] Discord投稿")
    print("-" * 80)
    try:
        notifier = DiscordNotifier()
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    body = Path(summary_path).read_text(encoding="utf-8").strip()
    if not body:
        print("⚠️  要約が空のため投稿をスキップ")
        return 0

    success = notifier.send_markdown(body)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
