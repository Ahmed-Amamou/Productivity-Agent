"""Tiny router: a small/fast LLM picks which tier should handle the user turn."""
from __future__ import annotations

import json
from typing import Literal

from openai import OpenAI

from gsheets_agent.config import COMPLEX_MODEL, FORCE_TIER, LIGHT_MODEL, ROUTER_MODEL

Tier = Literal["complex", "light"]


_ROUTER_SYSTEM = """You classify the difficulty of a user request for an agent that can read and write Google Sheets and operate Gmail across multiple accounts.

Return JSON of the form: {"tier": "light" | "complex", "reason": "..."}.

- "light": single, well-specified read/write/lookup; one or two tool calls; no transformation logic.
  Examples: "read A1:D10 in sheet X", "list my unread emails from boss@x.com", "create a tab called Q3", "share this sheet with alice@x.com".

- "complex": multi-step planning, data transformation, summarization, conditional logic, drafting prose, or anything that benefits from reasoning.
  Examples: "clean up this sheet, dedupe rows by email, normalize dates, write totals", "find all invoices over $1k from last month and add them as rows in the Tracker tab", "draft a follow-up email to everyone who hasn't replied".

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
