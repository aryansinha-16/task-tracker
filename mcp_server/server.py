"""
Remote MCP server for RK's task tracker.
Transport: StreamableHTTP via FastMCP
Served at: /mcp  (FastMCP internal path also set to /mcp, mounted at root)
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

try:
    from sheets import append_task, update_task_status, list_open_tasks
except ModuleNotFoundError:
    from mcp_server.sheets import append_task, update_task_status, list_open_tasks

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

IST = timezone(timedelta(hours=5, minutes=30))
MCP_SECRET = os.environ.get("MCP_SECRET", "")


def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


# ── FastMCP server ────────────────────────────────────────────────────────────
# streamable_http_path="/mcp" means FastMCP's inner Starlette serves at /mcp.
# We mount that inner app at "/" so no prefix is stripped, and /mcp reaches it intact.

mcp = FastMCP("task-tracker", streamable_http_path="/mcp")


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


# ── Route handlers ────────────────────────────────────────────────────────────

async def health(request: Request):
    return JSONResponse({"status": "ok"})


async def oauth_protected_resource(request: Request):
    return JSONResponse({"resource": "/mcp", "bearer_methods_supported": ["header"]})


async def oauth_authorization_server(request: Request):
    return JSONResponse({"error": "not_supported"}, status_code=404)


# ── App assembly ──────────────────────────────────────────────────────────────
# Mount FastMCP's inner app at "/" so it receives full paths (including /mcp).
# Our own routes for /health and /.well-known are listed first so they win.

mcp_asgi = mcp.streamable_http_app()

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
        Route("/.well-known/oauth-protected-resource/{path:path}", oauth_protected_resource),
        Route("/.well-known/oauth-authorization-server", oauth_authorization_server),
        Mount("/", app=mcp_asgi),
    ],
)
