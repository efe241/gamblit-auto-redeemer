"""
Unit tests for CodeParser.
"""
import pytest
from app.parser import CodeParser


def test_extract_code_with_tag():
    msg = "🎁 New Code: ABC123XYZ"
    code = CodeParser.extract_raw_code(msg)
    assert code == "ABC123XYZ"


def test_extract_code_in_backticks():
    msg = "Quick! Use code `PROMO2026` before it expires!"
    code = CodeParser.extract_raw_code(msg)
    assert code == "PROMO2026"


def test_extract_code_in_multiline_block():
    msg = """
    🚨 NEW DROP 🚨
    ```
    NIGHTLY_DROP_99
    ```
    Enjoy!
    """
    code = CodeParser.extract_raw_code(msg)
    assert code == "NIGHTLY_DROP_99"


def test_extract_code_with_emoji_and_mentions():
    msg = "<@&123456789> <:party:987654321> Promo Code: LUCKY777 https://gamblit.net"
    code = CodeParser.extract_raw_code(msg)
    assert code == "LUCKY777"


def test_standalone_code_line():
    msg = "XYZ999ABC"
    code = CodeParser.extract_raw_code(msg)
    assert code == "XYZ999ABC"


def test_ignore_normal_chat():
    msg = "Hello everyone, when is the next drop coming out?"
    code = CodeParser.extract_raw_code(msg)
    assert code is None


def test_ignore_common_words():
    msg = "gamblit announcement rules update"
    code = CodeParser.extract_raw_code(msg)
    assert code is None


def test_parse_message_returns_metadata():
    parsed = CodeParser.parse_message(
        content="Code: TEST1234",
        message_id=1001,
        channel_id=2002,
        guild_id=3003,
        author_id=4004,
    )
    assert parsed is not None
    assert parsed.code == "TEST1234"
    assert parsed.message_id == 1001
    assert parsed.channel_id == 2002
    assert parsed.parse_latency_ms >= 0.0


def test_multi_level_cascading_codes():
    msg = """
    🚨 MEGA DROP 🚨
    LEVEL 150+ Use the code LEVEL150CODE to claim 500 DL
    LEVEL 100+ Use the code LEVEL100CODE to claim 250 DL
    LEVEL 50+  Use the code LEVEL50CODE  to claim 100 DL
    LEVEL 10+  Use the code LEVEL10CODE   to claim 20 DL
    """
    # User is level 120 -> should get LEVEL100CODE, LEVEL50CODE, LEVEL10CODE in that descending order!
    codes = CodeParser.extract_eligible_codes(msg, user_level=120)
    assert codes == ["LEVEL100CODE", "LEVEL50CODE", "LEVEL10CODE"]

    # User is level 200 -> gets all 4 codes descending
    all_codes = CodeParser.extract_eligible_codes(msg, user_level=200)
    assert all_codes == ["LEVEL150CODE", "LEVEL100CODE", "LEVEL50CODE", "LEVEL10CODE"]

    # User is level 5 -> not eligible for anything
    no_codes = CodeParser.extract_eligible_codes(msg, user_level=5)
    assert no_codes == []

