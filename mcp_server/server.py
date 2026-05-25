"""
Remote MCP server for RK's task tracker.
Transport: StreamableHTTP via FastMCP (FastMCP app is the top-level ASGI app)
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from sheets import append_task, update_task_status, list_open_tasks, get_assignee_directory
except ModuleNotFoundError:
    from mcp_server.sheets import append_task, update_task_status, list_open_tasks, get_assignee_directory

import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from scheduler.whatsapp import send_whatsapp, send_task_assign_notification, send_whatsapp_image_template, send_whatsapp_rk_template
from scheduler.image import generate_task_image, generate_assignee_image
from scheduler.digest import build_rk_whatsapp, build_assignee_whatsapp

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


# ── FastMCP server ────────────────────────────────────────────────────────────

mcp = FastMCP(
    "task-tracker",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def add_task(assignee: str, description: str, due_date: str = "") -> str:
    """Log a new task assigned by RK to a direct report. Call this whenever RK says he told someone to do something."""
    assignee = assignee.strip()
    description = description.strip()
    due_date = due_date.strip()

    if not assignee or not description:
        raise ValueError("assignee and description are required.")

    task_id = str(uuid.uuid4())[:8].upper()
    date_assigned = now_ist()

    append_task({
        "task_id": task_id,
        "assignee": assignee,
        "description": description,
        "date_assigned": date_assigned,
        "due_date": due_date,
        "status": "Open",
        "closed_date": "",
    })

    # Send WhatsApp notification to assignee via template
    try:
        directory = get_assignee_directory()
        phone_map = {e["name"].lower(): e["phone"] for e in directory}
        phone = phone_map.get(assignee.lower())
        if phone:
            send_task_assign_notification(phone, assignee, description, due_date)
            log.info(f"WhatsApp task_assign sent to {assignee} ({phone})")
        else:
            log.warning(f"No phone found for assignee '{assignee}' — WhatsApp not sent")
    except Exception as e:
        log.error(f"WhatsApp notification failed: {e}")

    due_str = f", due {due_date}" if due_date else ""
    return (
        f"Task logged.\n"
        f"ID: {task_id}\n"
        f"Assignee: {assignee}\n"
        f"Task: {description}{due_str}\n"
        f"Assigned: {date_assigned}"
    )


@mcp.tool()
def close_task(task_id: str = "", description_hint: str = "") -> str:
    """Mark a task as closed when RK says someone has completed their work."""
    identifier = task_id.strip() or description_hint.strip()
    if not identifier:
        raise ValueError("Provide task_id or description_hint.")

    closed_date = now_ist()
    matched = update_task_status(identifier, "Closed", closed_date)

    if not matched:
        return f"No open task found matching '{identifier}'. Check the task list."

    return (
        f"Task marked as closed.\n"
        f"Task: {matched['description']}\n"
        f"Assignee: {matched['assignee']}\n"
        f"Closed: {closed_date}"
    )


@mcp.tool()
def list_tasks(assignee: str = "") -> str:
    """Show all open tasks, grouped by assignee. Optionally filter by one person."""
    assignee_filter = assignee.strip().lower()
    tasks = list_open_tasks()

    if assignee_filter:
        tasks = [t for t in tasks if t["assignee"].lower() == assignee_filter]

    if not tasks:
        return "No open tasks." if not assignee_filter else f"No open tasks for {assignee_filter.title()}."

    today = datetime.now(IST).date()
    grouped: dict[str, list] = {}
    for t in tasks:
        grouped.setdefault(t["assignee"], []).append(t)

    lines = [f"Open tasks as of {today} ({len(tasks)} total)\n"]
    for person, person_tasks in sorted(grouped.items()):
        lines.append(f"-- {person} --")
        for t in person_tasks:
            age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
            overdue_flag = ""
            if t.get("due_date"):
                due = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
                if today > due:
                    overdue_flag = " OVERDUE"
            due_str = f" | due {t['due_date']}" if t.get("due_date") else ""
            lines.append(f"  [{t['task_id']}] {t['description']}{due_str} | {age}d old{overdue_flag}")
        lines.append("")

    return "\n".join(lines).strip()


@mcp.tool()
def send_digest() -> str:
    """Send the daily WhatsApp image digest to RK and all assignees right now."""
    RK_PHONE = os.environ.get("RK_PHONE", "916361742805")
    WA_TEMPLATE_RK    = os.environ.get("WHATSAPP_TEMPLATE_NAME_RK", "rk_task_summary")
    WA_TEMPLATE_ASSIG = os.environ.get("WHATSAPP_TEMPLATE_NAME", "daily_task_summary")

    tasks = list_open_tasks()
    directory = get_assignee_directory()
    phone_map = {e["name"].lower(): e["phone"] for e in directory}
    date_str = datetime.now(IST).strftime("%d/%m/%Y")

    sent = []
    errors = []

    # RK's master digest
    if tasks:
        try:
            img = generate_task_image(tasks, title="Daily Task Summary")
            send_whatsapp_rk_template(RK_PHONE, img, WA_TEMPLATE_RK, date_str=date_str)
            sent.append(f"RK ({RK_PHONE})")
        except Exception as e:
            errors.append(f"RK: {e}")
    else:
        try:
            send_whatsapp(RK_PHONE, "No open tasks right now. All clear!")
            sent.append(f"RK ({RK_PHONE})")
        except Exception as e:
            errors.append(f"RK: {e}")

    # Per-assignee digests
    grouped: dict[str, list] = {}
    for t in tasks:
        grouped.setdefault(t["assignee"].strip().lower(), []).append(t)

    for assignee_key, assignee_tasks in grouped.items():
        phone = phone_map.get(assignee_key)
        if not phone:
            errors.append(f"{assignee_key}: no phone found")
            continue
        display_name = assignee_tasks[0]["assignee"]
        try:
            img = generate_assignee_image(display_name, assignee_tasks)
            send_whatsapp_image_template(phone, img, WA_TEMPLATE_ASSIG, assignee_name=display_name, date_str=date_str)
            sent.append(f"{display_name} ({phone})")
        except Exception as e:
            errors.append(f"{display_name}: {e}")

    result = f"Digest sent to: {', '.join(sent)}" if sent else "No messages sent."
    if errors:
        result += f"\nErrors: {'; '.join(errors)}"
    return result


# ── Extra routes (added to FastMCP's own Starlette app so lifespan runs) ──────

@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def oauth_protected_resource(request: Request) -> JSONResponse:
    return JSONResponse({"resource": "/mcp", "bearer_methods_supported": ["header"]})


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_authorization_server(request: Request) -> JSONResponse:
    return JSONResponse({"error": "not_supported"}, status_code=404)


# ── Top-level ASGI app ────────────────────────────────────────────────────────
# Use FastMCP's own Starlette app directly so its lifespan/session manager runs.

app = mcp.streamable_http_app()
