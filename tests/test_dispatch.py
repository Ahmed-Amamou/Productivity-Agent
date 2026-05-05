"""Tests for the tool dispatcher and tool implementations (with mocked Google services)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from gsheets_agent.tools import ALL_TOOLS, dispatch
from gsheets_agent.tools import sheets as sheets_tools
from gsheets_agent.tools import gmail as gmail_tools


# ---- Routing --------------------------------------------------------------

def test_dispatch_routes_sheets_prefix(monkeypatch):
    monkeypatch.setattr(sheets_tools, "dispatch_sheets_tool", lambda n, a: json.dumps({"ok": n}))
    monkeypatch.setattr("gsheets_agent.tools.dispatch_sheets_tool", lambda n, a: json.dumps({"ok": n}))
    out = dispatch("sheets_get", {})
    assert json.loads(out) == {"ok": "sheets_get"}


def test_dispatch_routes_drive_prefix(monkeypatch):
    monkeypatch.setattr("gsheets_agent.tools.dispatch_sheets_tool", lambda n, a: json.dumps({"ok": n}))
    out = dispatch("drive_list_spreadsheets", {})
    assert json.loads(out) == {"ok": "drive_list_spreadsheets"}


def test_dispatch_routes_gmail_prefix(monkeypatch):
    monkeypatch.setattr("gsheets_agent.tools.dispatch_gmail_tool", lambda n, a: json.dumps({"ok": n}))
    out = dispatch("gmail_send", {})
    assert json.loads(out) == {"ok": "gmail_send"}


def test_dispatch_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        dispatch("unknown_tool", {})


def test_all_tools_have_unique_names():
    names = [t["function"]["name"] for t in ALL_TOOLS]
    assert len(names) == len(set(names))


def test_all_tools_have_required_schema_fields():
    for t in ALL_TOOLS:
        assert t["type"] == "function"
        fn = t["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn


# ---- Sheets implementations (with mocked googleapiclient services) -------

@pytest.fixture
def mock_sheets_service(monkeypatch):
    """Replace _sheets_service / _drive_service / _account with mocks."""
    sheets_svc = MagicMock()
    drive_svc = MagicMock()

    monkeypatch.setattr(sheets_tools, "_sheets_service", lambda label: sheets_svc)
    monkeypatch.setattr(sheets_tools, "_drive_service", lambda label: drive_svc)
    monkeypatch.setattr(sheets_tools, "_account", lambda label: label or "work")
    return sheets_svc, drive_svc


def test_sheets_create_calls_api(mock_sheets_service):
    sheets_svc, _ = mock_sheets_service
    sheets_svc.spreadsheets().create().execute.return_value = {
        "spreadsheetId": "abc", "spreadsheetUrl": "u", "properties": {"title": "t"}
    }
    res = sheets_tools.create_spreadsheet("My Sheet", account="work")
    assert res["account"] == "work"
    assert res["spreadsheetId"] == "abc"


def test_sheets_read_range_normalizes_url(mock_sheets_service):
    sheets_svc, _ = mock_sheets_service
    sheets_svc.spreadsheets().values().get().execute.return_value = {
        "range": "S!A1:B2", "values": [[1, 2]]
    }
    url = "https://docs.google.com/spreadsheets/d/SHEET123/edit"
    res = sheets_tools.read_range(url, "S!A1:B2", account="work")
    # Verify the normalized id was passed to the API
    call_kwargs = sheets_svc.spreadsheets().values().get.call_args.kwargs
    assert call_kwargs["spreadsheetId"] == "SHEET123"
    assert res["values"] == [[1, 2]]


def test_sheets_share_calls_drive_permissions(mock_sheets_service):
    _, drive_svc = mock_sheets_service
    drive_svc.permissions().create().execute.return_value = {"id": "perm-1", "role": "writer", "emailAddress": "a@x"}
    res = sheets_tools.share_spreadsheet("SID", "a@x", role="writer", account="work")
    assert res["permission"]["role"] == "writer"


def test_dispatch_sheets_tool_serializes_to_json(mock_sheets_service):
    sheets_svc, _ = mock_sheets_service
    sheets_svc.spreadsheets().create().execute.return_value = {"spreadsheetId": "X"}
    raw = sheets_tools.dispatch_sheets_tool("sheets_create", {"title": "T"})
    parsed = json.loads(raw)
    assert parsed["spreadsheetId"] == "X"


def test_dispatch_sheets_tool_returns_error_json_on_exception(mock_sheets_service):
    sheets_svc, _ = mock_sheets_service
    sheets_svc.spreadsheets().create().execute.side_effect = RuntimeError("boom")
    raw = sheets_tools.dispatch_sheets_tool("sheets_create", {"title": "T"})
    parsed = json.loads(raw)
    assert parsed["error"] == "RuntimeError"


# ---- Gmail implementations ------------------------------------------------

@pytest.fixture
def mock_gmail_service(monkeypatch):
    g = MagicMock()
    monkeypatch.setattr(gmail_tools, "_gmail", lambda label: g)
    monkeypatch.setattr(gmail_tools, "_account", lambda label: label or "work")
    return g


def test_gmail_send_builds_proper_payload(mock_gmail_service):
    g = mock_gmail_service
    g.users().messages().send().execute.return_value = {"id": "msg1", "threadId": "t1"}
    res = gmail_tools.send_message(to="a@x", subject="hi", body="hey", account="work")
    assert res == {"account": "work", "id": "msg1", "threadId": "t1"}
    send_call = g.users().messages().send.call_args
    body = send_call.kwargs["body"]
    assert "raw" in body
    # Confirm raw is base64 and contains our subject
    import base64
    raw_bytes = base64.urlsafe_b64decode(body["raw"].encode())
    assert b"Subject: hi" in raw_bytes
    assert b"To: a@x" in raw_bytes


def test_gmail_create_draft_returns_ids(mock_gmail_service):
    g = mock_gmail_service
    g.users().drafts().create().execute.return_value = {
        "id": "d1", "message": {"id": "m1"}
    }
    res = gmail_tools.create_draft(to="a@x", subject="s", body="b", account="work")
    assert res["draft_id"] == "d1"
    assert res["message_id"] == "m1"


def test_gmail_dispatch_returns_error_json_on_exception(mock_gmail_service):
    g = mock_gmail_service
    g.users().messages().send().execute.side_effect = ValueError("nope")
    raw = gmail_tools.dispatch_gmail_tool(
        "gmail_send", {"to": "a@x", "subject": "s", "body": "b"}
    )
    parsed = json.loads(raw)
    assert parsed["error"] == "ValueError"
