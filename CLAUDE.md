# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An email-based personal task tracker for RK (Founder, RK Group). RK logs tasks via voice/text in Claude.ai on his phone. The system stores tasks in Google Sheets, sends daily 9 AM IST email digests to RK and each assignee, and lets RK close tasks by talking to Claude.

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env

# Start the MCP HTTP server (port 8000)
python -m dotenv -f .env run uvicorn mcp_server.server:app --port 8000

# Run the scheduler immediately (instead of waiting for 03:30 UTC)
python -m dotenv -f .env run python scheduler/main.py --run-now

# Test a specific tool function directly
python -c "from dotenv import load_dotenv; load_dotenv(); from mcp_server.server import list_tasks; print(list_tasks({}))"
```

**Windows note:** Python's default terminal encoding breaks emoji output. Prefix scripts with:
```python
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
```

## Architecture

```
mcp_server/server.py     FastAPI HTTP+SSE server — MCP protocol endpoint for Claude.ai
mcp_server/sheets.py     All Google Sheets read/write logic (gspread)
scheduler/main.py        Daily digest runner — reads sheet, sends email, handles stale task review
scheduler/digest.py      Message formatters: build_rk_digest(), build_assignee_digest(), build_stale_review_prompt()
scheduler/email.py       Gmail SMTP sender: send_email(to, subject, body)
```

The MCP server and scheduler are **independent processes** — both run on Railway via the `Procfile`. The scheduler imports from `mcp_server.sheets` directly (no HTTP calls between them).

## MCP transport

Claude.ai connects via SSE: it opens `GET /sse` (long-lived) and POSTs JSON-RPC to `POST /message?client_id=<id>`. Responses go back over the SSE stream, not the POST response (which always returns 202). Auth is `Authorization: Bearer <MCP_SECRET>`.

## Google Sheets schema

**Tasks tab:** `task_id | assignee | description | date_assigned | due_date | status | closed_date`
- `status` must be exactly `Open` or `Closed`
- `date_assigned` and `due_date` must be `YYYY-MM-DD`
- Headers are auto-created on first write if missing

**Assignees tab:** `name | email`
- `name` is matched case-insensitively against task assignee names
- `email` is the assignee's email address

## Email (Railway SendGrid MCP)

- Calls the same Railway-hosted SendGrid MCP used in the rk-newsletter project
- MCP URL: `https://valuecart-email-mcp-production.up.railway.app/mcp/valuecart2026`
- Uses JSON-RPC over SSE — no extra API keys needed beyond the MCP URL

## Key env vars

See `.env.example` for all values. Critical ones:
- `GOOGLE_SHEET_ID` — `166y8gfRlfbCTt7-y33yoLqBOlj2KrIyfrQw3RGN4mc4`
- `GOOGLE_CREDS_PATH` — path to `service_account.json`
- `SENDGRID_MCP_URL` — Railway SendGrid MCP endpoint (has a default, only override if URL changes)
- `RK_EMAIL` — RK's email address (currently `shrinivas.rc@gmail.com`)
- `MCP_SECRET` — Bearer token required on all `/sse` and `/message` requests

## Deployment

Railway reads `Procfile` and runs two processes:
- `web` → MCP server (gets public HTTPS URL, add to RK's Claude.ai Settings → Integrations)
- `scheduler` → daily digest at 03:30 UTC (= 09:00 IST)

Set all `.env` values as Railway environment variables. `GOOGLE_CREDS_PATH` won't work on Railway — the service account JSON needs to be inlined as an env var instead (see runbook).
