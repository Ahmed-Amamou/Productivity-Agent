"""Typer CLI entrypoint."""
from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from gsheets_agent import auth as auth_mod
from gsheets_agent.config import CREDENTIALS_DIR, OPENAI_API_KEY

# NOTE: heavy imports (openai, googleapiclient, prompt_toolkit) are deferred to
# inside command bodies so light commands like `gsa accounts` start fast.

app = typer.Typer(no_args_is_help=True, add_completion=False, help="CLI AI agent for Google Sheets + Gmail.")
auth_app = typer.Typer(no_args_is_help=True, help="Manage Google account authorizations.")
app.add_typer(auth_app, name="auth")

console = Console()


def _require_openai_key() -> None:
    if not OPENAI_API_KEY:
        console.print("[red]OPENAI_API_KEY is not set. Add it to .env or your environment.[/red]")
        raise typer.Exit(1)


# ---------- auth subcommands ----------

@auth_app.command("add")
def auth_add(label: str = typer.Argument(..., help="A short label, e.g. 'work' or 'personal'.")):
    """Authorize a Google account and save its token under ./credentials/token-<label>.json."""
    try:
        acc = auth_mod.add_account(label)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Authorized:[/green] {acc}")


@auth_app.command("remove")
def auth_remove(label: str):
    """Forget a previously-authorized account (deletes the local token file)."""
    if auth_mod.remove_account(label):
        console.print(f"[yellow]Removed[/yellow] account '{label}'.")
    else:
        console.print(f"[red]No account labeled '{label}'.[/red]")
        raise typer.Exit(1)


@auth_app.command("list")
def auth_list():
    """List authorized accounts."""
    _print_accounts()


@app.command("accounts")
def accounts():
    """Alias for `auth list`."""
    _print_accounts()


def _print_accounts() -> None:
    accs = auth_mod.list_accounts()
    if not accs:
        console.print(f"[yellow]No accounts yet.[/yellow] Drop an OAuth client JSON in {CREDENTIALS_DIR}/oauth_client.json then run: gsa auth add <label>")
        return
    table = Table(title="Authorized accounts")
    table.add_column("Label", style="cyan")
    table.add_column("Email", style="green")
    for a in accs:
        table.add_row(a.label, a.email)
    console.print(table)


# ---------- chat / ask ----------

def _print_event(event: str, payload: dict) -> None:
    if event == "router":
        console.print(f"[dim]router → {payload['tier']} ({payload['model']}): {payload['reason']}[/dim]")
    elif event == "tool_call":
        args_preview = json.dumps(payload["args"])
        if len(args_preview) > 200:
            args_preview = args_preview[:200] + "…"
        console.print(f"[blue]→ {payload['name']}[/blue] [dim]{args_preview}[/dim]")
    elif event == "tool_result":
        result = payload["result"]
        preview = result if len(result) <= 300 else result[:300] + "…"
        console.print(f"[dim]  ← {preview}[/dim]")


@app.command("ask")
def ask(prompt: str = typer.Argument(..., help="One-shot question for the agent.")):
    """Send a single prompt and print the response."""
    _require_openai_key()
    from gsheets_agent.agent import AgentSession  # heavy: pulls openai + googleapi
    session = AgentSession(on_event=_print_event)
    reply = session.send(prompt)
    console.print()
    console.print(reply)


@app.command("chat")
def chat():
    """Start an interactive REPL with persistent history."""
    _require_openai_key()
    if not auth_mod.list_accounts():
        console.print("[yellow]No authorized Google accounts. Add one with: gsa auth add <label>[/yellow]")

    from gsheets_agent.agent import AgentSession
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    session = AgentSession(on_event=_print_event)
    history_file = CREDENTIALS_DIR / ".chat_history"
    pt = PromptSession(history=FileHistory(str(history_file)))

    console.print("[bold]gsheets-agent[/bold]  (type 'exit' or Ctrl-D to quit)")
    while True:
        try:
            user = pt.prompt("you ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not user:
            continue
        if user.lower() in ("exit", "quit", ":q"):
            return
        try:
            reply = session.send(user)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]error:[/red] {e}")
            continue
        console.print()
        console.print(f"[bold green]agent ▸[/bold green] {reply}\n")


if __name__ == "__main__":
    app()
