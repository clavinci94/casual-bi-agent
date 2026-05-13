"""Slack incoming-webhook integration for high-priority alerts.

Pattern: when a recommendation lands with risk_level == "high", we push a
manager-readable message into a Slack channel with a deep-link back to
the dashboard. No-op when SLACK_WEBHOOK_URL isn't configured.

We never raise inside the notify path — Slack outages must not block the
agent loop or the audit write.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from biq.config import settings

_logger = logging.getLogger(__name__)


def notify_recommendation(
    rec_id: str,
    title: str,
    body: str,
    risk_level: str,
    confidence: float | None = None,
) -> bool:
    """Send a Slack message about a new recommendation.

    Returns True on success, False if disabled or upstream failed.
    """
    webhook = settings.slack_webhook_url
    if not webhook:
        return False

    risk_label = {
        "high": ":rotating_light: DRINGEND",
        "medium": ":warning: Beachten",
        "low": ":information_source: Hinweis",
    }.get(risk_level, risk_level)

    link = f"{settings.dashboard_public_url.rstrip('/')}/recommendations/{rec_id}"

    # Body kürzen — Slack-Messages werden bei >3000 Zeichen abgeschnitten,
    # und Manager scrollen sowieso nicht weit
    short_body = body.strip()
    if len(short_body) > 600:
        short_body = short_body[:580].rstrip() + " …"

    confidence_str = (
        f"  ·  *{int(confidence * 100)} % Sicherheit*" if confidence is not None else ""
    )

    payload: dict[str, Any] = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Neue Empfehlung · {title}"[:150]},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"{risk_label}{confidence_str}"},
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": short_body}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Ansehen und entscheiden"},
                        "url": link,
                        "style": "primary",
                    }
                ],
            },
        ],
        "text": f"Neue Empfehlung: {title}",  # fallback for clients without block kit
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                webhook, content=json.dumps(payload), headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()
        return True
    except Exception as exc:
        _logger.warning("slack notify failed: %s", exc)
        return False


def notify_test() -> bool:
    """Smoke-test for the configured webhook. Returns True if Slack accepted."""
    return notify_recommendation(
        rec_id="test-12345",
        title="Test-Nachricht von causal-bi",
        body=(
            "Worum geht es: Dies ist eine Test-Nachricht, ausgelöst durch "
            "`make slack-test`. Wenn Sie das in Ihrem Slack-Channel sehen, "
            "funktioniert die Integration.\n\n"
            "Datenbasis: keine — reiner Setup-Test.\n\n"
            "Vorschlag: keinen — Sie können diese Nachricht ignorieren."
        ),
        risk_level="low",
        confidence=1.0,
    )
