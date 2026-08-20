from fantasy_rng_screenshot_ocr import _tier_from_line, _token_from_button_text


def test_token_mapping_handles_client_wording():
    assert _token_from_button_text("Reroll quality for one random red emblem")[0] == "quality_random_one_red"
    assert _token_from_button_text("Reroll stat for the last green emblem")[0] == "stat_last_green"
    assert _token_from_button_text("Randomly increase two qualities and reduce one")[0] == "quality_shift_plus2_minus1"


def test_token_mapping_returns_empty_for_unknown_text():
    assert _token_from_button_text("unreadable button")[0] == ""


def test_tier_mapping_handles_roman_and_ocr_variants():
    assert _tier_from_line("TIER IV") == "tier_iv"
    assert _tier_from_line("tier 111") == "tier_iii"
    assert _tier_from_line("t1er 1v") == "tier_iv"
