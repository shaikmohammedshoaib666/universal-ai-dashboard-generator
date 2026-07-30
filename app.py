"""Streamlit interface for the Universal AI Dashboard Generator."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from src.cleaning import CleaningSummary, load_and_clean_csv, profile_dataframe
from src.emailer import configured_recipients, send_report
from src.insights import Insight, generate_insights
from src.llm import build_executive_summary
from src.reporting import build_pdf_report


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "latest_cleaned.csv"
REPORT_PATH = ROOT / "outputs" / "ai_dashboard_report.pdf"
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="Universal AI Dashboard", page_icon="✦", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1400px; padding-top: 2.2rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {background: #f7fbfc; border: 1px solid #d5e7eb; padding: 0.7rem; border-radius: 0.55rem;}
      .insight-title {color: #176b87; font-weight: 650; margin-bottom: .25rem;}
      .insight-finding {font-size: 1.02rem; line-height: 1.42;}
      .insight-detail {color: #5c6f75; font-size: .88rem; margin-top: .35rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Cleaning and profiling your CSV…")
def process_upload(contents: bytes) -> tuple[pd.DataFrame, CleaningSummary]:
    return load_and_clean_csv(contents)


def _cleaning_description(summary: CleaningSummary) -> str:
    return (
        f"**{summary.original_rows:,} → {summary.cleaned_rows:,} rows** · "
        f"**{summary.original_columns} columns** · "
        f"**{summary.duplicate_rows_removed:,} duplicate rows removed** · "
        f"**{summary.missing_cells:,} missing cells retained and flagged**"
    )


def _render_chart(frame: pd.DataFrame, summary: CleaningSummary) -> None:
    st.subheader("Adaptive chart builder")
    valid_x = summary.date_columns + summary.categorical_columns + summary.numeric_columns
    if not valid_x:
        st.info("No chartable columns were detected in this view.")
        return

    col1, col2, col3, col4 = st.columns([1.2, 1.2, 1.2, 1])
    x_column = col1.selectbox("X axis", valid_x, key="chart_x")
    measures = ["Record count"] + summary.numeric_columns
    measure = col2.selectbox("Measure", measures, key="chart_measure")
    chart_options = ["Bar", "Line", "Scatter", "Histogram"]
    default_chart = "Line" if x_column in summary.date_columns else "Bar"
    chart_type = col3.selectbox("Chart", chart_options, index=chart_options.index(default_chart), key="chart_type")
    color_options = ["None"] + [field for field in summary.categorical_columns if field != x_column]
    color_field = col4.selectbox("Split by", color_options, key="chart_color")
    color = None if color_field == "None" else color_field

    try:
        if chart_type == "Histogram":
            if measure == "Record count":
                fig = px.histogram(frame, x=x_column, color=color, title=f"Distribution of {x_column}")
            else:
                fig = px.histogram(frame, x=measure, color=color, title=f"Distribution of {measure}")
        elif chart_type == "Scatter":
            if measure == "Record count" or not summary.numeric_columns:
                st.info("Choose a numeric measure for a scatter plot.")
                return
            fig = px.scatter(frame, x=x_column, y=measure, color=color, title=f"{measure} by {x_column}", opacity=0.72)
        else:
            aggregation = st.radio("Aggregate values by", ["Sum", "Average", "Median", "Count"], horizontal=True)
            group_fields = [x_column] + ([color] if color else [])
            if measure == "Record count" or aggregation == "Count":
                plotted = frame.groupby(group_fields, dropna=False).size().reset_index(name="value")
                value_label = "Records"
            else:
                method = {"Sum": "sum", "Average": "mean", "Median": "median"}[aggregation]
                plotted = frame.groupby(group_fields, dropna=False)[measure].agg(method).reset_index(name="value")
                value_label = f"{aggregation} {measure}"
            if x_column in summary.date_columns:
                plotted = plotted.sort_values(x_column)
            if chart_type == "Line":
                fig = px.line(plotted, x=x_column, y="value", color=color, markers=True, title=f"{value_label} by {x_column}")
            else:
                fig = px.bar(plotted, x=x_column, y="value", color=color, barmode="group", title=f"{value_label} by {x_column}")
            fig.update_yaxes(title=value_label)
        fig.update_layout(template="plotly_white", legend_title_text=color or "", margin=dict(l=20, r=20, t=60, b=20))
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
    except (ValueError, TypeError) as exc:
        st.warning(f"This chart cannot be drawn with the selected fields: {exc}")


def _report_bytes(frame: pd.DataFrame, summary: CleaningSummary, insights: list[Insight], narrative: str | None) -> bytes:
    report = build_pdf_report(REPORT_PATH, frame, summary, insights, narrative)
    return report.read_bytes()


def _render_automation(frame: pd.DataFrame, summary: CleaningSummary, insights: list[Insight], narrative: str | None) -> None:
    st.subheader("Report automation")
    st.caption("Save this cleaned dataset, then run the scheduler as a separate process for reliable 7:00 AM delivery.")
    save_col, report_col, email_col = st.columns(3)
    with save_col:
        if st.button("Save for daily automation", use_container_width=True):
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(DATA_PATH, index=False)
            st.success("Saved as data/latest_cleaned.csv")
    with report_col:
        if st.button("Prepare PDF report", use_container_width=True):
            st.session_state["pdf_bytes"] = _report_bytes(frame, summary, insights, narrative)
            st.success("PDF report is ready below.")
    with email_col:
        if st.button("Generate & email now", type="primary", use_container_width=True):
            try:
                pdf_bytes = _report_bytes(frame, summary, insights, narrative)
                st.session_state["pdf_bytes"] = pdf_bytes
                message = send_report(REPORT_PATH)
                st.success(message)
            except Exception as exc:
                st.error(str(exc))

    if st.session_state.get("pdf_bytes"):
        st.download_button(
            "Download PDF report", st.session_state["pdf_bytes"], file_name="ai_dashboard_report.pdf",
            mime="application/pdf", use_container_width=False,
        )
    recipients = configured_recipients()
    scheduled_at = f"{os.getenv('REPORT_HOUR', '7')}:{os.getenv('REPORT_MINUTE', '0').zfill(2)} {os.getenv('REPORT_TIMEZONE', 'Asia/Kolkata')}"
    st.info(
        f"**Schedule:** {scheduled_at} daily  ·  **Recipients:** {', '.join(recipients) if recipients else 'not configured'}\n\n"
        "Start the durable worker with `python -m src.scheduler`. Test the full flow using `python -m src.scheduler --run-now`."
    )


def _render_dashboard(frame: pd.DataFrame, cleaning: CleaningSummary, source_name: str) -> None:
    st.title("Universal AI Dashboard Generator")
    st.caption(f"{source_name} · Local CSV analysis · Evidence-based insight engine")
    st.markdown(_cleaning_description(cleaning))

    with st.sidebar:
        st.header("Explore this data")
        st.caption("Filters update the charts, insights, and PDF report.")
        filter_column = st.selectbox("Filter a category", ["No filter"] + cleaning.categorical_columns)
        visible = frame
        if filter_column != "No filter":
            options = frame[filter_column].dropna().astype(str).unique().tolist()
            selected = st.multiselect("Keep values", options, default=options)
            visible = frame[frame[filter_column].astype(str).isin(selected)]
        st.divider()
        st.download_button(
            "Download cleaned CSV", frame.to_csv(index=False).encode("utf-8"), "cleaned_data.csv", "text/csv",
            use_container_width=True,
        )

    view_summary = profile_dataframe(visible)
    insights = generate_insights(visible, view_summary)
    metrics = st.columns(4)
    metrics[0].metric("Visible records", f"{len(visible):,}")
    metrics[1].metric("Numeric fields", len(view_summary.numeric_columns))
    metrics[2].metric("Date fields", len(view_summary.date_columns))
    metrics[3].metric("Missing cells", f"{view_summary.missing_cells:,}")

    with st.expander("See cleaning and field profile"):
        st.write(_cleaning_description(cleaning))
        schema = pd.DataFrame({
            "Field": frame.columns,
            "Type": frame.dtypes.astype(str).values,
            "Non-null": frame.notna().sum().values,
            "Unique values": frame.nunique(dropna=True).values,
        })
        st.dataframe(schema, use_container_width=True, hide_index=True)

    _render_chart(visible, view_summary)
    st.subheader("10 evidence-based insights")
    st.caption("Every statement below is calculated from the visible data. They are prompts for investigation, not unsupported forecasts.")
    for row_start in range(0, len(insights), 2):
        columns = st.columns(2)
        for index, insight in enumerate(insights[row_start:row_start + 2]):
            with columns[index]:
                with st.container(border=True):
                    st.markdown(f'<div class="insight-title">{insight.title} · {insight.category}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="insight-finding">{insight.finding}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="insight-detail">{insight.detail}</div>', unsafe_allow_html=True)

    st.subheader("Optional AI executive narrative")
    narrative = st.session_state.get("narrative")
    if not os.getenv("OPENAI_API_KEY"):
        st.caption("Add `OPENAI_API_KEY` to `.env` to enable this. Raw rows are never sent—only the calculated findings above.")
    elif st.button("Write executive narrative"):
        with st.spinner("Summarizing verified findings…"):
            narrative = build_executive_summary(insights)
            st.session_state["narrative"] = narrative
            if not narrative:
                st.warning("The narrative service did not return a result. The measured insights remain available.")
    if narrative:
        st.info(narrative)

    _render_automation(visible, view_summary, insights, narrative)
    st.subheader("Clean data preview")
    st.dataframe(visible.head(250), use_container_width=True, hide_index=True)


def main() -> None:
    uploaded = st.file_uploader("Upload a CSV to create your AI dashboard", type=["csv"])
    if uploaded is None:
        st.title("Universal AI Dashboard Generator")
        st.markdown("Upload a CSV and this app will clean it, surface ten evidence-based insights, build an adaptive dashboard, and prepare a daily PDF email workflow.")
        st.info("Your file is processed locally. Add an API key only if you want the optional executive summary.")
        return
    try:
        frame, summary = process_upload(uploaded.getvalue())
        _render_dashboard(frame, summary, uploaded.name)
    except Exception as exc:
        st.error(f"I couldn't process this file: {exc}")
        st.caption("Try exporting it as a conventional CSV with a header row.")


if __name__ == "__main__":
    main()
