import pytest

from gsheets_agent.config import token_path


def test_token_path_normalizes_label(tmp_credentials):
    p = token_path("WorK")
    assert p.name == "token-work.json"
    assert p.parent == tmp_credentials


def test_token_path_strips_unsafe_chars(tmp_credentials):
    assert token_path("my-account_2").name == "token-my-account_2.json"


def test_token_path_rejects_empty_label(tmp_credentials):
    with pytest.raises(ValueError):
        token_path("!!!")
