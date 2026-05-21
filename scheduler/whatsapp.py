"""
WhatsApp Cloud API sender — uses free-form text messages.
Requires the recipient to have messaged the business number within the last 24h.
"""

import os
import requests

WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "1124409430751461")
API_URL = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"


def send_whatsapp(to: str, body_text: str) -> None:
    """
    Send a free-form WhatsApp text message.
    `to` must be a phone number with country code, no '+' (e.g. '916361742805').
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body_text[:4096]},
    }

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
