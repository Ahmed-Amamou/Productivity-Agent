# gsheets-agent

CLI AI agent that interacts with Google Sheets and Gmail across multiple Google accounts. Uses OpenAI's GPT-5 family with a tiny router model that picks the right tier per turn.

## Setup

### 1. Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
# put your OPENAI_API_KEY in .env
```

### 2. Get a Google OAuth client (one-time)
1. Go to https://console.cloud.google.com/ → create or pick a project.
2. APIs & Services → Library → enable: **Google Sheets API**, **Google Drive API**, **Gmail API**.
3. APIs & Services → OAuth consent screen → External → add yourself as a test user.
4. APIs & Services → Credentials → Create Credentials → **OAuth client ID** → **Desktop app**.
5. Download the JSON and save as `./credentials/oauth_client.json`.

### 3. Authorize your accounts
```bash
gsa auth add work        # opens browser; sign in with account #1
gsa auth add personal    # opens browser; sign in with account #2
gsa accounts             # list authorized accounts
```

Tokens are stored at `./credentials/token-<label>.json` with `0600` permissions. Delete a token file (or run `gsa auth remove <label>`) to revoke locally.

### 4. Run the agent
```bash
gsa chat                          # interactive REPL
gsa ask "summarize tab Sales in https://docs.google.com/spreadsheets/d/...."
```

## Models
- `ROUTER_MODEL` (default `gpt-5-nano`) decides each turn whether the work is "light" or "complex".
- `LIGHT_MODEL` (default `gpt-5-mini`) handles direct reads/writes/lookups.
- `COMPLEX_MODEL` (default `gpt-5`) handles multi-step reasoning, transformations, planning.

Override any of these in `.env`. Set `FORCE_TIER=complex` to bypass the router.

## Capabilities
**Sheets** (via Sheets + Drive APIs): list, create, get metadata, read/write/append/clear ranges, format cells, add tabs, share.

**Gmail** (per account): list/search messages, get message content, send, create drafts, list/create labels, modify labels on messages.

The agent is account-aware — when you ask it to email someone "from my work account", it routes the call through that account's credentials.
