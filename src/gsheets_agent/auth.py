"""Google OAuth - per-account token storage with strict perms.

Uses the InstalledAppFlow loopback flow (Google's recommended approach for desktop
clients): a one-shot HTTP server on 127.0.0.1 receives the auth code; the refresh
token is then stored on disk at 0600.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from gsheets_agent.config import (
    CREDENTIALS_DIR,
    OAUTH_CLIENT_FILE,
    SCOPES,
    token_path,
)


@dataclass
class Account:
    label: str
    email: str

    def __str__(self) -> str:
        return f"{self.label} <{self.email}>"


def _save_credentials(label: str, creds: Credentials) -> None:
    path = token_path(label)
    path.write_text(creds.to_json())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows / WSL on NTFS: best-effort.


def _load_credentials(label: str) -> Optional[Credentials]:
    path = token_path(label)
    if not path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(label, creds)
    return creds


def _email_for(creds: Credentials) -> str:
    svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
    info = svc.userinfo().get().execute()
    return info.get("email", "unknown")


def add_account(label: str) -> Account:
    """Run the loopback OAuth flow and persist the token."""
    if not OAUTH_CLIENT_FILE.exists():
        raise FileNotFoundError(
            f"OAuth client file not found at {OAUTH_CLIENT_FILE}. "
            "Download it from Google Cloud Console (Desktop app credentials)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CLIENT_FILE), SCOPES)
    # port=0 picks a random free local port; access_type=offline to get a refresh token.
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        open_browser=True,
        authorization_prompt_message="Authorize {url}",
        success_message="Authorization complete. You can close this tab.",
    )
    _save_credentials(label, creds)
    email = _email_for(creds)
    return Account(label=label, email=email)


def remove_account(label: str) -> bool:
    path = token_path(label)
    if path.exists():
        path.unlink()
        return True
    return False


def list_accounts() -> list[Account]:
    accounts: list[Account] = []
    for path in sorted(CREDENTIALS_DIR.glob("token-*.json")):
        label = path.stem.removeprefix("token-")
        try:
            creds = _load_credentials(label)
            if not creds:
                continue
            data = json.loads(path.read_text())
            email = data.get("_email")
            if not email:
                email = _email_for(creds)
                data["_email"] = email
                path.write_text(json.dumps(data))
            accounts.append(Account(label=label, email=email))
        except Exception as e:  # noqa: BLE001
            accounts.append(Account(label=label, email=f"(error: {e})"))
    return accounts


def get_credentials(label: str) -> Credentials:
    creds = _load_credentials(label)
    if not creds:
        raise RuntimeError(
            f"No credentials for account '{label}'. Run: gsa auth add {label}"
        )
    return creds


def default_label() -> Optional[str]:
    accs = list_accounts()
    return accs[0].label if accs else None
