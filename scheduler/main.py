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

import schedule
import time

# Allow imports from parent dirs when running standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_server.sheets import list_open_tasks, get_assignee_directory
from scheduler.digest import build_stale_review_prompt
from scheduler.pdf import generate_task_pdf, generate_assignee_pdf
from scheduler.whatsapp import send_whatsapp, send_whatsapp_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

RK_PHONE = os.environ.get("RK_PHONE", "916361742805")


def send_daily_digest():
    log.info("Starting daily digest run...")
    today = datetime.now(IST).date()

    try:
        tasks = list_open_tasks()
        directory = get_assignee_directory()
    except Exception as e:
        log.error(f"Failed to fetch data from Google Sheets: {e}")
        return

    # ── RK's master digest (PDF of all tasks) ────────────────────────────────
    if tasks:
        try:
            pdf = generate_task_pdf(tasks, title="Daily Task Summary")
            filename = f"tasks_{today.strftime('%Y%m%d')}.pdf"
            send_whatsapp_pdf(RK_PHONE, pdf, filename=filename, caption=f"Task Summary — {today.strftime('%d %b %Y')}")
            log.info(f"Sent PDF digest to RK ({RK_PHONE})")
        except Exception as e:
            log.error(f"Failed to send PDF digest to RK: {e}")
    else:
        try:
            send_whatsapp(RK_PHONE, f"No open tasks as of {today.strftime('%d %b %Y')}. All clear!")
            log.info("Sent all-clear to RK")
        except Exception as e:
            log.error(f"Failed to send all-clear to RK: {e}")

    # ── Per-assignee PDF digests ──────────────────────────────────────────────
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
            pdf = generate_assignee_pdf(display_name, assignee_tasks)
            filename = f"tasks_{display_name.lower()}_{today.strftime('%Y%m%d')}.pdf"
            send_whatsapp_pdf(phone, pdf, filename=filename, caption=f"Hi {display_name}, here are your pending tasks.")
            log.info(f"Sent PDF digest to {display_name} ({phone})")
        except Exception as e:
            log.error(f"Failed to send PDF to {display_name}: {e}")

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
    # Schedule at 09:00 IST = 03:30 UTC
    schedule.every().day.at("03:30").do(send_daily_digest)
    log.info("Scheduler started. Waiting for 03:30 UTC (09:00 IST)...")

    # If --run-now flag passed (for testing), fire immediately
    if "--run-now" in sys.argv:
        log.info("--run-now flag detected, sending digest immediately.")
        send_daily_digest()
        return

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
