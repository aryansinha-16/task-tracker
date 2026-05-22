"""
WhatsApp Cloud API sender.
- send_whatsapp: free-form text (only works within 24h window)
- send_whatsapp_template: template message (works anytime)
"""

import os
import requests

WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "1124409430751461")
API_URL = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"


def _post(payload: dict) -> None:
    resp = requests.post(
        API_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"WhatsApp API error {resp.status_code}: {resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"WhatsApp API error: {data['error']}")


def send_whatsapp(to: str, body_text: str) -> None:
    """Free-form text — requires recipient to have messaged in last 24h."""
    _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body_text[:4096]},
    })


def send_whatsapp_template(to: str, template_name: str, parameters: list[str], language: str = "en") -> None:
    """Send a template message. `parameters` is an ordered list of variable values."""
    _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in parameters],
                }
            ],
        },
    })
