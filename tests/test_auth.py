"""Tests for auth helpers that don't touch the network."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from gsheets_agent import auth as auth_mod


# ---- _is_headless ---------------------------------------------------------

def test_is_headless_detects_wsl(monkeypatch):
    monkeypatch.setattr(auth_mod.platform, "uname", lambda: type("U", (), {"release": "5.15-microsoft-standard-WSL2"})())
    monkeypatch.setattr(auth_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":0")  # would be non-headless if not for WSL
    assert auth_mod._is_headless() is True


def test_is_headless_detects_ssh(monkeypatch):
    monkeypatch.setattr(auth_mod.platform, "uname", lambda: type("U", (), {"release": "6.0-generic"})())
    monkeypatch.setattr(auth_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 22 5.6.7.8 22")
    assert auth_mod._is_headless() is True


def test_is_headless_false_on_desktop_linux(monkeypatch):
    monkeypatch.setattr(auth_mod.platform, "uname", lambda: type("U", (), {"release": "6.0-generic"})())
    monkeypatch.setattr(auth_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    assert auth_mod._is_headless() is False


# ---- save / load roundtrip -----------------------------------------------

def test_save_credentials_writes_json_with_safe_perms(tmp_credentials, monkeypatch):
    creds = MagicMock()
    creds.to_json.return_value = json.dumps({"refresh_token": "xyz"})
    auth_mod._save_credentials("work", creds)
    p = tmp_credentials / "token-work.json"
    assert p.exists()
    # POSIX-only sanity check: chmod was attempted to 0600
    if os.name == "posix":
        assert (p.stat().st_mode & 0o777) == 0o600


def test_load_credentials_returns_none_when_missing(tmp_credentials):
    assert auth_mod._load_credentials("nope") is None


def test_load_credentials_refreshes_when_expired(tmp_credentials, monkeypatch):
    p = tmp_credentials / "token-work.json"
    p.write_text(json.dumps({"refresh_token": "xyz"}))

    fake_creds = MagicMock(expired=True, refresh_token="xyz")
    fake_creds.to_json.return_value = json.dumps({"refresh_token": "xyz"})

    fake_credentials_class = MagicMock()
    fake_credentials_class.from_authorized_user_file.return_value = fake_creds

    with patch("google.oauth2.credentials.Credentials", fake_credentials_class), \
         patch("google.auth.transport.requests.Request"):
        result = auth_mod._load_credentials("work")

    assert result is fake_creds
    fake_creds.refresh.assert_called_once()


# ---- list / remove --------------------------------------------------------

def test_list_accounts_uses_cached_email_when_present(tmp_credentials):
    p = tmp_credentials / "token-personal.json"
    p.write_text(json.dumps({"refresh_token": "xyz", "_email": "me@example.com"}))

    fake_creds = MagicMock(expired=False, refresh_token="xyz")
    with patch("google.oauth2.credentials.Credentials") as Creds:
        Creds.from_authorized_user_file.return_value = fake_creds
        accounts = auth_mod.list_accounts()

    assert len(accounts) == 1
    assert accounts[0].label == "personal"
    assert accounts[0].email == "me@example.com"


def test_remove_account_deletes_token(tmp_credentials):
    p = tmp_credentials / "token-work.json"
    p.write_text("{}")
    assert auth_mod.remove_account("work") is True
    assert not p.exists()


def test_remove_account_returns_false_when_missing(tmp_credentials):
    assert auth_mod.remove_account("ghost") is False


def test_default_label_picks_first(tmp_credentials):
    (tmp_credentials / "token-aaa.json").write_text(json.dumps({"_email": "a@x"}))
    (tmp_credentials / "token-bbb.json").write_text(json.dumps({"_email": "b@x"}))
    with patch("google.oauth2.credentials.Credentials") as Creds:
        Creds.from_authorized_user_file.return_value = MagicMock(expired=False, refresh_token="r")
        assert auth_mod.default_label() == "aaa"


def test_get_credentials_raises_if_unknown(tmp_credentials):
    with pytest.raises(RuntimeError):
        auth_mod.get_credentials("ghost")


def test_add_account_raises_when_oauth_client_missing(tmp_credentials):
    # OAUTH_CLIENT_FILE doesn't exist in tmp_credentials
    with pytest.raises(FileNotFoundError):
        auth_mod.add_account("work")
