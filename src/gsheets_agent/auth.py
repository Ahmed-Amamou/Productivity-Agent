"""Google OAuth - per-account token storage with strict perms.

Uses the InstalledAppFlow loopback flow (Google's recommended approach for desktop
clients): a one-shot HTTP server on 127.0.0.1 receives the auth code; the refresh
token is then stored on disk at 0600.
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from gsheets_agent.config import (
    CREDENTIALS_DIR,
    OAUTH_CLIENT_FILE,
    SCOPES,
    token_path,
)

# Heavy google-* imports are deferred into the functions that need them.
# `gsa accounts` only triggers the lightweight `google.oauth2.credentials` chain.


def _is_headless() -> bool:
    """True when there's no usable browser (WSL, SSH session, no DISPLAY)."""
    if "microsoft" in platform.uname().release.lower():
        return True  # WSL
    if not os.environ.get("DISPLAY") and platform.system() == "Linux":
        return True
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return True
    return False


@dataclass
class Account:
    label: str
    email: str

    def __str__(self) -> str:
        return f"{self.label} <{self.email}>"


def _save_credentials(label: str, creds) -> None:
    path = token_path(label)
    path.write_text(creds.to_json())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows / WSL on NTFS: best-effort.


def _load_credentials(label: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = token_path(label)
    if not path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(label, creds)
    return creds


def _email_for(creds) -> str:
    from googleapiclient.discovery import build  # heavy import, deferred

    svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
    info = svc.userinfo().get().execute()
    return info.get("email", "unknown")


def _add_account_manual(label: str) -> Account:
    from google_auth_oauthlib.flow import Flow  # heavy import, deferred
    """Headless OAuth: print URL, user pastes back the redirect URL from their browser.

    Doesn't depend on WSL/Windows localhost forwarding. The user authorizes in
    their host browser; the browser is redirected to http://localhost/?code=...
    which fails to load — the user copies that full URL from the address bar
    and pastes it here.
    """
    flow = Flow.from_client_secrets_file(str(OAUTH_CLIENT_FILE), SCOPES)
    flow.redirect_uri = "http://localhost"  # must be allowed for Desktop OAuth clients

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    print()
    print("=" * 78)
    print("Open this URL in a browser on your host machine and sign in:")
    print()
    print(f"  {auth_url}")
    print()
    print("After approving, the browser will try to load 'http://localhost/?code=...'")
    print("and show 'site can't be reached'. That is expected. Copy the FULL URL")
    print("from the browser's address bar and paste it below.")
    print("=" * 78)
    print()

    pasted = input("Paste the redirect URL here: ").strip()
    if not pasted:
        raise RuntimeError("No URL provided.")
    # Desktop OAuth uses http://localhost; oauthlib otherwise refuses non-HTTPS.
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    flow.fetch_token(authorization_response=pasted)
    creds = flow.credentials
    _save_credentials(label, creds)
    email = _email_for(creds)
    return Account(label=label, email=email)


def add_account(label: str) -> Account:
    """Authorize a Google account. Uses loopback when possible, manual paste in WSL/SSH."""
    if not OAUTH_CLIENT_FILE.exists():
        raise FileNotFoundError(
            f"OAuth client file not found at {OAUTH_CLIENT_FILE}. "
            "Download it from Google Cloud Console (Desktop app credentials)."
        )

    if _is_headless():
        return _add_account_manual(label)

    from google_auth_oauthlib.flow import InstalledAppFlow  # heavy import, deferred

    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CLIENT_FILE), SCOPES)
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


def get_credentials(label: str):
    creds = _load_credentials(label)
    if not creds:
        raise RuntimeError(
            f"No credentials for account '{label}'. Run: gsa auth add {label}"
        )
    return creds


def default_label() -> Optional[str]:
    accs = list_accounts()
    return accs[0].label if accs else None
