"""Optional LLM enrichment, deliberately limited to aggregate statistics."""

from __future__ import annotations

import json
import os
from typing import Iterable

from .insights import Insight


def build_executive_summary(insights: Iterable[Insight]) -> str | None:
    """Create a concise narrative from computed findings, never raw CSV rows."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    findings = [item.to_dict() for item in insights]
    prompt = (
        "Write a concise executive summary (120 words max) of these verified data "
        "findings. State trends and risks carefully, do not invent causes or metrics, "
        "and end with 2 practical actions. Findings:\n"
        + json.dumps(findings, ensure_ascii=False)
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt,
        )
        return response.output_text.strip() or None
    except Exception:
        # The dashboard remains fully functional if an optional API is unavailable.
        return None
