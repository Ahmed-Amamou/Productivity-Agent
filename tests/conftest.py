"""Shared pytest fixtures: temp credentials dir, fake services, fake OpenAI client."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_credentials(tmp_path, monkeypatch):
    """Redirect CREDENTIALS_DIR (in both config and auth modules) to a tmp dir."""
    cred_dir = tmp_path / "credentials"
    cred_dir.mkdir()
    oauth_file = cred_dir / "oauth_client.json"
    # Both modules took `from ... import CREDENTIALS_DIR`, so each has its own ref.
    for target in (
        "gsheets_agent.config.CREDENTIALS_DIR",
        "gsheets_agent.config.OAUTH_CLIENT_FILE",
        "gsheets_agent.auth.CREDENTIALS_DIR",
        "gsheets_agent.auth.OAUTH_CLIENT_FILE",
    ):
        monkeypatch.setattr(
            target,
            oauth_file if target.endswith("OAUTH_CLIENT_FILE") else cred_dir,
        )
    return cred_dir


@pytest.fixture
def fake_credentials():
    """A creds-like object that's not expired."""
    creds = MagicMock()
    creds.expired = False
    creds.refresh_token = "refresh-xyz"
    return creds


# ---- OpenAI helpers --------------------------------------------------------

def _oai_message(content: str | None = None, tool_calls: list | None = None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _oai_tool_call(call_id: str, name: str, arguments: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


@pytest.fixture
def oai_message():
    return _oai_message


@pytest.fixture
def oai_tool_call():
    return _oai_tool_call


@pytest.fixture
def fake_openai_client():
    """A MagicMock OpenAI client; configure .chat.completions.create on demand."""
    client = MagicMock()
    return client
