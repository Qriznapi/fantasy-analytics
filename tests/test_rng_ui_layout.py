from pathlib import Path


UI_SOURCE = (Path(__file__).resolve().parents[1] / "app" / "rng_human_vs_model.py").read_text(encoding="utf-8")


def test_hover_preview_uses_fixed_five_slot_grid_per_role():
    """Long stat, trait, or token labels must never move another emblem."""
    assert "grid-template-rows:repeat(5,74px)" in UI_SOURCE
    assert "height:74px;overflow:hidden" in UI_SOURCE
    assert "grid-template-rows:13px 26px 19px" in UI_SOURCE
    assert "class='role-slots'" in UI_SOURCE
    assert "grid-auto-rows:76px" in UI_SOURCE
    assert "height:76px;overflow:hidden" in UI_SOURCE
