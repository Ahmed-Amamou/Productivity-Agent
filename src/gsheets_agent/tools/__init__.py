from gsheets_agent.tools.sheets import SHEETS_TOOLS, dispatch_sheets_tool
from gsheets_agent.tools.gmail import GMAIL_TOOLS, dispatch_gmail_tool

ALL_TOOLS = SHEETS_TOOLS + GMAIL_TOOLS


def dispatch(name: str, arguments: dict) -> str:
    if name.startswith("sheets_") or name.startswith("drive_"):
        return dispatch_sheets_tool(name, arguments)
    if name.startswith("gmail_"):
        return dispatch_gmail_tool(name, arguments)
    raise ValueError(f"Unknown tool: {name}")
