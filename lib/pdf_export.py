"""
lib/pdf_export.py
PDF report generation for the Desert Analysis tab.
"""
from datetime import date
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
)


FLAGGED_HEX     = "#BC4A3C"
NOT_FLAGGED_HEX = "#C8C8C8"


def _render_static_map(df_filtered, gdf_zctas):
    """Render flagged vs non-flagged ZCTAs as a PNG; returns BytesIO."""
    gdf = gdf_zctas.copy()
    gdf["ZCTA5CE20"] = gdf["ZCTA5CE20"].astype(str).str.zfill(5)
    flags = df_filtered[["ZCTA5CE20", "flagged"]].copy()
    flags["ZCTA5CE20"] = flags["ZCTA5CE20"].astype(str).str.zfill(5)
    gdf = gdf.merge(flags, on="ZCTA5CE20", how="left")
    gdf["flagged"] = gdf["flagged"].fillna(False)

    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    not_flagged = gdf[~gdf["flagged"]]
    flagged     = gdf[gdf["flagged"]]
    if len(not_flagged) > 0:
        not_flagged.plot(ax=ax, color=NOT_FLAGGED_HEX, edgecolor="white", linewidth=0.3)
    if len(flagged) > 0:
        flagged.plot(ax=ax, color=FLAGGED_HEX, edgecolor="white", linewidth=0.3)
    ax.set_axis_off()
    ax.set_title("Flagged ZCTAs", fontsize=14, pad=8)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def _format_threshold(label, direction, threshold):
    op = ">" if direction == "gt" else "<"
    if "income" in label.lower() or "$" in label:
        return f"{label} {op} ${threshold:,.0f}"
    if "%" in label:
        return f"{label} {op} {threshold:.1f}%"
    if "miles" in label.lower():
        return f"{label} {op} {threshold:.1f} mi"
    return f"{label} {op} {threshold:g}"


def _build_narrative(enabled_slider_details, logic, summary):
    if not enabled_slider_details:
        return "No thresholds were active when this report was generated."
    thresh_phrases = [
        _format_threshold(d["label"], d["direction"], d["threshold"])
        for d in enabled_slider_details
    ]
    joined = "; ".join(thresh_phrases)
    conj = "all of" if logic == "AND" else "any of"
    return (
        f"This report flags ZCTAs meeting {conj} {len(enabled_slider_details)} "
        f"threshold(s): {joined}. "
        f"A total of {summary['n_flagged']:,} ZCTAs were flagged across "
        f"{summary['n_counties']} counties, covering an estimated "
        f"{summary['total_pop_flagged']:,} residents."
    )


def build_desert_analysis_pdf(
    flagged_df,
    df_filtered,
    gdf_zctas,
    enabled_slider_details,
    logic,
    summary,
):
    """
    Build a single-page Desert Analysis PDF report.

    flagged_df : DataFrame of flagged ZCTAs with display columns
                 (ZCTA5CE20, optional area_name/county_name, and enabled metrics)
    df_filtered : full filtered DataFrame with ZCTA5CE20 + 'flagged' bool
                  (used to render the map; includes non-flagged ZCTAs for context)
    gdf_zctas : GeoDataFrame with ZCTA boundaries
    enabled_slider_details : list of {col, label, direction, threshold}
    logic : "AND" or "OR"
    summary : {"n_flagged", "total_pop_flagged", "n_counties"}

    Returns: bytes (PDF content)
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Title"], fontSize=18, spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "MetaStyle", parent=styles["Normal"],
        fontSize=9, textColor=colors.grey, spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "BodyStyle", parent=styles["BodyText"], fontSize=10, leading=13,
    )
    section_style = ParagraphStyle(
        "SectionStyle", parent=styles["Heading3"], fontSize=11,
        spaceBefore=10, spaceAfter=4,
    )

    story = []

    story.append(Paragraph("Desert Analysis Report", title_style))
    story.append(Paragraph(
        f"Generated {date.today().isoformat()} &nbsp;|&nbsp; Logic: <b>{logic}</b>",
        meta_style,
    ))

    story.append(Paragraph(_build_narrative(enabled_slider_details, logic, summary), body_style))

    summary_table_data = [
        ["Flagged ZCTAs", "Est. population", "Counties"],
        [
            f"{summary['n_flagged']:,}",
            f"{summary['total_pop_flagged']:,}",
            f"{summary['n_counties']}",
        ],
    ]
    summary_tbl = Table(summary_table_data, colWidths=[2.3 * inch] * 3)
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 10),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX",         (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID",   (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story.append(Spacer(1, 6))
    story.append(summary_tbl)

    if enabled_slider_details:
        story.append(Paragraph("Active Thresholds", section_style))
        for d in enabled_slider_details:
            story.append(Paragraph(
                "&bull; " + _format_threshold(d["label"], d["direction"], d["threshold"]),
                body_style,
            ))

    story.append(Paragraph("Map", section_style))
    try:
        img_buf = _render_static_map(df_filtered, gdf_zctas)
        story.append(Image(img_buf, width=6.5 * inch, height=4.8 * inch))
    except Exception as e:
        story.append(Paragraph(f"<i>Map unavailable: {e}</i>", body_style))

    story.append(PageBreak())
    story.append(Paragraph("Flagged ZCTAs", section_style))

    if len(flagged_df) == 0:
        story.append(Paragraph("No ZCTAs met the active thresholds.", body_style))
    else:
        display = flagged_df.copy()
        for c in display.columns:
            if pd.api.types.is_float_dtype(display[c]):
                display[c] = display[c].round(2)
            display[c] = display[c].astype(str)

        table_data = [list(display.columns)] + display.values.tolist()

        n_cols = len(display.columns)
        total_w = 7.5 * inch
        col_widths = [total_w / n_cols] * n_cols

        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#BC4A3C")),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 7),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F7F4F2")]),
            ("GRID",         (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)

    doc.build(story)
    return buf.getvalue()
