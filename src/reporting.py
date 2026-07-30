"""PDF report generation for dashboard findings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .cleaning import CleaningSummary
from .insights import Insight


def _clean_text(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf_report(
    path: str | Path,
    frame: pd.DataFrame,
    summary: CleaningSummary,
    insights: list[Insight],
    executive_summary: str | None = None,
) -> Path:
    """Build a compact, email-safe A4 report and return its path."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DashboardTitle", parent=styles["Title"], alignment=TA_CENTER,
        fontSize=20, leading=24, textColor=colors.HexColor("#102A43"), spaceAfter=10,
    )
    heading = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], textColor=colors.HexColor("#176B87"),
        spaceBefore=12, spaceAfter=6,
    )
    body = ParagraphStyle("ReportBody", parent=styles["BodyText"], fontSize=9, leading=12)
    story = [
        Paragraph("Universal AI Dashboard Generator", title),
        Paragraph(f"Prepared {datetime.now():%d %b %Y, %I:%M %p}", ParagraphStyle(
            "Timestamp", parent=body, alignment=TA_CENTER, textColor=colors.grey
        )),
        Spacer(1, 0.18 * inch),
    ]
    kpis = [
        ["Clean rows", "Columns", "Missing cells", "Duplicates removed"],
        [f"{len(frame):,}", f"{len(frame.columns):,}", f"{summary.missing_cells:,}", f"{summary.duplicate_rows_removed:,}"],
    ]
    kpi_table = Table(kpis, colWidths=[1.75 * inch] * 4)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#176B87")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#EAF4F4")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BFD7D9")),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(kpi_table)

    if executive_summary:
        story += [Paragraph("Executive summary", heading), Paragraph(_clean_text(executive_summary), body)]

    story.append(Paragraph("Top 10 evidence-based insights", heading))
    rows = [[Paragraph("#", body), Paragraph("Finding", body), Paragraph("Why it matters", body)]]
    for index, insight in enumerate(insights[:10], start=1):
        finding = f"<b>{_clean_text(insight.title)}</b><br/>{_clean_text(insight.finding)}"
        rows.append([Paragraph(str(index), body), Paragraph(finding, body), Paragraph(_clean_text(insight.detail), body)])
    insight_table = Table(rows, colWidths=[0.35 * inch, 3.35 * inch, 3.3 * inch], repeatRows=1)
    insight_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102A43")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6E3E5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6FAFA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(insight_table)
    story += [
        Paragraph("Method note", heading),
        Paragraph(
            "Findings are calculated from the cleaned CSV. Correlations identify relationships, not causation. "
            "Outliers use the 1.5×IQR rule. The optional AI narrative summarizes calculated findings only.", body,
        ),
    ]
    document = SimpleDocTemplate(
        str(output), pagesize=A4, rightMargin=0.45 * inch, leftMargin=0.45 * inch,
        topMargin=0.45 * inch, bottomMargin=0.45 * inch,
    )
    document.build(story)
    return output
