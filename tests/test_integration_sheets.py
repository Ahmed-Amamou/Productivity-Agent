"""Integration tests for Google Sheets tools — hits the REAL API.

Run with:  pytest tests/test_integration_sheets.py -v -s

These tests create a temporary spreadsheet, exercise all CRUD operations,
then trash it at the end. You (the human) can verify results live by
opening the printed URL during the test run.

Requires: a valid authorized account (run `gsa auth add work` first).
"""
from __future__ import annotations

import time

import pytest

from gsheets_agent.tools.sheets import (
    add_sheet,
    append_rows,
    clear_range,
    create_spreadsheet,
    format_range,
    get_spreadsheet,
    list_spreadsheets,
    read_range,
    trash_file,
    write_range,
)

ACCOUNT = "work"
TEST_SHEET_TITLE = "__integration_test_sheet__"


@pytest.fixture(scope="module")
def spreadsheet():
    """Create a test spreadsheet for the module, trash it when done."""
    result = create_spreadsheet(title=TEST_SHEET_TITLE, account=ACCOUNT)
    print(f"\n>>> Created test spreadsheet: {result['spreadsheetUrl']}")
    yield result
    # Cleanup
    trash_file(result["spreadsheetId"], account=ACCOUNT)
    print(f"\n>>> Trashed test spreadsheet: {result['spreadsheetId']}")


# ---------- Discovery ----------

class TestDiscovery:
    def test_list_spreadsheets_returns_files(self):
        """Can we list spreadsheets at all?"""
        result = list_spreadsheets(account=ACCOUNT, page_size=5)
        assert result["account"] == ACCOUNT
        assert isinstance(result["files"], list)
        print(f"  Found {len(result['files'])} spreadsheets")

    def test_list_spreadsheets_with_query(self, spreadsheet):
        """Can we search by name?"""
        # Give API a moment to index
        time.sleep(2)
        result = list_spreadsheets(account=ACCOUNT, query=TEST_SHEET_TITLE)
        assert any(f["id"] == spreadsheet["spreadsheetId"] for f in result["files"]), (
            f"Test sheet not found in search results: {result['files']}"
        )
        print(f"  Found test sheet via search")


# ---------- Create & Metadata ----------

class TestCreateAndMetadata:
    def test_create_returns_id_and_url(self, spreadsheet):
        """Does create return expected fields?"""
        assert "spreadsheetId" in spreadsheet
        assert "spreadsheetUrl" in spreadsheet
        assert spreadsheet["properties"]["title"] == TEST_SHEET_TITLE

    def test_get_spreadsheet_metadata(self, spreadsheet):
        """Can we fetch metadata for our sheet?"""
        result = get_spreadsheet(spreadsheet["spreadsheetId"], account=ACCOUNT)
        assert result["properties"]["title"] == TEST_SHEET_TITLE
        assert len(result["sheets"]) >= 1
        default_tab = result["sheets"][0]["properties"]["title"]
        print(f"  Default tab: '{default_tab}'")
        assert default_tab == "Sheet1"

    def test_get_spreadsheet_by_url(self, spreadsheet):
        """Can we pass a full URL instead of bare ID?"""
        url = spreadsheet["spreadsheetUrl"]
        result = get_spreadsheet(url, account=ACCOUNT)
        assert result["spreadsheetId"] == spreadsheet["spreadsheetId"]


# ---------- Write & Read ----------

class TestWriteAndRead:
    def test_write_then_read(self, spreadsheet):
        """Write data and read it back."""
        sid = spreadsheet["spreadsheetId"]
        data = [
            ["Name", "Age", "City"],
            ["Alice", "30", "NYC"],
            ["Bob", "25", "LA"],
            ["Charlie", "35", "Chicago"],
        ]
        write_result = write_range(sid, "Sheet1!A1:C4", data, account=ACCOUNT)
        assert write_result["updatedCells"] == 12
        print(f"  Wrote {write_result['updatedCells']} cells")

        read_result = read_range(sid, "Sheet1!A1:C4", account=ACCOUNT)
        assert read_result["values"] == data
        print(f"  Read back matches: {len(read_result['values'])} rows")

    def test_write_formulas(self, spreadsheet):
        """Formulas should be evaluated."""
        sid = spreadsheet["spreadsheetId"]
        write_range(sid, "Sheet1!E1:E3", [["=1+1"], ["=2*3"], ["=SUM(E1:E2)"]], account=ACCOUNT)

        read_result = read_range(sid, "Sheet1!E1:E3", account=ACCOUNT)
        # API returns computed values as strings
        assert read_result["values"] == [["2"], ["6"], ["8"]]
        print(f"  Formulas evaluated correctly: {read_result['values']}")

    def test_append_rows(self, spreadsheet):
        """Append adds rows after existing data."""
        sid = spreadsheet["spreadsheetId"]
        new_rows = [["Dave", "28", "Seattle"], ["Eve", "32", "Boston"]]
        result = append_rows(sid, "Sheet1", new_rows, account=ACCOUNT)
        assert "updates" in result
        print(f"  Appended {result['updates']['updatedRows']} rows")

        # Verify they appear after existing data
        all_data = read_range(sid, "Sheet1!A1:C10", account=ACCOUNT)
        assert len(all_data["values"]) == 6  # 4 original + 2 appended
        assert all_data["values"][4] == ["Dave", "28", "Seattle"]
        assert all_data["values"][5] == ["Eve", "32", "Boston"]

    def test_clear_range(self, spreadsheet):
        """Clear removes values but sheet still exists."""
        sid = spreadsheet["spreadsheetId"]
        clear_range(sid, "Sheet1!E1:E3", account=ACCOUNT)
        read_result = read_range(sid, "Sheet1!E1:E3", account=ACCOUNT)
        # Empty range returns no values
        assert read_result["values"] == []
        print("  Cleared formula column successfully")


