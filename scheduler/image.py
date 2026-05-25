"""
Generate a task-list PNG image using Pillow.
High-res (2x), clean card design — no avatar icons, no footer.
"""

import io
import os
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

IST = timezone(timedelta(hours=5, minutes=30))

SCALE   = 8          # 8x for high-res
W_BASE  = 780
W       = W_BASE * SCALE
PAD     = 32 * SCALE

BG          = (255, 255, 255)
BORDER      = (220, 220, 220)
HEADER_FG   = (20,  20,  20)
DATE_FG     = (130, 130, 130)
OVERDUE_FG  = (200,  40,  40)
OVERDUE_BG  = (255, 243, 243)
OVERDUE_DOT = (220,  50,  50)
SEC_FG      = (40,  40,  40)
TH_FG       = (150, 150, 150)
CELL_FG     = (30,  30,  30)
LATE_BG     = (255, 220, 220)
LATE_FG     = (190,  35,  35)
ONTRACK_BG  = (220, 245, 225)
ONTRACK_FG  = (35,  150,  60)
DIV         = (230, 230, 230)
ACCENT      = (99,  102, 241)

AVATAR_COLORS = [
    (99, 102, 241), (234, 88, 12), (16, 185, 129),
    (245, 158, 11), (239, 68, 68), (14, 165, 233),
]


_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts")

