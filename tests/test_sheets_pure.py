"""Pure-logic tests for sheets helpers (no Google API calls)."""
import pytest

from gsheets_agent.tools.sheets import _grid_range, _normalize_id


def test_normalize_id_extracts_from_url():
    url = "https://docs.google.com/spreadsheets/d/1AbC_def-GHIjk_lmnop/edit#gid=0"
    assert _normalize_id(url) == "1AbC_def-GHIjk_lmnop"


def test_normalize_id_passes_through_bare_id():
    assert _normalize_id("1AbC_def-GHIjk") == "1AbC_def-GHIjk"


def test_grid_range_basic():
    meta = {"sheets": [{"properties": {"sheetId": 42, "title": "Sales"}}]}
    g = _grid_range(meta, "Sales", "A1:B2")
    assert g == {
        "sheetId": 42,
        "startRowIndex": 0,
        "endRowIndex": 2,
        "startColumnIndex": 0,
        "endColumnIndex": 2,
    }


def test_grid_range_multi_letter_columns():
    meta = {"sheets": [{"properties": {"sheetId": 1, "title": "S"}}]}
    g = _grid_range(meta, "S", "A1:AA10")
    assert g["startColumnIndex"] == 0
    assert g["endColumnIndex"] == 27  # AA = 27
    assert g["endRowIndex"] == 10


def test_grid_range_unknown_tab_raises():
    meta = {"sheets": [{"properties": {"sheetId": 1, "title": "S"}}]}
    with pytest.raises(ValueError, match="not found"):
        _grid_range(meta, "MissingTab", "A1:B2")


def test_grid_range_invalid_a1_raises():
    meta = {"sheets": [{"properties": {"sheetId": 1, "title": "S"}}]}
    with pytest.raises(ValueError, match="A1:B2 form"):
        _grid_range(meta, "S", "Sheet1!A1:B2")  # tab prefix not allowed
