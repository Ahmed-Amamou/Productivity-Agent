"""Pure-logic tests for gmail helpers (no Google API calls)."""
import base64

from gsheets_agent.tools.gmail import _decode_body, _extract_body


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def test_decode_body_roundtrip():
    assert _decode_body(_b64("hello world")) == "hello world"


def test_extract_body_top_level():
    payload = {"body": {"data": _b64("plain text body")}}
    assert _extract_body(payload) == "plain text body"


def test_extract_body_prefers_text_plain_over_html():
    payload = {
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("plain")}},
        ]
    }
    assert _extract_body(payload) == "plain"


def test_extract_body_falls_back_to_html():
    payload = {
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>only html</p>")}},
        ]
    }
    assert _extract_body(payload) == "<p>only html</p>"


def test_extract_body_recurses_into_multipart():
    payload = {
        "parts": [
            {"mimeType": "multipart/alternative", "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("nested plain")}},
            ]},
        ]
    }
    assert _extract_body(payload) == "nested plain"


def test_extract_body_empty_payload():
    assert _extract_body({}) == ""
    assert _extract_body(None) == ""
