"""Google Sheets + Drive tool implementations exposed to the LLM."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gsheets_agent.auth import default_label, get_credentials


# ---------- service builders (cached per account) ----------

@lru_cache(maxsize=8)
def _sheets_service(label: str):
    return build("sheets", "v4", credentials=get_credentials(label), cache_discovery=False)


@lru_cache(maxsize=8)
def _drive_service(label: str):
    return build("drive", "v3", credentials=get_credentials(label), cache_discovery=False)


def _account(label: str | None) -> str:
    label = label or default_label()
    if not label:
        raise RuntimeError("No authorized accounts. Run: gsa auth add <label>")
    return label


_URL_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")


def _normalize_id(spreadsheet_id_or_url: str) -> str:
    m = _URL_RE.search(spreadsheet_id_or_url)
    return m.group(1) if m else spreadsheet_id_or_url


# ---------- implementations ----------

def list_spreadsheets(account: str | None = None, query: str | None = None, page_size: int = 25) -> dict:
    label = _account(account)
    drive = _drive_service(label)
    q = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    if query:
        q += f" and name contains '{query.replace(chr(39), '')}'"
    res = drive.files().list(
        q=q,
        pageSize=page_size,
        fields="files(id,name,modifiedTime,webViewLink,owners(emailAddress))",
        orderBy="modifiedTime desc",
    ).execute()
    return {"account": label, "files": res.get("files", [])}


def create_spreadsheet(title: str, account: str | None = None) -> dict:
    label = _account(account)
    sheets = _sheets_service(label)
    res = sheets.spreadsheets().create(
        body={"properties": {"title": title}},
        fields="spreadsheetId,spreadsheetUrl,properties.title",
    ).execute()
    return {"account": label, **res}


def get_spreadsheet(spreadsheet_id: str, account: str | None = None) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    sheets = _sheets_service(label)
    res = sheets.spreadsheets().get(
        spreadsheetId=sid,
        fields="spreadsheetId,spreadsheetUrl,properties.title,sheets(properties(sheetId,title,index,gridProperties))",
    ).execute()
    return {"account": label, **res}


def read_range(spreadsheet_id: str, range: str, account: str | None = None) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    sheets = _sheets_service(label)
    res = sheets.spreadsheets().values().get(spreadsheetId=sid, range=range).execute()
    return {"account": label, "range": res.get("range"), "values": res.get("values", [])}


def write_range(
    spreadsheet_id: str,
    range: str,
    values: list[list[Any]],
    account: str | None = None,
    value_input_option: str = "USER_ENTERED",
) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    sheets = _sheets_service(label)
    res = sheets.spreadsheets().values().update(
        spreadsheetId=sid,
        range=range,
        valueInputOption=value_input_option,
        body={"values": values},
    ).execute()
    return {"account": label, **res}


def append_rows(
    spreadsheet_id: str,
    range: str,
    values: list[list[Any]],
    account: str | None = None,
    value_input_option: str = "USER_ENTERED",
) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    sheets = _sheets_service(label)
    res = sheets.spreadsheets().values().append(
        spreadsheetId=sid,
        range=range,
        valueInputOption=value_input_option,
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()
    return {"account": label, **res}


def clear_range(spreadsheet_id: str, range: str, account: str | None = None) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    sheets = _sheets_service(label)
    res = sheets.spreadsheets().values().clear(spreadsheetId=sid, range=range, body={}).execute()
    return {"account": label, **res}


def add_sheet(spreadsheet_id: str, title: str, account: str | None = None) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    sheets = _sheets_service(label)
    res = sheets.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()
    return {"account": label, **res}


def _grid_range(meta: dict, sheet_title: str, a1: str) -> dict:
    """Convert a sheet title + A1 cell range into a GridRange object."""
    sheet_id = None
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == sheet_title:
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        raise ValueError(f"Sheet tab '{sheet_title}' not found")

    m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", a1.upper())
    if not m:
        raise ValueError(f"Range '{a1}' must be in A1:B2 form (no tab prefix)")

    def col_to_idx(col: str) -> int:
        n = 0
        for ch in col:
            n = n * 26 + (ord(ch) - 64)
        return n - 1

    return {
        "sheetId": sheet_id,
        "startRowIndex": int(m.group(2)) - 1,
        "endRowIndex": int(m.group(4)),
        "startColumnIndex": col_to_idx(m.group(1)),
        "endColumnIndex": col_to_idx(m.group(3)) + 1,
    }


def format_range(
    spreadsheet_id: str,
    sheet_title: str,
    range: str,
    bold: bool | None = None,
    italic: bool | None = None,
    background_color: dict | None = None,  # {"red":1,"green":1,"blue":1}
    text_color: dict | None = None,
    horizontal_alignment: str | None = None,  # LEFT/CENTER/RIGHT
    number_format: str | None = None,  # e.g. "#,##0.00", "0.00%", "yyyy-mm-dd"
    account: str | None = None,
) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    sheets = _sheets_service(label)
    meta = sheets.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
    grid = _grid_range(meta, sheet_title, range)

    text_format: dict = {}
    if bold is not None:
        text_format["bold"] = bold
    if italic is not None:
        text_format["italic"] = italic
    if text_color is not None:
        text_format["foregroundColor"] = text_color

    cell_format: dict = {}
    if text_format:
        cell_format["textFormat"] = text_format
    if background_color is not None:
        cell_format["backgroundColor"] = background_color
    if horizontal_alignment is not None:
        cell_format["horizontalAlignment"] = horizontal_alignment
    if number_format is not None:
        cell_format["numberFormat"] = {"type": "NUMBER", "pattern": number_format}

    fields = []
    if "textFormat" in cell_format:
        fields.append("userEnteredFormat.textFormat")
    if "backgroundColor" in cell_format:
        fields.append("userEnteredFormat.backgroundColor")
    if "horizontalAlignment" in cell_format:
        fields.append("userEnteredFormat.horizontalAlignment")
    if "numberFormat" in cell_format:
        fields.append("userEnteredFormat.numberFormat")
    if not fields:
        return {"account": label, "ok": True, "note": "no format changes specified"}

    req = {
        "repeatCell": {
            "range": grid,
            "cell": {"userEnteredFormat": cell_format},
            "fields": ",".join(fields),
        }
    }
    res = sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [req]}).execute()
    return {"account": label, **res}


def share_spreadsheet(
    spreadsheet_id: str,
    email: str,
    role: str = "writer",  # reader | commenter | writer
    notify: bool = False,
    account: str | None = None,
) -> dict:
    label = _account(account)
    sid = _normalize_id(spreadsheet_id)
    drive = _drive_service(label)
    perm = drive.permissions().create(
        fileId=sid,
        body={"type": "user", "role": role, "emailAddress": email},
        sendNotificationEmail=notify,
        fields="id,role,emailAddress",
    ).execute()
    return {"account": label, "permission": perm}


# ---------- dispatcher + OpenAI tool schemas ----------

_DISPATCH = {
    "drive_list_spreadsheets": list_spreadsheets,
    "sheets_create": create_spreadsheet,
    "sheets_get": get_spreadsheet,
    "sheets_read_range": read_range,
    "sheets_write_range": write_range,
    "sheets_append_rows": append_rows,
    "sheets_clear_range": clear_range,
    "sheets_add_sheet": add_sheet,
    "sheets_format_range": format_range,
    "sheets_share": share_spreadsheet,
}


def dispatch_sheets_tool(name: str, arguments: dict) -> str:
    fn = _DISPATCH.get(name)
    if not fn:
        raise ValueError(f"Unknown sheets tool: {name}")
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
        "description": "Account label (e.g. 'work', 'personal'). Omit to use the default account.",
    }


SHEETS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "drive_list_spreadsheets",
            "description": "List the user's Google Sheets files. Useful for discovering a spreadsheet by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": _account_param(),
                    "query": {"type": "string", "description": "Optional name substring filter."},
                    "page_size": {"type": "integer", "default": 25},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_create",
            "description": "Create a new Google Sheets spreadsheet. Returns its id and URL.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "account": _account_param()},
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_get",
            "description": "Get spreadsheet metadata: title, URL, list of tab/sheet names with their grid sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string", "description": "Spreadsheet id or full URL."},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_read_range",
            "description": "Read a range. Range uses A1 notation including tab name, e.g. 'Sales!A1:D100'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string"},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id", "range"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_write_range",
            "description": "Overwrite values in a range. Pass a 2D array. Formulas (starting with '=') are evaluated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string", "description": "A1 notation, e.g. 'Sheet1!A1'."},
                    "values": {
                        "type": "array",
                        "items": {"type": "array", "items": {}},
                        "description": "2D array of cell values.",
                    },
                    "value_input_option": {"type": "string", "enum": ["RAW", "USER_ENTERED"], "default": "USER_ENTERED"},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id", "range", "values"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_append_rows",
            "description": "Append rows after the last data row in the given range/table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string", "description": "Usually a tab name like 'Sheet1' or 'Sheet1!A:Z'."},
                    "values": {"type": "array", "items": {"type": "array", "items": {}}},
                    "value_input_option": {"type": "string", "enum": ["RAW", "USER_ENTERED"], "default": "USER_ENTERED"},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id", "range", "values"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_clear_range",
            "description": "Clear values in a range (keeps formatting).",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "range": {"type": "string"},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id", "range"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_add_sheet",
            "description": "Add a new tab/sheet to a spreadsheet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "title": {"type": "string"},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_format_range",
            "description": "Format a cell range: bold, italic, colors, alignment, number format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "sheet_title": {"type": "string", "description": "Tab name."},
                    "range": {"type": "string", "description": "A1 cell range without tab prefix, e.g. 'A1:D1'."},
                    "bold": {"type": "boolean"},
                    "italic": {"type": "boolean"},
                    "background_color": {
                        "type": "object",
                        "properties": {
                            "red": {"type": "number"}, "green": {"type": "number"}, "blue": {"type": "number"},
                        },
                        "description": "RGB 0..1.",
                    },
                    "text_color": {
                        "type": "object",
                        "properties": {
                            "red": {"type": "number"}, "green": {"type": "number"}, "blue": {"type": "number"},
                        },
                    },
                    "horizontal_alignment": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT"]},
                    "number_format": {"type": "string", "description": "Pattern like '#,##0.00', '0.00%', 'yyyy-mm-dd'."},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id", "sheet_title", "range"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sheets_share",
            "description": "Share a spreadsheet with a user by email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string", "enum": ["reader", "commenter", "writer"], "default": "writer"},
                    "notify": {"type": "boolean", "default": False},
                    "account": _account_param(),
                },
                "required": ["spreadsheet_id", "email"],
            },
        },
    },
]
