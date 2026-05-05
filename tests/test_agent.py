"""Tests for the agent loop with mocked OpenAI tool-calling."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import gsheets_agent.agent as agent_mod


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


def _tc(call_id, name, args):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


@pytest.fixture
def patched_session(monkeypatch):
    """An AgentSession with router pinned to 'light' and dispatch mocked."""
    monkeypatch.setattr(agent_mod, "pick_tier", lambda msg, client: ("light", "light-x", "test"))
    monkeypatch.setattr(agent_mod, "list_accounts", lambda: [])
    fake_client = MagicMock()
    s = agent_mod.AgentSession(client=fake_client)
    return s, fake_client


def test_agent_returns_assistant_text_when_no_tool_calls(patched_session):
    s, client = patched_session
    client.chat.completions.create.return_value = _msg(content="all done")
    out = s.send("hi")
    assert out == "all done"
    # 1 system + 1 user + 1 assistant
    assert len(s.messages) == 3
    assert s.messages[-1]["role"] == "assistant"


def test_agent_executes_tool_calls_then_finishes(patched_session, monkeypatch):
    s, client = patched_session
    # First response: one tool call. Second response: final text.
    client.chat.completions.create.side_effect = [
        _msg(tool_calls=[_tc("c1", "sheets_read_range", {"spreadsheet_id": "X", "range": "A1:B2"})]),
        _msg(content="here are your values"),
    ]
    monkeypatch.setattr(agent_mod, "dispatch", lambda name, args: json.dumps({"values": [[1, 2]]}))

    out = s.send("read X")
    assert out == "here are your values"
    # system, user, assistant(tool_call), tool, assistant(final)
    roles = [m["role"] for m in s.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]


def test_agent_records_tool_errors_as_results(patched_session, monkeypatch):
    s, client = patched_session
    client.chat.completions.create.side_effect = [
        _msg(tool_calls=[_tc("c1", "sheets_read_range", {})]),
        _msg(content="recovered"),
    ]

    def boom(name, args):
        raise RuntimeError("simulated tool failure")

    monkeypatch.setattr(agent_mod, "dispatch", boom)
    out = s.send("read X")
    assert out == "recovered"
    tool_msg = [m for m in s.messages if m["role"] == "tool"][0]
    parsed = json.loads(tool_msg["content"])
    assert parsed["error"] == "RuntimeError"


def test_agent_emits_events(patched_session, monkeypatch):
    s, client = patched_session
    client.chat.completions.create.side_effect = [
        _msg(tool_calls=[_tc("c1", "sheets_get", {"spreadsheet_id": "X"})]),
        _msg(content="ok"),
    ]
    monkeypatch.setattr(agent_mod, "dispatch", lambda n, a: '{"ok": true}')

    events = []
    s.on_event = lambda ev, payload: events.append((ev, payload))
    s.send("x")

    types_seen = [e[0] for e in events]
    assert "router" in types_seen
    assert "tool_call" in types_seen
    assert "tool_result" in types_seen


def test_agent_stops_after_max_iterations(patched_session, monkeypatch):
    s, client = patched_session
    monkeypatch.setattr(agent_mod, "MAX_TOOL_ITERATIONS", 3)
    # Always return a tool call -> infinite loop guarded by max iterations
    client.chat.completions.create.return_value = _msg(
        tool_calls=[_tc("c1", "sheets_get", {"spreadsheet_id": "X"})]
    )
    monkeypatch.setattr(agent_mod, "dispatch", lambda n, a: '{"ok": true}')

    out = s.send("loop forever")
    assert "MAX_TOOL_ITERATIONS" in out
    assert client.chat.completions.create.call_count == 3


def test_agent_passes_tools_to_openai(patched_session):
    s, client = patched_session
    client.chat.completions.create.return_value = _msg(content="done")
    s.send("hi")
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert "tools" in call_kwargs and len(call_kwargs["tools"]) > 0
    assert call_kwargs["tool_choice"] == "auto"
    assert call_kwargs["model"] == "light-x"
