"""
Digest builder — formats email messages for RK and each assignee.
"""

from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def _today():
    return datetime.now(IST).date()


def build_rk_digest(tasks: list[dict]) -> str:
    today = _today()
    overdue = []
    on_track = []

    for t in tasks:
        age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
        is_overdue = False
        if t.get("due_date"):
            due = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
            is_overdue = today > due
        t["_age"] = age
        t["_overdue"] = is_overdue
        if is_overdue:
            overdue.append(t)
        else:
            on_track.append(t)

    lines = [f"Task Digest — {today.strftime('%d %b %Y')}"]
    lines.append(f"Total open: {len(tasks)}")
    lines.append("")

    if overdue:
        lines.append("⚠️ OVERDUE")
        for t in sorted(overdue, key=lambda x: x["_age"], reverse=True):
            due_str = f" | due {t['due_date']}" if t.get("due_date") else ""
            lines.append(f"  • [{t['task_id']}] {t['assignee']}: {t['description']}{due_str} | {t['_age']}d old")
        lines.append("")

    # Group on-track tasks by assignee
    grouped: dict[str, list] = {}
    for t in on_track:
        grouped.setdefault(t["assignee"], []).append(t)

    if grouped:
        lines.append("✅ Open Tasks by Person")
        for person, person_tasks in sorted(grouped.items()):
            lines.append(f"\n{person}")
            for t in person_tasks:
                due_str = f" | due {t['due_date']}" if t.get("due_date") else ""
                lines.append(f"  • [{t['task_id']}] {t['description']}{due_str} | {t['_age']}d old")

    lines.append("")
    lines.append("Reply to Claude to add or close tasks.")
    return "\n".join(lines)


def build_assignee_digest(assignee_name: str, tasks: list[dict]) -> str:
    today = _today()
    lines = [
        f"Namaste {assignee_name}! 🙏",
        f"",
        f"This is a reminder from RK's office of your pending tasks as of {today.strftime('%d %b %Y')}:",
        "",
    ]

    for t in tasks:
        age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
        due_str = f" (due {t['due_date']})" if t.get("due_date") else ""
        overdue_flag = ""
        if t.get("due_date"):
            due = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
            if today > due:
                overdue_flag = " ⚠️ OVERDUE"
        lines.append(f"  • {t['description']}{due_str} — {age} day(s) since assigned{overdue_flag}")

    lines.append("")
    lines.append("Kindly update RK once these are done. Thank you!")
    return "\n".join(lines)


def build_rk_whatsapp(tasks: list[dict]) -> str:
    today = _today()
    grouped: dict[str, list] = {}
    for t in tasks:
        grouped.setdefault(t["assignee"], []).append(t)

    lines = [
        f"📋 *Daily Task Summary — {today.strftime('%d %b %Y')}*",
        f"*{len(tasks)} open task(s)*",
        "",
    ]

    for person, person_tasks in sorted(grouped.items()):
        lines.append(f"*{person}*")
        for t in person_tasks:
            age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
            if t.get("due_date"):
                due = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
                overdue = today > due
                due_str = f" | due {t['due_date']}"
                flag = " 🔴" if overdue else (" ⚠️" if age >= 3 else "")
            else:
                due_str = ""
                flag = " ⚠️" if age >= 3 else ""
            lines.append(f"  • {t['description']}{due_str} ({age}d){flag}")
        lines.append("")

    return "\n".join(lines).strip()


def build_assignee_whatsapp(assignee_name: str, tasks: list[dict]) -> str:
    today = _today()
    lines = [
        f"📌 *Hi {assignee_name}!*",
        f"Here are your pending tasks as of {today.strftime('%d %b %Y')}:",
        "",
    ]

    for t in tasks:
        age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
        if t.get("due_date"):
            due = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
            overdue = today > due
            due_str = f" | due {t['due_date']}"
            flag = " 🔴 *OVERDUE*" if overdue else ""
        else:
            due_str = ""
            flag = ""
        lines.append(f"  • {t['description']}{due_str} ({age}d){flag}")

    lines.append("")
    lines.append("Please update RK once done. 🙏")
    return "\n".join(lines)


def build_stale_review_prompt(stale_tasks: list[dict]) -> str:
    today = _today()
    lines = [
        f"📌 Fortnightly Task Review — {today.strftime('%d %b %Y')}",
        "",
        "The following tasks are more than 30 days old. Please review each one:",
        "",
    ]
    for t in stale_tasks:
        age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
        lines.append(f"  • [{t['task_id']}] {t['assignee']}: {t['description']} | {age}d old")

    lines.append("")
    lines.append("For each task, please tell Claude: close it, defer it, or escalate it.")
    return "\n".join(lines)
