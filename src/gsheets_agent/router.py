"""Tiny router: a small/fast LLM picks which tier should handle the user turn."""
from __future__ import annotations

import json
from typing import Literal

from openai import OpenAI

from gsheets_agent.config import COMPLEX_MODEL, FORCE_TIER, LIGHT_MODEL, ROUTER_MODEL

Tier = Literal["complex", "light"]


_ROUTER_SYSTEM = """Classify a user request for a Google Sheets/Gmail agent. Return JSON: {"tier": "light" | "complex", "reason": "one sentence"}.

"complex" — requires reasoning, multi-step planning, or heavy data work:
- Data manipulation: sorting, deduplication, merging, restructuring
- Math/formulas: calculations, aggregations, building formula columns
- Graph/chart generation
- Conditional logic or transformations across rows
- Drafting prose (emails, summaries)
- Anything involving more than 3 tool calls

"light" — straightforward single actions:
- Simple lookups: read a range, list sheets, search by name
- Simple writes: add a row, update a cell, create a sheet
- Formatting: bold, colors, date format changes
- Sharing, renaming, general questions about the sheet

When uncertain, prefer "complex"."""


def pick_tier(user_message: str, client: OpenAI) -> tuple[Tier, str, str]:
    """Return (tier, model_name, reason)."""
    if FORCE_TIER in ("complex", "light"):
        model = COMPLEX_MODEL if FORCE_TIER == "complex" else LIGHT_MODEL
        return FORCE_TIER, model, "FORCE_TIER env override"

    try:
        resp = client.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        tier: Tier = "complex" if data.get("tier") == "complex" else "light"
        reason = str(data.get("reason", ""))[:200]
    except Exception as e:  # noqa: BLE001
        tier = "complex"
        reason = f"router_error: {e}"

    model = COMPLEX_MODEL if tier == "complex" else LIGHT_MODEL
    return tier, model, reason
