"""
Discord通知モジュール

Discord Incoming Webhook経由で、Claude Code GitHub Actionsが生成した
要約Markdownを投稿します。Discordの2000文字/1メッセージ制限に対応するため、
長文は自動分割して送信します。
"""
import json
import os
import sys
import time
from typing import List, Optional

import requests


class DiscordNotifier:
    """Discord Webhookにメッセージを送信するクラス"""

    # Discordのcontent最大長は2000文字
    MAX_CONTENT_LENGTH = 1900  # ヘッダ等の余白を考慮して少し小さく
    REQUEST_TIMEOUT_SEC = 15
    RETRY_COUNT = 3

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        if not self.webhook_url:
            raise ValueError(
                "Discord Webhook URL is required. "
                "Set DISCORD_WEBHOOK_URL environment variable."
            )

    @staticmethod
    def _split_message(text: str, max_len: int) -> List[str]:
        """
        Markdownメッセージをmax_len以下のチャンクに分割。
        改行を尊重して、できるだけ自然な箇所で切る。
        """
        if len(text) <= max_len:
            return [text]

        chunks: List[str] = []
        remaining = text
        while len(remaining) > max_len:
            # 直近のmax_len内で最後の改行を探す
            split_pos = remaining.rfind("\n", 0, max_len)
            if split_pos == -1 or split_pos < max_len // 2:
                # 改行が見つからないか、極端に短い位置なら強制カット
                split_pos = max_len
            chunks.append(remaining[:split_pos].rstrip())
            remaining = remaining[split_pos:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks

    def _post(self, payload: dict) -> bool:
        """1メッセージをPOST。リトライ付き。"""
        for attempt in range(1, self.RETRY_COUNT + 1):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT_SEC,
                )
                # 429(レート制限)はretry_after秒待つ
                if response.status_code == 429:
                    retry_after = float(
                        response.json().get("retry_after", 1.0)
                    )
                    print(
                        f"⏳ Rate limited. Retrying after {retry_after}s "
                        f"(attempt {attempt}/{self.RETRY_COUNT})"
                    )
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return True

            except requests.exceptions.RequestException as e:
                print(
                    f"❌ Discord send error (attempt {attempt}/{self.RETRY_COUNT}): {e}",
                    file=sys.stderr,
                )
                if attempt < self.RETRY_COUNT:
                    time.sleep(2 ** attempt)  # 指数バックオフ
        return False

    def send_markdown(
        self,
        markdown_body: str,
        header: Optional[str] = None,
        username: str = "AI News Bot",
    ) -> bool:
        """
        Markdown本文をDiscordに送信。長文は自動分割。

        Args:
            markdown_body: 送信するMarkdown本文
            header: 先頭に付けるヘッダ(任意)
            username: Webhook表示ユーザ名

        Returns:
            すべてのチャンクが成功したらTrue
        """
        if header:
            full_text = f"{header}\n\n{markdown_body}"
        else:
            full_text = markdown_body

        chunks = self._split_message(full_text, self.MAX_CONTENT_LENGTH)
        print(f"📤 {len(chunks)}メッセージに分割して送信します")

        all_ok = True
        for idx, chunk in enumerate(chunks, 1):
            payload = {
                "username": username,
                "content": chunk,
                # @mentionの誤爆を防止
                "allowed_mentions": {"parse": []},
            }
            ok = self._post(payload)
            status_icon = "✅" if ok else "❌"
            print(f"   {status_icon} メッセージ {idx}/{len(chunks)}")
            all_ok = all_ok and ok
            # 連投はレート制限を踏みやすいので少し間隔を置く
            if idx < len(chunks):
                time.sleep(0.5)

        return all_ok


def main() -> int:
    """CLIエントリポイント。要約Markdownファイルを読み込んでDiscordへ投稿。"""
    summary_path = os.environ.get("SUMMARY_PATH", "summary.md")
    header = os.environ.get("DISCORD_HEADER")  # ない場合はNone

    if not os.path.exists(summary_path):
        print(f"❌ 要約ファイルが見つかりません: {summary_path}", file=sys.stderr)
        return 1

    with open(summary_path, "r", encoding="utf-8") as f:
        markdown_body = f.read().strip()

    if not markdown_body:
        print("⚠️  要約ファイルが空です。投稿をスキップします。")
        return 0

    print("=" * 80)
    print("📤 Discord Notifier - 要約をDiscordに投稿")
    print("=" * 80)
    print(f"要約ファイル: {summary_path} ({len(markdown_body)}文字)")

    try:
        notifier = DiscordNotifier()
    except ValueError as e:
        print(f"❌ 設定エラー: {e}", file=sys.stderr)
        return 1

    success = notifier.send_markdown(markdown_body, header=header)

    if success:
        print("\n🎉 すべてのメッセージ送信に成功しました。")
        return 0
    else:
        print("\n❌ 一部メッセージの送信に失敗しました。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
