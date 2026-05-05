"""Tests for the CLI surface using typer's CliRunner."""
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsheets_agent.auth import Account
from gsheets_agent.cli import app

runner = CliRunner()


def test_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "auth" in result.stdout
    assert "chat" in result.stdout
    assert "ask" in result.stdout


def test_accounts_empty(monkeypatch):
    monkeypatch.setattr("gsheets_agent.cli.auth_mod.list_accounts", lambda: [])
    result = runner.invoke(app, ["accounts"])
    assert result.exit_code == 0
    assert "No accounts" in result.stdout


def test_accounts_lists_authorized(monkeypatch):
    monkeypatch.setattr(
        "gsheets_agent.cli.auth_mod.list_accounts",
        lambda: [Account("work", "me@example.com")],
    )
    result = runner.invoke(app, ["accounts"])
    assert result.exit_code == 0
    assert "work" in result.stdout
    assert "me@example.com" in result.stdout


def test_auth_add_invokes_helper(monkeypatch):
    called = {}

    def fake_add(label):
        called["label"] = label
        return Account(label, "me@example.com")

    monkeypatch.setattr("gsheets_agent.cli.auth_mod.add_account", fake_add)
    result = runner.invoke(app, ["auth", "add", "work"])
    assert result.exit_code == 0
    assert called["label"] == "work"
    assert "Authorized" in result.stdout


def test_auth_add_handles_missing_oauth_client(monkeypatch):
    def fake_add(label):
        raise FileNotFoundError("oauth_client.json not found")

    monkeypatch.setattr("gsheets_agent.cli.auth_mod.add_account", fake_add)
    result = runner.invoke(app, ["auth", "add", "work"])
    assert result.exit_code == 1
    assert "oauth_client.json" in result.stdout


def test_auth_remove_success(monkeypatch):
    monkeypatch.setattr("gsheets_agent.cli.auth_mod.remove_account", lambda lbl: True)
    result = runner.invoke(app, ["auth", "remove", "work"])
    assert result.exit_code == 0
    assert "Removed" in result.stdout


def test_auth_remove_missing(monkeypatch):
    monkeypatch.setattr("gsheets_agent.cli.auth_mod.remove_account", lambda lbl: False)
    result = runner.invoke(app, ["auth", "remove", "ghost"])
    assert result.exit_code == 1


def test_ask_requires_openai_key(monkeypatch):
    monkeypatch.setattr("gsheets_agent.cli.OPENAI_API_KEY", "")
    result = runner.invoke(app, ["ask", "do something"])
    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.stdout


def test_ask_invokes_agent(monkeypatch):
    monkeypatch.setattr("gsheets_agent.cli.OPENAI_API_KEY", "sk-fake")

    fake_session = MagicMock()
    fake_session.send.return_value = "agent reply"

    fake_agent_module = MagicMock()
    fake_agent_module.AgentSession = MagicMock(return_value=fake_session)

    with patch.dict("sys.modules", {"gsheets_agent.agent": fake_agent_module}):
        result = runner.invoke(app, ["ask", "hello"])
    assert result.exit_code == 0
    assert "agent reply" in result.stdout
    fake_session.send.assert_called_once_with("hello")
