"""
Generate a task list PDF using reportlab.
"""

import io
from datetime import datetime, timezone, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

IST = timezone(timedelta(hours=5, minutes=30))


def generate_task_pdf(tasks: list[dict], title: str = "Task Summary") -> bytes:
    """Return a PDF as bytes."""
    today = datetime.now(IST).date()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    heading = ParagraphStyle("heading", fontSize=16, fontName="Helvetica-Bold", spaceAfter=4)
    subheading = ParagraphStyle("subheading", fontSize=10, fontName="Helvetica", textColor=colors.grey, spaceAfter=12)
    section = ParagraphStyle("section", fontSize=12, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=6)

    story = []
    story.append(Paragraph(title, heading))
    story.append(Paragraph(f"Generated: {today.strftime('%d %b %Y')} | {len(tasks)} open task(s)", subheading))

    # Group by assignee
    grouped: dict[str, list] = {}
    for t in tasks:
        grouped.setdefault(t["assignee"], []).append(t)

    for person, person_tasks in sorted(grouped.items()):
        story.append(Paragraph(person, section))

        table_data = [["Task", "Due Date", "Age", "Status"]]
        for t in person_tasks:
            age = (today - datetime.strptime(t["date_assigned"], "%Y-%m-%d").date()).days
            due = t.get("due_date") or "—"
            overdue = ""
            if t.get("due_date"):
                due_date = datetime.strptime(t["due_date"], "%Y-%m-%d").date()
                if today > due_date:
                    overdue = " ⚠"
            table_data.append([
                t["description"],
                due,
                f"{age}d",
                f"Open{overdue}",
            ])

        col_widths = [95 * mm, 30 * mm, 20 * mm, 25 * mm]
        tbl = Table(table_data, colWidths=col_widths)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d2d2d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("RK Group — Confidential", ParagraphStyle("footer", fontSize=8, textColor=colors.grey)))

    doc.build(story)
    return buf.getvalue()


def generate_assignee_pdf(assignee_name: str, tasks: list[dict]) -> bytes:
    """PDF for a single assignee showing only their tasks."""
    return generate_task_pdf(tasks, title=f"Tasks for {assignee_name}")
