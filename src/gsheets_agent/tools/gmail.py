"""Gmail tool implementations exposed to the LLM, account-aware."""
from __future__ import annotations

import base64
import json
from email.message import EmailMessage
from functools import lru_cache
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gsheets_agent.auth import default_label, get_credentials


@lru_cache(maxsize=8)
def _gmail(label: str):
    return build("gmail", "v1", credentials=get_credentials(label), cache_discovery=False)


def _account(label: str | None) -> str:
    label = label or default_label()
    if not label:
        raise RuntimeError("No authorized accounts. Run: gsa auth add <label>")
    return label


def _decode_body(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """Walk MIME parts and return the best text body."""
    if not payload:
        return ""
    if payload.get("body", {}).get("data"):
        return _decode_body(payload["body"]["data"])
    parts = payload.get("parts") or []
    # Prefer text/plain, fall back to text/html
    for mime in ("text/plain", "text/html"):
        for p in parts:
            if p.get("mimeType") == mime and p.get("body", {}).get("data"):
                return _decode_body(p["body"]["data"])
    # Recurse into multipart
    for p in parts:
        if p.get("parts"):
            body = _extract_body(p)
            if body:
                return body
    return ""


# ---------- implementations ----------

def list_messages(
    query: str = "",
    max_results: int = 20,
    label_ids: list[str] | None = None,
    account: str | None = None,
) -> dict:
    label = _account(account)
    g = _gmail(label)
    res = g.users().messages().list(
        userId="me", q=query, maxResults=max_results, labelIds=label_ids or None,
    ).execute()
    msgs = res.get("messages", [])
    # Hydrate with subject/from for usability
    out = []
    for m in msgs:
        meta = g.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
        out.append({
            "id": m["id"],
            "threadId": meta.get("threadId"),
            "snippet": meta.get("snippet"),
            "subject": headers.get("Subject"),
            "from": headers.get("From"),
            "date": headers.get("Date"),
            "labelIds": meta.get("labelIds", []),
        })
    return {"account": label, "messages": out}


def get_message(message_id: str, account: str | None = None) -> dict:
    label = _account(account)
    g = _gmail(label)
    msg = g.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "account": label,
        "id": msg["id"],
        "threadId": msg.get("threadId"),
        "labelIds": msg.get("labelIds", []),
        "subject": headers.get("Subject"),
        "from": headers.get("From"),
        "to": headers.get("To"),
        "cc": headers.get("Cc"),
        "date": headers.get("Date"),
        "body": _extract_body(msg.get("payload", {})),
    }


def send_message(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    reply_to_message_id: str | None = None,
    account: str | None = None,
) -> dict:
    label = _account(account)
    g = _gmail(label)

    msg = EmailMessage()
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject
    msg.set_content(body)

    thread_id = None
    if reply_to_message_id:
        original = g.users().messages().get(
            userId="me", id=reply_to_message_id, format="metadata",
            metadataHeaders=["Message-ID", "References", "Subject"],
        ).execute()
        thread_id = original.get("threadId")
        headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
        if headers.get("Message-ID"):
            msg["In-Reply-To"] = headers["Message-ID"]
            msg["References"] = (headers.get("References", "") + " " + headers["Message-ID"]).strip()

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body_payload: dict[str, Any] = {"raw": raw}
    if thread_id:
        body_payload["threadId"] = thread_id

    sent = g.users().messages().send(userId="me", body=body_payload).execute()
    return {"account": label, "id": sent.get("id"), "threadId": sent.get("threadId")}


def create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    account: str | None = None,
) -> dict:
    label = _account(account)
    g = _gmail(label)

    msg = EmailMessage()
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject
    msg.set_content(body)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = g.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return {"account": label, "draft_id": draft.get("id"), "message_id": draft.get("message", {}).get("id")}


def list_labels(account: str | None = None) -> dict:
    label = _account(account)
    g = _gmail(label)
    res = g.users().labels().list(userId="me").execute()
    return {"account": label, "labels": res.get("labels", [])}


def create_label(name: str, account: str | None = None) -> dict:
    label = _account(account)
    g = _gmail(label)
    res = g.users().labels().create(
        userId="me",
        body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    return {"account": label, "label": res}


def modify_message_labels(
    message_id: str,
    add_label_ids: list[str] | None = None,
    remove_label_ids: list[str] | None = None,
    account: str | None = None,
) -> dict:
    label = _account(account)
    g = _gmail(label)
    res = g.users().messages().modify(
        userId="me", id=message_id,
        body={"addLabelIds": add_label_ids or [], "removeLabelIds": remove_label_ids or []},
    ).execute()
    return {"account": label, "id": res.get("id"), "labelIds": res.get("labelIds", [])}


def trash_message(message_id: str, account: str | None = None) -> dict:
    """Move to Trash (reversible). Permanent delete is not exposed."""
    label = _account(account)
    g = _gmail(label)
    res = g.users().messages().trash(userId="me", id=message_id).execute()
    return {"account": label, "id": res.get("id"), "labelIds": res.get("labelIds", [])}


# ---------- dispatcher + OpenAI tool schemas ----------

_DISPATCH = {
    "gmail_list_messages": list_messages,
    "gmail_get_message": get_message,
    "gmail_send": send_message,
    "gmail_create_draft": create_draft,
    "gmail_list_labels": list_labels,
    "gmail_create_label": create_label,
    "gmail_modify_labels": modify_message_labels,
    "gmail_trash_message": trash_message,
}


def dispatch_gmail_tool(name: str, arguments: dict) -> str:
    fn = _DISPATCH.get(name)
    if not fn:
        raise ValueError(f"Unknown gmail tool: {name}")
    try:
        result = fn(**arguments)
        return json.dumps(result, default=str)
    except HttpError as e:
        return json.dumps({"error": "google_api_error", "status": e.status_code, "details": str(e)})
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": type(e).__name__, "details": str(e)})


def _account_param() -> dict:
    return {
        "type": "string",
        "description": "Account label. Omit to use the default account.",
    }


GMAIL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "gmail_list_messages",
            "description": "Search/list messages. `query` uses Gmail search syntax (e.g. 'from:alice newer_than:7d is:unread').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "default": ""},
                    "max_results": {"type": "integer", "default": 20},
                    "label_ids": {"type": "array", "items": {"type": "string"}},
                    "account": _account_param(),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_get_message",
            "description": "Fetch full content (headers + body text) of a message by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "account": _account_param(),
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": "Send an email. Provide `reply_to_message_id` to thread the reply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "cc": {"type": "string"},
                    "bcc": {"type": "string"},
                    "reply_to_message_id": {"type": "string"},
                    "account": _account_param(),
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_create_draft",
            "description": "Create a Gmail draft (does not send).",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "cc": {"type": "string"},
                    "bcc": {"type": "string"},
                    "account": _account_param(),
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_list_labels",
            "description": "List Gmail labels with their ids.",
            "parameters": {"type": "object", "properties": {"account": _account_param()}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_create_label",
            "description": "Create a new Gmail label.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "account": _account_param()},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_modify_labels",
            "description": "Add and/or remove labels on a message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "add_label_ids": {"type": "array", "items": {"type": "string"}},
                    "remove_label_ids": {"type": "array", "items": {"type": "string"}},
                    "account": _account_param(),
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_trash_message",
            "description": "Move a message to Trash (reversible). Permanent delete is intentionally not exposed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "account": _account_param(),
                },
                "required": ["message_id"],
            },
        },
    },
]
