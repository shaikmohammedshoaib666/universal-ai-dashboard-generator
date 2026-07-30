"""A transparent insight engine: every statement is traceable to the dataframe."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .cleaning import CleaningSummary


@dataclass
class Insight:
    title: str
    finding: str
    detail: str
    category: str
    priority: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fmt(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    if abs(float(value)) >= 1_000_000:
        return f"{float(value) / 1_000_000:.2f}M"
    if abs(float(value)) >= 1_000:
        return f"{float(value) / 1_000:.1f}K"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.2f}"


def _fallback(title: str, finding: str, detail: str) -> Insight:
    return Insight(title=title, finding=finding, detail=detail, category="Data profile")


def generate_insights(frame: pd.DataFrame, summary: CleaningSummary) -> list[Insight]:
    """Return ten measured findings, degrading gracefully for very sparse CSVs."""
    insights: list[Insight] = []
    rows, columns = frame.shape
    cells = max(rows * columns, 1)
    missing_pct = summary.missing_cells / cells * 100
    insights.append(Insight(
        "Dataset readiness",
        f"{rows:,} clean rows across {columns} columns are ready to explore.",
        f"Cleaning removed {summary.duplicate_rows_removed:,} duplicate row(s); {missing_pct:.1f}% of remaining cells are blank.",
        "Data quality", 2,
    ))

    if summary.missing_cells:
        missing_by_column = frame.isna().sum().sort_values(ascending=False)
        worst = missing_by_column.iloc[0]
        column = missing_by_column.index[0]
        insights.append(Insight(
            "Missing-data watch",
            f"{column} has the most missing values ({int(worst):,}, {worst / max(rows, 1) * 100:.1f}%).",
            "Consider completing, excluding, or explicitly labeling these records before making decisions from this field.",
            "Data quality", 3,
        ))
    else:
        insights.append(_fallback(
            "Complete records",
            "No missing values remain after cleaning.",
            "All available fields are populated, reducing the risk of analysis bias from blank cells.",
        ))

    numeric = summary.numeric_columns
    if numeric:
        dispersion = frame[numeric].std(numeric_only=True).dropna().sort_values(ascending=False)
        if not dispersion.empty:
            col = dispersion.index[0]
            median = frame[col].median()
            insights.append(Insight(
                "Largest variation",
                f"{col} varies most across records (standard deviation {_fmt(dispersion.iloc[0])}).",
                f"Its median is {_fmt(median)}; investigate the upper and lower ranges for operational drivers.",
                "Distribution", 2,
            ))

        skewness = frame[numeric].skew(numeric_only=True).dropna().abs().sort_values(ascending=False)
        if not skewness.empty:
            col, skew = skewness.index[0], skewness.iloc[0]
            direction = "right" if frame[col].skew() > 0 else "left"
            insights.append(Insight(
                "Skewed distribution",
                f"{col} is the least symmetric metric (skew {skew:.2f}, leaning {direction}).",
                "Use median and percentile views alongside averages so extreme records do not dominate the story.",
                "Distribution", 2,
            ))

        outlier_rates: list[tuple[str, float, int]] = []
        for col in numeric:
            values = frame[col].dropna()
            if len(values) >= 4:
                q1, q3 = values.quantile([0.25, 0.75])
                iqr = q3 - q1
                if iqr > 0:
                    count = int(((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).sum())
                    outlier_rates.append((col, count / len(values), count))
        if outlier_rates:
            col, rate, count = max(outlier_rates, key=lambda item: item[1])
            insights.append(Insight(
                "Unusual records",
                f"{count:,} {col} values ({rate:.1%}) sit outside the standard IQR range.",
                "These are not automatically errors—review them as unusually high- or low-impact cases.",
                "Distribution", 2,
            ))

        if len(numeric) >= 2:
            correlations = frame[numeric].corr(numeric_only=True)
            pairs: list[tuple[float, str, str, float]] = []
            for index, first in enumerate(correlations.columns):
                for second in correlations.columns[index + 1:]:
                    corr = correlations.loc[first, second]
                    if pd.notna(corr):
                        pairs.append((abs(corr), first, second, corr))
            if pairs:
                _, first, second, corr = max(pairs)
                direction = "move together" if corr >= 0 else "move in opposite directions"
                insights.append(Insight(
                    "Strongest relationship",
                    f"{first} and {second} {direction} (correlation {corr:.2f}).",
                    "Correlation identifies a useful relationship to investigate; it does not establish causation.",
                    "Relationships", 3,
                ))

    if summary.categorical_columns:
        concentrations: list[tuple[float, str, str, int, int]] = []
        for col in summary.categorical_columns:
            counts = frame[col].value_counts(dropna=True)
            if not counts.empty:
                concentrations.append((counts.iloc[0] / counts.sum(), col, str(counts.index[0]), int(counts.iloc[0]), int(counts.sum())))
        if concentrations:
            share, col, leader, count, total = max(concentrations, key=lambda item: item[0])
            insights.append(Insight(
                "Category concentration",
                f"{leader} accounts for {share:.1%} of known {col} records ({count:,} of {total:,}).",
                "A high concentration can signal a primary customer segment, market, product, or operational dependency.",
                "Composition", 2,
            ))

        cardinalities = [(frame[col].nunique(dropna=True), col) for col in summary.categorical_columns]
        if cardinalities:
            count, col = max(cardinalities)
            insights.append(Insight(
                "Most diverse dimension",
                f"{col} contains {count:,} distinct non-empty values.",
                "Use it as a segmentation lens, but group long tails in charts to keep comparisons readable.",
                "Composition",
            ))

    if summary.date_columns and numeric:
        date_col = summary.date_columns[0]
        metric = numeric[0]
        series = frame[[date_col, metric]].dropna().sort_values(date_col)
        if len(series) >= 4:
            grouped = series.groupby(pd.Grouper(key=date_col, freq="ME"))[metric].mean().dropna()
            if len(grouped) >= 2 and grouped.iloc[0] != 0:
                change = (grouped.iloc[-1] - grouped.iloc[0]) / abs(grouped.iloc[0])
                wording = "increased" if change >= 0 else "decreased"
                insights.append(Insight(
                    "Time trend",
                    f"Average {metric} {wording} {abs(change):.1%} from the first to last observed month.",
                    f"Based on {len(grouped)} monthly periods spanning {grouped.index.min():%b %Y} to {grouped.index.max():%b %Y}.",
                    "Trend", 3,
                ))

    if numeric:
        completeness = frame[numeric].notna().mean().sort_values(ascending=False)
        if not completeness.empty:
            col, rate = completeness.index[0], completeness.iloc[0]
            insights.append(Insight(
                "Reliable metric",
                f"{col} is populated for {rate:.1%} of rows.",
                "It is a strong default choice for aggregation and comparison in the dashboard.",
                "Data quality",
            ))

    fallbacks = [
        ("Schema breadth", f"The file has {columns} analysis-ready fields.", "Add a short data dictionary so other users can interpret each field consistently."),
        ("Record volume", f"The dataset contains {rows:,} usable records.", "Filter by a business-relevant segment to turn broad patterns into focused next actions."),
        ("Repeatable baseline", "This cleaned dataset has been prepared for repeat reporting.", "Save it for automation to compare future reports against the same baseline."),
        ("Exploration prompt", "Use the chart builder to test the most relevant category and metric combinations.", "The strongest decisions usually combine one segmentation field, one measure, and one time period."),
    ]
    for title, finding, detail in fallbacks:
        if len(insights) >= 10:
            break
        insights.append(_fallback(title, finding, detail))

    return insights[:10]