def _load_font(size: int, bold: bool = False):
    candidates_bold = [
        os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf"),
        "arialbd.ttf", "Arial Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    candidates_regular = [
        os.path.join(_FONT_DIR, "DejaVuSans.ttf"),
        "arial.ttf", "Arial.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in (candidates_bold if bold else candidates_regular):
        try:
            return ImageFont.truetype(path, size * SCALE)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _th_val(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]


def _pill(draw, x, y, text, bg, fg, font, h=20):
    h = h * SCALE
    tw = _tw(draw, text, font)
    px = 10 * SCALE
    r  = h // 2
    draw.rounded_rectangle([x, y, x + tw + px * 2, y + h], radius=r, fill=bg)
    draw.text((x + px, y + (h - _th_val(draw, text, font)) // 2), text, font=font, fill=fg)
    return tw + px * 2


def _divider(draw, y, x0=None, x1=None):
    if x0 is None: x0 = PAD
    if x1 is None: x1 = W - PAD
    draw.line([(x0, y), (x1, y)], fill=DIV, width=SCALE)


def _date_str(d) -> str:
    return f"{d.day} {d.strftime('%b')}"


def generate_task_image(tasks: list[dict], title: str = "Daily Task Summary") -> bytes:
    today = datetime.now(IST).date()
    dow   = today.strftime("%a")
    header_date = f"{dow} {today.day} {today.strftime('%b %Y')} · 8:00 AM"

    # Annotate tasks
    overdue_tasks = []
    grouped: dict[str, list] = {}
    for t in tasks:
        t = dict(t)
        age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
        days_late = 0
        is_overdue = False
        if t.get("due_date"):
            due_dt = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
            days_late = (today - due_dt).days
            is_overdue = days_late > 0
        t["_age"] = age
        t["_overdue"] = is_overdue
        t["_days_late"] = days_late
        if is_overdue:
            overdue_tasks.append(t)
        grouped.setdefault(t["assignee"], []).append(t)

    # Fonts
    f_title  = _load_font(14, bold=True)
    f_date   = _load_font(11)
    f_sec    = _load_font(12, bold=True)
    f_th     = _load_font(10)
    f_cell   = _load_font(11)
    f_pill   = _load_font(10, bold=True)

    # Row/section heights (base, will be multiplied by SCALE)
    S = SCALE
    ROW_H  = 38 * S
    TH_H   = 26 * S
    SEC_H  = 40 * S
    HDR_H  = 56 * S
    OVER_H = 36 * S

    # Compute total height
    h = HDR_H + 16 * S
    if overdue_tasks:
        h += OVER_H + TH_H + ROW_H * len(overdue_tasks) + 20 * S
    h += 10 * S  # gap
    h += 30 * S  # "TEAM MEMBER STATUS" label
    for person_tasks in grouped.values():
        h += SEC_H + TH_H + ROW_H * len(person_tasks) + 16 * S
    h += 16 * S  # bottom pad

    img  = Image.new("RGB", (W, h), BG)
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rounded_rectangle([0, 0, W - 1, h - 1], radius=12 * S, outline=BORDER, width=S)

    y = 0

    # ── Header ───────────────────────────────────────────────────────────────
    # Accent left bar
    draw.rectangle([0, 0, 5 * S, HDR_H], fill=ACCENT)

    draw.text((PAD, 14 * S), title, font=f_title, fill=HEADER_FG)
    date_tw = _tw(draw, header_date, f_date)
    draw.text((W - PAD - date_tw, 18 * S), header_date, font=f_date, fill=DATE_FG)
    y = HDR_H
    draw.line([(0, y), (W, y)], fill=DIV, width=S)

    y += 16 * S

    # ── Overdue section ───────────────────────────────────────────────────────
    if overdue_tasks:
        # Tinted background strip
        strip_h = OVER_H + TH_H + ROW_H * len(overdue_tasks) + 12 * S
        draw.rectangle([0, y - 8 * S, W, y + strip_h], fill=OVERDUE_BG)

        # Red dot + label
        dot_r = 5 * S
        draw.ellipse([PAD, y + 6 * S, PAD + dot_r * 2, y + 6 * S + dot_r * 2], fill=OVERDUE_DOT)
        draw.text((PAD + dot_r * 2 + 8 * S, y + 4 * S), "OVERDUE TASKS — ACTION NEEDED", font=f_sec, fill=OVERDUE_FG)
        y += OVER_H

        # Column headers
        CX = [PAD, PAD + 248 * S, PAD + 378 * S, PAD + 490 * S]
        for i, lbl in enumerate(["Task", "Assigned To", "Due Date", "Overdue By"]):
            draw.text((CX[i], y), lbl, font=f_th, fill=TH_FG)
        y += TH_H
        _divider(draw, y)

        for t in overdue_tasks:
            y += 8 * S
            desc = t["description"]
            while _tw(draw, desc, f_cell) > 230 * S and len(desc) > 8:
                desc = desc[:-4] + "…"
            draw.text((CX[0], y), desc, font=f_cell, fill=CELL_FG)
            draw.text((CX[1], y), t["assignee"], font=f_cell, fill=CELL_FG)
            due_str = _date_str(datetime.strptime(t["due_date"], "%Y-%m-%d").date()) if t.get("due_date") else "—"
            draw.text((CX[2], y), due_str, font=f_cell, fill=CELL_FG)
            late_lbl = f"{t['_days_late']} day{'s' if t['_days_late'] != 1 else ''}"
            _pill(draw, CX[3], y - 2 * S, late_lbl, LATE_BG, LATE_FG, f_pill)
            y += ROW_H

        y += 8 * S
        draw.line([(0, y), (W, y)], fill=DIV, width=S)
        y += 10 * S

    # ── Team member status ────────────────────────────────────────────────────
    draw.text((PAD, y), "TEAM MEMBER STATUS", font=f_sec, fill=(100, 100, 100))
    y += 30 * S

    for idx, (person, person_tasks) in enumerate(sorted(grouped.items())):
        color = AVATAR_COLORS[idx % len(AVATAR_COLORS)]

        # Section row: coloured left accent + name
        draw.rectangle([0, y, 4 * S, y + SEC_H], fill=color)
        task_count = len(person_tasks)
        sec_label = f"{person} — {task_count} task{'s' if task_count != 1 else ''}"
        draw.text((PAD, y + (SEC_H - _th_val(draw, sec_label, f_sec)) // 2), sec_label, font=f_sec, fill=SEC_FG)
        y += SEC_H
        _divider(draw, y)

        # Column headers
        CX2 = [PAD, PAD + 390 * S, PAD + 510 * S]
        y += 6 * S
        for i, lbl in enumerate(["Task", "ETA", "Status"]):
            draw.text((CX2[i], y), lbl, font=f_th, fill=TH_FG)
        y += TH_H

        for t in person_tasks:
            desc = t["description"]
            while _tw(draw, desc, f_cell) > 370 * S and len(desc) > 8:
                desc = desc[:-4] + "…"
            draw.text((CX2[0], y), desc, font=f_cell, fill=CELL_FG)
            eta = _date_str(datetime.strptime(t["due_date"], "%Y-%m-%d").date()) if t.get("due_date") else "—"
            draw.text((CX2[1], y), eta, font=f_cell, fill=CELL_FG)
            if t["_overdue"]:
                late_lbl = f"{t['_days_late']} day{'s' if t['_days_late'] != 1 else ''} late"
                _pill(draw, CX2[2], y - 2 * S, late_lbl, LATE_BG, LATE_FG, f_pill)
            else:
                _pill(draw, CX2[2], y - 2 * S, "On track", ONTRACK_BG, ONTRACK_FG, f_pill)
            y += ROW_H

        y += 16 * S

    buf = io.BytesIO()
    # Save at half the pixel size so it renders at 1x on screen but is high-res
    out = img.resize((W_BASE, h // SCALE), Image.LANCZOS)
    out.save(buf, format="PNG", optimize=True, dpi=(144, 144))
    return buf.getvalue()


def generate_assignee_image(assignee_name: str, tasks: list[dict]) -> bytes:
    """Personal task list — no assignee column, overdue first then on-track."""
    today = datetime.now(IST).date()
    header_date = f"{today.strftime('%a')} {today.day} {today.strftime('%b %Y')} · 8:00 AM"
    title = f"Your Tasks — {assignee_name}"

    # Annotate and split
    overdue_tasks = []
    ontrack_tasks = []
    for t in tasks:
        t = dict(t)
        days_late = 0
        is_overdue = False
        if t.get("due_date"):
            due_dt = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
            days_late = (today - due_dt).days
            is_overdue = days_late > 0
        t["_overdue"] = is_overdue
        t["_days_late"] = days_late
        if is_overdue:
            overdue_tasks.append(t)
        else:
            ontrack_tasks.append(t)

    all_tasks = overdue_tasks + ontrack_tasks

    f_title = _load_font(14, bold=True)
    f_date  = _load_font(11)
    f_num   = _load_font(10, bold=True)
    f_th    = _load_font(10)
    f_cell  = _load_font(11)
    f_pill  = _load_font(10, bold=True)

    S      = SCALE
    ROW_H  = 40 * S
    TH_H   = 28 * S
    HDR_H  = 56 * S

    all_tasks = overdue_tasks + ontrack_tasks

    h = HDR_H + 16 * S + TH_H + ROW_H * len(all_tasks) + 20 * S

    img  = Image.new("RGB", (W, h), BG)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, W - 1, h - 1], radius=12 * S, outline=BORDER, width=S)

    # Header
    draw.rectangle([0, 0, 5 * S, HDR_H], fill=ACCENT)
    draw.text((PAD, 14 * S), title, font=f_title, fill=HEADER_FG)
    date_tw = _tw(draw, header_date, f_date)
    draw.text((W - PAD - date_tw, 18 * S), header_date, font=f_date, fill=DATE_FG)
    y = HDR_H
    draw.line([(0, y), (W, y)], fill=DIV, width=S)
    y += 16 * S

    # Columns: # | Task | Due Date | Status
    NUM_W = 36 * S
    CX = [PAD, PAD + NUM_W + 8 * S, PAD + NUM_W + 390 * S, PAD + NUM_W + 510 * S]
    for i, lbl in enumerate(["#", "Task", "Due Date", "Status"]):
        draw.text((CX[i], y), lbl, font=f_th, fill=TH_FG)
    y += TH_H
    _divider(draw, y)

    for idx, t in enumerate(all_tasks, start=1):
        row_bg = (250, 250, 252) if idx % 2 == 0 else BG
        draw.rectangle([0, y, W, y + ROW_H], fill=row_bg)

        mid_y = y + (ROW_H - _th_val(draw, "1", f_num)) // 2

        # Row number
        draw.text((CX[0], mid_y), str(idx), font=f_num, fill=TH_FG)

        # Task description
        desc = t["description"]
        while _tw(draw, desc, f_cell) > 360 * S and len(desc) > 8:
            desc = desc[:-4] + "…"
        draw.text((CX[1], mid_y), desc, font=f_cell, fill=CELL_FG)

        # Due date
        due_str = _date_str(datetime.strptime(t["due_date"], "%Y-%m-%d").date()) if t.get("due_date") else "—"
        draw.text((CX[2], mid_y), due_str, font=f_cell, fill=CELL_FG)

        # Status pill
        if t["_overdue"]:
            late_lbl = f"{t['_days_late']} day{'s' if t['_days_late'] != 1 else ''} late"
            _pill(draw, CX[3], y + (ROW_H - 20 * S) // 2, late_lbl, LATE_BG, LATE_FG, f_pill)
        else:
            _pill(draw, CX[3], y + (ROW_H - 20 * S) // 2, "On track", ONTRACK_BG, ONTRACK_FG, f_pill)

        y += ROW_H
        _divider(draw, y)

    buf = io.BytesIO()
    out = img.resize((W_BASE, h // SCALE), Image.LANCZOS)
    out.save(buf, format="PNG", optimize=True, dpi=(144, 144))
    return buf.getvalue()
