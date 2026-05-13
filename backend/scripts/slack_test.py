"""Smoke-test for the Slack webhook configured in .env.

    uv run python scripts/slack_test.py
"""

from __future__ import annotations

import sys

from biq.config import settings
from biq.integrations import slack


def main() -> None:
    if not settings.slack_webhook_url:
        print("SLACK_WEBHOOK_URL ist nicht in .env gesetzt.")
        print(
            "Eine Incoming-Webhook-URL anlegen: "
            "https://api.slack.com/messaging/webhooks"
        )
        sys.exit(1)

    ok = slack.notify_test()
    if ok:
        print("✓ Test-Nachricht erfolgreich gesendet. Schauen Sie in den Slack-Channel.")
    else:
        print("✗ Slack hat den Webhook abgelehnt. Logs im Backend prüfen.")
        sys.exit(2)


if __name__ == "__main__":
    main()
