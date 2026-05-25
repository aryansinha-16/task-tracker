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


def upload_media(pdf_bytes: bytes, filename: str = "tasks.pdf") -> str:
    """Upload a PDF to WhatsApp media API and return the media_id."""
    upload_url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/media"
    resp = requests.post(
        upload_url,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"messaging_product": "whatsapp", "type": "application/pdf"},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"WhatsApp media upload error {resp.status_code}: {resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"WhatsApp media upload error: {data['error']}")
    return data["id"]


def send_whatsapp_pdf(to: str, pdf_bytes: bytes, filename: str = "tasks.pdf", caption: str = "") -> None:
    """Upload a PDF and send it as a document message."""
    media_id = upload_media(pdf_bytes, filename)
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
        },
    }
    if caption:
        payload["document"]["caption"] = caption
    _post(payload)


def upload_image(image_bytes: bytes, filename: str = "tasks.png") -> str:
    """Upload a PNG to WhatsApp media API and return the media_id."""
    upload_url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/media"
    resp = requests.post(
        upload_url,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        files={"file": (filename, image_bytes, "image/png")},
        data={"messaging_product": "whatsapp", "type": "image/png"},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"WhatsApp image upload error {resp.status_code}: {resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"WhatsApp image upload error: {data['error']}")
    return data["id"]


def _send_image_template(to: str, media_id: str, template_name: str, body_params: list[str], language: str = "en") -> None:
    _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": [
                {
                    "type": "header",
                    "parameters": [{"type": "image", "image": {"id": media_id}}],
                },
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in body_params],
                },
            ],
        },
    })


def send_whatsapp_image_template(
    to: str,
    image_bytes: bytes,
    template_name: str,
    assignee_name: str,
    date_str: str,
    language: str = "en",
) -> None:
    """Two-variable template: {{1}} = name, {{2}} = date. Used for assignees (daily_task_summary)."""
    media_id = upload_image(image_bytes)
    _send_image_template(to, media_id, template_name, [assignee_name, date_str], language)


def send_task_assign_notification(to: str, assignee_name: str, description: str, due_date: str, language: str = "en") -> None:
    """Send task_assign template — no image, text only. {{1}}=name {{2}}=task {{3}}=due date."""
    _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": "task_assign",
            "language": {"code": language},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": assignee_name},
                        {"type": "text", "text": description},
                        {"type": "text", "text": due_date or "Not set"},
                    ],
                }
            ],
        },
    })


def send_whatsapp_rk_template(
    to: str,
    image_bytes: bytes,
    template_name: str,
    date_str: str,
    language: str = "en",
) -> None:
    """One-variable template: {{1}} = date. Used for RK (rk_task_summary)."""
    media_id = upload_image(image_bytes)
    _send_image_template(to, media_id, template_name, [date_str], language)
