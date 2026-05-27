"""
Scheduler entry point.
Runs daily at 9:45 AM IST to send WhatsApp digests.
Also triggers the fortnightly stale-task review.

Deployed on Railway as a cron job: 15 4 * * * (09:45 IST daily)
Run manually: python scheduler/main.py
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

# Allow imports from parent dirs when running standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_server.sheets import list_open_tasks, get_assignee_directory
from scheduler.digest import build_stale_review_prompt
from scheduler.image import generate_task_image, generate_assignee_image
from scheduler.whatsapp import send_whatsapp, send_whatsapp_image_template, send_whatsapp_rk_template

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

RK_PHONE          = os.environ.get("RK_PHONE", "916361742805")
RK_PHONE_2        = os.environ.get("RK_PHONE_2", "")
WA_TEMPLATE_RK    = os.environ.get("WHATSAPP_TEMPLATE_NAME_RK", "rk_task_summary")
WA_TEMPLATE_ASSIG = os.environ.get("WHATSAPP_TEMPLATE_NAME", "daily_task_summary")


def send_daily_digest():
    log.info("Starting daily digest run...")
    today = datetime.now(IST).date()

    try:
        tasks = list_open_tasks()
        directory = get_assignee_directory()
    except Exception as e:
        log.error(f"Failed to fetch data from Google Sheets: {e}")
        return

    date_str = today.strftime("%d/%m/%Y")

    # ── RK's master digest (image of all tasks) ───────────────────────────────
    rk_phones = [p for p in [RK_PHONE, RK_PHONE_2] if p]
    if tasks:
        img = generate_task_image(tasks, title="Daily Task Summary")
        for phone in rk_phones:
            try:
                send_whatsapp_rk_template(phone, img, WA_TEMPLATE_RK, date_str=date_str)
                log.info(f"Sent image digest to RK ({phone})")
            except Exception as e:
                log.error(f"Failed to send image digest to RK ({phone}): {e}")
    else:
        for phone in rk_phones:
            try:
                send_whatsapp(phone, f"No open tasks as of {today.strftime('%d %b %Y')}. All clear!")
                log.info(f"Sent all-clear to RK ({phone})")
            except Exception as e:
                log.error(f"Failed to send all-clear to RK ({phone}): {e}")

    # ── Per-assignee image digests ────────────────────────────────────────────
    grouped: dict[str, list] = {}
    for t in tasks:
        grouped.setdefault(t["assignee"].strip().lower(), []).append(t)

    phone_map = {entry["name"].strip().lower(): entry["phone"] for entry in directory}

    for assignee_key, assignee_tasks in grouped.items():
        phone = phone_map.get(assignee_key)
        if not phone:
            log.warning(f"No phone for {assignee_key}, skipping")
            continue
        display_name = assignee_tasks[0]["assignee"]
        try:
            img = generate_assignee_image(display_name, assignee_tasks)
            send_whatsapp_image_template(
                phone, img, WA_TEMPLATE_ASSIG,
                assignee_name=display_name, date_str=date_str,
            )
            log.info(f"Sent image digest to {display_name} ({phone})")
        except Exception as e:
            log.error(f"Failed to send image to {display_name}: {e}")

    # ── Fortnightly stale task review (every 14 days, triggered if today is the day) ──
    day_of_year = today.timetuple().tm_yday
    if day_of_year % 14 == 0:
        stale = [
            t for t in tasks
            if (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days >= 30
        ]
        if stale:
            prompt = build_stale_review_prompt(stale)
            for phone in rk_phones:
                try:
                    send_whatsapp(phone, prompt)
                    log.info(f"Sent stale task review prompt to {phone} ({len(stale)} tasks)")
                except Exception as e:
                    log.error(f"Failed to send stale review WhatsApp to {phone}: {e}")

    log.info("Daily digest run complete.")


if __name__ == "__main__":
    send_daily_digest()
