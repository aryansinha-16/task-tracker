"""
Scheduler entry point.
Runs daily at 9 AM IST to send email digests.
Also triggers the fortnightly stale-task review.

Deploy on Railway or Render as a long-running process.
"""

import logging
import os
import sys
from datetime import datetime, timezone, timedelta

import time

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
    if tasks:
        try:
            img = generate_task_image(tasks, title="Daily Task Summary")
            send_whatsapp_rk_template(
                RK_PHONE, img, WA_TEMPLATE_RK,
                date_str=date_str,
            )
            log.info(f"Sent image digest to RK ({RK_PHONE})")
        except Exception as e:
            log.error(f"Failed to send image digest to RK: {e}")
    else:
        try:
            send_whatsapp(RK_PHONE, f"No open tasks as of {today.strftime('%d %b %Y')}. All clear!")
            log.info("Sent all-clear to RK")
        except Exception as e:
            log.error(f"Failed to send all-clear to RK: {e}")

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
            try:
                send_whatsapp(RK_PHONE, prompt)
                log.info(f"Sent stale task review prompt ({len(stale)} tasks)")
            except Exception as e:
                log.error(f"Failed to send stale review WhatsApp: {e}")

    log.info("Daily digest run complete.")


def main():
    # If --run-now flag passed (for testing), fire immediately and exit
    if "--run-now" in sys.argv:
        log.info("--run-now flag detected, sending digest immediately.")
        send_daily_digest()
        return

    log.info("Scheduler started. Will send digest at 04:00-04:15 UTC (09:30-09:45 IST) each day.")
    last_run_date = None

    while True:
        now_utc = datetime.now(timezone.utc)
        # Fire at 03:30 UTC, but only once per day even if process restarts
        if now_utc.hour == 4 and 0 <= now_utc.minute <= 15 and last_run_date != now_utc.date():
            last_run_date = now_utc.date()
            log.info(f"Firing daily digest for {last_run_date}")
            send_daily_digest()

        time.sleep(60)


if __name__ == "__main__":
    main()
