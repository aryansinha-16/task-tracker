"""
Remote MCP server for RK's task tracker.
Transport: HTTP + SSE (required for Claude.ai remote integrations).
Deploy on Railway. Add the public URL to RK's Claude.ai Settings → Integrations.

Auth: shared secret via Authorization: Bearer <MCP_SECRET> header.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    from sheets import append_task, update_task_status, list_open_tasks
except ModuleNotFoundError:
    from mcp_server.sheets import append_task, update_task_status, list_open_tasks

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

IST = timezone(timedelta(hours=5, minutes=30))
MCP_SECRET = os.environ.get("MCP_SECRET", "")  # set this in Railway env vars


def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def verify_auth(request: Request):
    if not MCP_SECRET:
        return  # no secret configured — open (only do this in dev)
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {MCP_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")


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
        f"✅ Task logged.\n"
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
        return f"⚠️ No open task found matching '{identifier}'. Check the task list."

    return (
        f"✅ Task marked as closed.\n"
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

    lines = [f"📋 Open tasks as of {today} ({len(tasks)} total)\n"]
    for person, person_tasks in sorted(grouped.items()):
        lines.append(f"── {person} ──")
        for t in person_tasks:
            age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
            overdue_flag = ""
            if t.get("due_date"):
                due = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
                if today > due:
                    overdue_flag = " ⚠️ OVERDUE"
            due_str = f" | due {t['due_date']}" if t.get("due_date") else ""
            lines.append(f"  [{t['task_id']}] {t['description']}{due_str} | {age}d old{overdue_flag}")
        lines.append("")

    return "\n".join(lines).strip()


# ── MCP tool registry ────────────────────────────────────────────────────────

TOOLS = {
    "add_task": {
        "fn": add_task,
        "schema": {
            "name": "add_task",
            "description": (
                "Log a new task assigned by RK to a direct report. "
                "Call this whenever RK says he told someone to do something."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "First name of the assignee (e.g. Mahendra, Mali, Rehan)."},
                    "description": {"type": "string", "description": "What the person needs to do."},
                    "due_date": {"type": "string", "description": "Optional due date in YYYY-MM-DD format."},
                },
                "required": ["assignee", "description"],
            },
        },
    },
    "close_task": {
        "fn": close_task,
        "schema": {
            "name": "close_task",
            "description": "Mark a task as closed when RK says someone has completed their work.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "8-character task ID if known."},
                    "description_hint": {"type": "string", "description": "Keyword from the task description to find it."},
                },
            },
        },
    },
    "list_tasks": {
        "fn": list_tasks,
        "schema": {
            "name": "list_tasks",
            "description": "Show all open tasks, grouped by assignee. Optionally filter by one person.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Filter by first name. Leave blank for everyone."},
                },
            },
        },
    },
}


# ── MCP message handler ──────────────────────────────────────────────────────

def handle_mcp(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "task-tracker", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": [t["schema"] for t in TOOLS.values()]},
        }

    if method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}

        try:
            text = TOOLS[tool_name]["fn"](args)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": text}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notifications need no response

    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="Task Tracker MCP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://claude.ai", "https://api.anthropic.com"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# SSE endpoint — Claude.ai opens a long-lived GET to receive server→client events.
# Each connected client gets its own queue.
_sse_queues: dict[str, asyncio.Queue] = {}


async def _sse_stream(request: Request, secret: str = "") -> StreamingResponse:
    client_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _sse_queues[client_id] = queue

    base = str(request.base_url).rstrip("/")
    if secret:
        endpoint_url = base + f"/mcp/{secret}/message?client_id={client_id}"
    else:
        endpoint_url = base + f"/message?client_id={client_id}"

    async def event_stream():
        try:
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _sse_queues.pop(client_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _handle_message(request: Request, client_id: str) -> Response:
    body = await request.json()
    response = handle_mcp(body)
    queue = _sse_queues.get(client_id)
    if response is not None and queue:
        await queue.put(response)
    return Response(status_code=202)


# Bearer-token auth routes
@app.get("/sse")
async def sse_endpoint(request: Request, _=Depends(verify_auth)):
    return await _sse_stream(request)


@app.post("/message")
async def message_endpoint(request: Request, client_id: str, _=Depends(verify_auth)):
    return await _handle_message(request, client_id)


# Secret-in-URL routes: /mcp/<secret>/sse and /mcp/<secret>/message
@app.get("/mcp/{secret}/sse")
async def sse_endpoint_secret(secret: str, request: Request):
    if MCP_SECRET and secret != MCP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await _sse_stream(request, secret=secret)


@app.post("/mcp/{secret}/message")
async def message_endpoint_secret(secret: str, request: Request, client_id: str):
    if MCP_SECRET and secret != MCP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await _handle_message(request, client_id)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")
