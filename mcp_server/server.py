"""
Remote MCP server for RK's task tracker.
Transport: StreamableHTTP (POST /mcp/<secret>)
Compatible with Claude.ai desktop and web integrations.
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import Tool, TextContent

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


# ── Tool implementations ─────────────────────────────────────────────────────

def add_task(args: dict) -> str:
    assignee = args.get("assignee", "").strip()
    description = args.get("description", "").strip()
    due_date = args.get("due_date", "").strip()

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


def close_task(args: dict) -> str:
    identifier = args.get("task_id", "").strip() or args.get("description_hint", "").strip()
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


def list_tasks(args: dict) -> str:
    assignee_filter = args.get("assignee", "").strip().lower()
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


# ── MCP Server ───────────────────────────────────────────────────────────────

def make_mcp_server() -> Server:
    server = Server("task-tracker")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name="add_task",
                description="Log a new task assigned by RK to a direct report. Call this whenever RK says he told someone to do something.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "assignee": {"type": "string", "description": "First name of the assignee (e.g. Mahendra, Mali, Rehan)."},
                        "description": {"type": "string", "description": "What the person needs to do."},
                        "due_date": {"type": "string", "description": "Optional due date in YYYY-MM-DD format."},
                    },
                    "required": ["assignee", "description"],
                },
            ),
            Tool(
                name="close_task",
                description="Mark a task as closed when RK says someone has completed their work.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "8-character task ID if known."},
                        "description_hint": {"type": "string", "description": "Keyword from the task description to find it."},
                    },
                },
            ),
            Tool(
                name="list_tasks",
                description="Show all open tasks, grouped by assignee. Optionally filter by one person.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "assignee": {"type": "string", "description": "Filter by first name. Leave blank for everyone."},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "add_task":
            result = add_task(arguments)
        elif name == "close_task":
            result = close_task(arguments)
        elif name == "list_tasks":
            result = list_tasks(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
        return [TextContent(type="text", text=result)]

    return server


# ── Starlette app ─────────────────────────────────────────────────────────────

async def handle_mcp(request: Request) -> None:
    secret = request.path_params.get("secret", "")
    if MCP_SECRET and secret != MCP_SECRET:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    mcp_server = make_mcp_server()
    transport = StreamableHTTPServerTransport(mcp_path=f"/mcp/{secret}")

    async with mcp_server.run_with_transport(transport) as (read_stream, write_stream):
        await transport.handle_request(request.scope, request.receive, request._send)


async def health(request: Request):
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/health", health),
        Route("/mcp/{secret}", handle_mcp, methods=["POST", "GET"]),
    ]
)
