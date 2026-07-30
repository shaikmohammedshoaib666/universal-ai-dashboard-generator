"""CSV ingestion and conservative, auditable data cleaning."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

import pandas as pd


MISSING_MARKERS = {"", "na", "n/a", "null", "none", "nan", "-", "?"}


@dataclass
class CleaningSummary:
    original_rows: int
    cleaned_rows: int
    original_columns: int
    cleaned_columns: int
    duplicate_rows_removed: int
    missing_cells: int
    numeric_columns: list[str]
    date_columns: list[str]
    categorical_columns: list[str]


def _normalise_column(name: object, index: int, used: set[str]) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    value = value or f"column_{index + 1}"
    base, counter = value, 2
    while value in used:
        value = f"{base}_{counter}"
        counter += 1
    used.add(value)
    return value


def _read_with_fallback(upload: bytes | BinaryIO) -> pd.DataFrame:
    """Read a CSV while handling common real-world encodings and delimiters."""
    raw = upload if isinstance(upload, bytes) else upload.read()
    if not raw:
        raise ValueError("The uploaded file is empty.")

    sample = raw[:8192].decode("utf-8-sig", errors="replace")
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","

    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(
                BytesIO(raw), encoding=encoding, sep=delimiter, low_memory=False
            )
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError("Could not parse the CSV. " + " | ".join(errors))


def load_and_clean_csv(upload: bytes | BinaryIO) -> tuple[pd.DataFrame, CleaningSummary]:
    """Load a CSV and make low-risk fixes without inventing or deleting data."""
    frame = _read_with_fallback(upload)
    original_rows, original_columns = frame.shape

    used: set[str] = set()
    frame.columns = [
        _normalise_column(name, index, used) for index, name in enumerate(frame.columns)
    ]

    # Keep text values intact, but make blanks and common placeholders consistent.
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        text = frame[column].astype("string").str.strip()
        frame[column] = text.mask(text.str.lower().isin(MISSING_MARKERS))

    # Convert values to numeric only when the overwhelming majority are numbers.
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        source = frame[column]
        non_null = source.dropna()
        if len(non_null) < 3:
            continue
        candidate = pd.to_numeric(
            non_null.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.replace("%", "", regex=False),
            errors="coerce",
        )
        if candidate.notna().mean() >= 0.85:
            converted = pd.to_numeric(
                source.astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("$", "", regex=False)
                .str.replace("%", "", regex=False),
                errors="coerce",
            )
            frame[column] = converted

    # Date parsing is opt-in by a date-like field name, avoiding accidental ID conversion.
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        if re.search(r"date|time|month|year|day", column, flags=re.IGNORECASE):
            parsed = pd.to_datetime(frame[column], errors="coerce", utc=False)
            original_non_null = frame[column].notna().sum()
            if original_non_null and parsed.notna().sum() / original_non_null >= 0.75:
                frame[column] = parsed

    before_deduplication = len(frame)
    frame = frame.drop_duplicates().reset_index(drop=True)
    duplicate_rows_removed = before_deduplication - len(frame)

    numeric_columns = frame.select_dtypes(include="number").columns.tolist()
    date_columns = frame.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    categorical_columns = [
        column
        for column in frame.columns
        if column not in numeric_columns + date_columns and frame[column].nunique(dropna=True) <= 100
    ]
    summary = CleaningSummary(
        original_rows=original_rows,
        cleaned_rows=len(frame),
        original_columns=original_columns,
        cleaned_columns=len(frame.columns),
        duplicate_rows_removed=duplicate_rows_removed,
        missing_cells=int(frame.isna().sum().sum()),
        numeric_columns=numeric_columns,
        date_columns=date_columns,
        categorical_columns=categorical_columns,
    )
    return frame, summary


def load_cleaned_csv(path: str) -> tuple[pd.DataFrame, CleaningSummary]:
    """Load a persisted cleaned dataset while restoring likely datetime fields."""
    frame = pd.read_csv(path)
    for column in frame.columns:
        if re.search(r"date|time|month|year|day", column, flags=re.IGNORECASE):
            parsed = pd.to_datetime(frame[column], errors="coerce")
            if len(frame) and parsed.notna().mean() >= 0.75:
                frame[column] = parsed
    return frame, profile_dataframe(frame)


def profile_dataframe(frame: pd.DataFrame) -> CleaningSummary:
    """Create an analysis profile for an already-clean dataframe or filtered view."""
    numeric_columns = frame.select_dtypes(include="number").columns.tolist()
    date_columns = frame.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    categorical_columns = [
        col
        for col in frame.columns
        if col not in numeric_columns + date_columns and frame[col].nunique(dropna=True) <= 100
    ]
    return CleaningSummary(
        original_rows=len(frame), cleaned_rows=len(frame), original_columns=len(frame.columns),
        cleaned_columns=len(frame.columns), duplicate_rows_removed=0,
        missing_cells=int(frame.isna().sum().sum()), numeric_columns=numeric_columns,
        date_columns=date_columns, categorical_columns=categorical_columns,
    )