# ---------- Tabs ----------

class TestTabs:
    def test_add_sheet_tab(self, spreadsheet):
        """Can we add a new tab?"""
        sid = spreadsheet["spreadsheetId"]
        result = add_sheet(sid, "DataTab", account=ACCOUNT)
        assert "replies" in result
        new_sheet_props = result["replies"][0]["addSheet"]["properties"]
        assert new_sheet_props["title"] == "DataTab"
        print(f"  Added tab 'DataTab' with sheetId={new_sheet_props['sheetId']}")

    def test_write_to_new_tab(self, spreadsheet):
        """Write to the newly created tab."""
        sid = spreadsheet["spreadsheetId"]
        data = [["Product", "Price"], ["Widget", "9.99"], ["Gadget", "14.50"]]
        write_range(sid, "DataTab!A1:B3", data, account=ACCOUNT)

        read_result = read_range(sid, "DataTab!A1:B3", account=ACCOUNT)
        # USER_ENTERED mode parses numbers and may trim trailing zeros (14.50 -> 14.5)
        assert read_result["values"][0] == ["Product", "Price"]
        assert read_result["values"][1] == ["Widget", "9.99"]
        assert float(read_result["values"][2][1]) == 14.5
        print(f"  Wrote and read from 'DataTab' successfully")


# ---------- Formatting ----------

class TestFormatting:
    def test_bold_header(self, spreadsheet):
        """Apply bold formatting to header row."""
        sid = spreadsheet["spreadsheetId"]
        result = format_range(
            sid, "Sheet1", "A1:C1", bold=True, account=ACCOUNT
        )
        # batchUpdate returns replies
        assert "replies" in result
        print("  Applied bold to A1:C1")

    def test_background_color(self, spreadsheet):
        """Apply background color."""
        sid = spreadsheet["spreadsheetId"]
        result = format_range(
            sid, "Sheet1", "A1:C1",
            background_color={"red": 0.2, "green": 0.6, "blue": 0.9},
            account=ACCOUNT,
        )
        assert "replies" in result
        print("  Applied background color to A1:C1")

    def test_number_format(self, spreadsheet):
        """Apply number format to DataTab prices."""
        sid = spreadsheet["spreadsheetId"]
        result = format_range(
            sid, "DataTab", "B2:B3",
            number_format="$#,##0.00",
            account=ACCOUNT,
        )
        assert "replies" in result
        print("  Applied currency format to DataTab!B2:B3")

    def test_format_no_changes(self, spreadsheet):
        """Calling format with no format options returns gracefully."""
        sid = spreadsheet["spreadsheetId"]
        result = format_range(sid, "Sheet1", "A1:A1", account=ACCOUNT)
        assert result["note"] == "no format changes specified"


# ---------- Edge Cases ----------

class TestEdgeCases:
    def test_read_empty_range(self, spreadsheet):
        """Reading a range with no data returns empty values."""
        sid = spreadsheet["spreadsheetId"]
        result = read_range(sid, "Sheet1!Z1:Z10", account=ACCOUNT)
        assert result["values"] == []

    def test_write_single_cell(self, spreadsheet):
        """Write a single value."""
        sid = spreadsheet["spreadsheetId"]
        write_range(sid, "Sheet1!G1", [["hello"]], account=ACCOUNT)
        result = read_range(sid, "Sheet1!G1", account=ACCOUNT)
        assert result["values"] == [["hello"]]

    def test_write_raw_mode(self, spreadsheet):
        """RAW mode should not evaluate formulas."""
        sid = spreadsheet["spreadsheetId"]
        write_range(
            sid, "Sheet1!H1", [["=1+1"]],
            value_input_option="RAW", account=ACCOUNT,
        )
        result = read_range(sid, "Sheet1!H1", account=ACCOUNT)
        # RAW keeps the formula as literal text
        assert result["values"] == [["=1+1"]]
        print("  RAW mode preserved formula as text")


# ---------- Dispatch integration ----------

class TestDispatch:
    """Test the dispatch layer with real API calls."""

    def test_dispatch_sheets_get(self, spreadsheet):
        """dispatch_sheets_tool routes correctly to real API."""
        from gsheets_agent.tools.sheets import dispatch_sheets_tool
        import json

        result = json.loads(dispatch_sheets_tool("sheets_get", {
            "spreadsheet_id": spreadsheet["spreadsheetId"],
            "account": ACCOUNT,
        }))
        assert result["properties"]["title"] == TEST_SHEET_TITLE

    def test_dispatch_unknown_tool(self):
        """Unknown tool name returns error."""
        from gsheets_agent.tools.sheets import dispatch_sheets_tool
        try:
            dispatch_sheets_tool("nonexistent_tool", {})
            assert False, "Should have raised"
        except ValueError as e:
            assert "Unknown" in str(e)
