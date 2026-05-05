"""Agent loop: calls the chosen model with the tool catalog and runs tool calls until done."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from openai import OpenAI
from rich.console import Console

from gsheets_agent.auth import list_accounts
from gsheets_agent.config import OPENAI_API_KEY
from gsheets_agent.router import pick_tier
from gsheets_agent.tools import ALL_TOOLS, dispatch

console = Console()

MAX_TOOL_ITERATIONS = 12


def _system_prompt() -> str:
    accs = list_accounts()
    if accs:
        accs_str = "\n".join(f"- label='{a.label}' email='{a.email}'" for a in accs)
    else:
        accs_str = "(none authorized yet — instruct the user to run: gsa auth add <label>)"
    return f"""You are a CLI agent that operates Google Sheets and Gmail on behalf of the user via tool calls.

Authorized accounts:
{accs_str}

Rules:
- Every tool that touches a Google account accepts an `account` parameter (the label). If the user mentions which account to use ("from work", "in my personal inbox"), pass that label. Otherwise omit and the default (first) account is used.
- A spreadsheet may be referenced by its full URL or by its id; tools accept either.
- Before writing or formatting a range, if you don't already know the tab names and shape, call `sheets_get` first.
- For Gmail searches, use Gmail query syntax (e.g. `from:`, `to:`, `newer_than:7d`, `is:unread`, `has:attachment`).
- When sending an email, confirm the recipient and a one-line summary in your final reply.
- Be concise in chat output. Show URLs/ids when you create things."""


@dataclass
class AgentSession:
    client: OpenAI = field(default_factory=lambda: OpenAI(api_key=OPENAI_API_KEY))
    messages: list[dict] = field(default_factory=list)
    on_event: Callable[[str, dict], None] | None = None  # (event_type, payload)

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages.append({"role": "system", "content": _system_prompt()})

    def _emit(self, event: str, payload: dict) -> None:
        if self.on_event:
            self.on_event(event, payload)

    def send(self, user_message: str) -> str:
        tier, model, reason = pick_tier(user_message, self.client)
        self._emit("router", {"tier": tier, "model": model, "reason": reason})

        self.messages.append({"role": "user", "content": user_message})

        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self.client.chat.completions.create(
                model=model,
                messages=self.messages,
                tools=ALL_TOOLS,
                tool_choice="auto",
            )
            msg = resp.choices[0].message

            # Persist assistant message (with tool_calls if any).
            assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            self.messages.append(assistant_entry)

            if not msg.tool_calls:
                return msg.content or ""

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                self._emit("tool_call", {"name": name, "args": args})
                try:
                    result = dispatch(name, args)
                except Exception as e:  # noqa: BLE001
                    result = json.dumps({"error": type(e).__name__, "details": str(e)})
                self._emit("tool_result", {"name": name, "result": result})
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return "(stopped: hit MAX_TOOL_ITERATIONS — try a smaller request)"
