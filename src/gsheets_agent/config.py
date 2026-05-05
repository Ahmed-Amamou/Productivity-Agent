import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
CREDENTIALS_DIR.mkdir(exist_ok=True)

OAUTH_CLIENT_FILE = Path(
    os.environ.get("GOOGLE_OAUTH_CLIENT_FILE", CREDENTIALS_DIR / "oauth_client.json")
)

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
COMPLEX_MODEL = os.environ.get("COMPLEX_MODEL", "gpt-5")
LIGHT_MODEL = os.environ.get("LIGHT_MODEL", "gpt-5-mini")
ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "gpt-5-nano")
FORCE_TIER = os.environ.get("FORCE_TIER")  # "complex" | "light" | None

# Google API scopes - request only what we need.
# Sheets: full read/write. Drive: file-level (only files we create or open).
# Gmail: read, send, modify (labels). NOT including https://mail.google.com/ which allows permanent delete.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def token_path(label: str) -> Path:
    safe = "".join(c for c in label if c.isalnum() or c in "-_").lower()
    if not safe:
        raise ValueError("account label must contain alphanumerics")
    return CREDENTIALS_DIR / f"token-{safe}.json"
