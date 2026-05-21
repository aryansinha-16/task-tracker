"""
Google Sheets helpers for the task tracker.
Uses a service account JSON credential file.
Sheet schema (row order):
  task_id | assignee | description | date_assigned | due_date | status | closed_date
"""

import os
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
TASKS_TAB = os.environ.get("TASKS_TAB", "Tasks")
ASSIGNEES_TAB = os.environ.get("ASSIGNEES_TAB", "Assignees")
CREDS_PATH = os.environ["GOOGLE_CREDS_PATH"]

HEADERS = ["task_id", "assignee", "description", "date_assigned", "due_date", "status", "closed_date"]


def _client():
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet(tab: str):
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    return sh.worksheet(tab)


def _ensure_headers(ws):
    first_row = ws.row_values(1)
    if first_row != HEADERS:
        ws.insert_row(HEADERS, 1)


def append_task(row: dict):
    ws = get_sheet(TASKS_TAB)
    _ensure_headers(ws)
    values = [row.get(h, "") for h in HEADERS]
    ws.append_row(values, value_input_option="USER_ENTERED")


def update_task_status(identifier: str, new_status: str, closed_date: str = "") -> Optional[dict]:
    """
    Find an open task by task_id or description keyword and update its status.
    Returns the matched task dict, or None if not found.
    """
    ws = get_sheet(TASKS_TAB)
    records = ws.get_all_records()

    identifier_lower = identifier.lower()
    matched_idx = None
    matched_task = None

    for i, rec in enumerate(records):
        if rec.get("status", "").lower() != "open":
            continue
        if (rec.get("task_id", "").lower() == identifier_lower or
                identifier_lower in rec.get("description", "").lower()):
            matched_idx = i + 2  # 1-indexed + header row
            matched_task = rec
            break

    if matched_idx is None:
        return None

    status_col = HEADERS.index("status") + 1
    closed_col = HEADERS.index("closed_date") + 1
    ws.update_cell(matched_idx, status_col, new_status)
    ws.update_cell(matched_idx, closed_col, closed_date)

    return matched_task


def list_open_tasks() -> list[dict]:
    ws = get_sheet(TASKS_TAB)
    records = ws.get_all_records()
    return [r for r in records if r.get("status", "").lower() == "open"]


def get_assignee_directory() -> list[dict]:
    """Returns list of {name, phone} from the Assignees tab."""
    ws = get_sheet(ASSIGNEES_TAB)
    records = ws.get_all_records()
    return [
        {"name": r["name"].strip(), "phone": str(r.get("phone", "")).strip()}
        for r in records if r.get("name")
    ]
