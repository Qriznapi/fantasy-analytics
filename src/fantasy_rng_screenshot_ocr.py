"""Local, template-aware OCR for Dota Fantasy banner screenshots.

The parser is intentionally conservative: incomplete role cards are returned
as reviewable suggestions and are never applied automatically by this module.
"""

from __future__ import annotations

import io
import os
import re
from difflib import SequenceMatcher
from typing import Any

from PIL import Image, ImageEnhance, ImageOps


STATS = {
    "kills": "kills", "deaths": "deaths", "creep score": "creep_score", "gpm": "gpm",
    "madstone collected": "madstone_collected", "madstone": "madstone_collected", "tower kills": "tower_kills", "wards placed": "wards_placed",
    "camps stacked": "camps_stacked", "runes grabbed": "runes_grabbed", "runes": "runes_grabbed", "watchers taken": "watchers_taken",
    "smokes used": "smokes_used", "lotuses gained": "lotus", "lotus": "lotus", "voruses": "lotus", "voruses camer": "lotus", "roshan kills": "roshan_kills",
    "teamfight": "teamfight_participation", "stuns": "stuns", "tormentor kills": "tormentor_kills",
    "courier kills": "courier_kills", "first blood": "first_blood", "tormentor": "tormentor_kills", "obs wards": "wards_placed", "obs": "wards_placed", "teeamficht": "teamfight_participation", "teamficht": "teamfight_participation",
}
TRAITS = {"fractal", "benevolent", "vampiric", "unique", "friendly"}
TIERS = {"i": "tier_i", "ii": "tier_ii", "iii": "tier_iii", "iv": "tier_iv", "v": "tier_v"}
TIER_FROM_BONUS = {"10": "tier_i", "30": "tier_ii", "60": "tier_iii", "100": "tier_iv", "150": "tier_v"}
# Two common client compositions: with a persistent left navigation panel and
# a full-width/cropped capture with the three role panels filling the screen.
ROLE_LAYOUTS = (
    ({"core": (.355, .475), "mid": (.605, .715), "support": (.850, .975)}, .23, .67),
    # Full-width replay/cropped layout: emblems sit on the right edge of each
    # wide role panel and begin much higher in the screenshot.
    ({"core": (.175, .325), "mid": (.500, .645), "support": (.835, .995)}, .035, .52),
)
ROLE_NAMES = ("core", "mid", "support")
# Client scale, browser zoom, and cropped captures can shift a card by a few
# percent. Try a small number of wider cards, then retain the strongest OCR
# result for each role independently.
ROLE_CROP_VARIANTS = (
    (0.0, 0.0, 0.0, 0.0),
    (-.012, .012, -.015, .025),
    (-.025, .025, -.030, .040),
)


def _ocr():
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("Local OCR requires pytesseract and Tesseract. Run the optional OCR setup first.") from exc
    configured = os.environ.get("TESSERACT_CMD", "").strip()
    candidates = [
        configured,
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    executable = next((path for path in candidates if path and __import__("pathlib").Path(path).exists()), "")
    if executable:
        pytesseract.pytesseract.tesseract_cmd = executable
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:
        raise RuntimeError("Tesseract executable was not found. Install it, then restart the UI.") from exc
    return pytesseract


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _nearest(text: str, choices: dict[str, str], minimum: float = .72) -> str | None:
    text = _normal(text)
    compact = text.replace(" ", "")
    direct = [value for label, value in sorted(choices.items(), key=lambda item: len(item[0]), reverse=True) if label in text or label.replace(" ", "") in compact]
    if direct:
        return direct[0]
    best = max(((SequenceMatcher(None, text, label).ratio(), value) for label, value in choices.items()), default=(0.0, None))
    return best[1] if best[0] >= minimum else None


def _role_card(
    image: Image.Image,
    role: str,
    columns: dict[str, tuple[float, float]],
    top: float,
    bottom: float,
    pytesseract: Any,
    margins: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> list[dict[str, str]]:
    width, height = image.size
    start, end = columns[role]
    left, right, upper, lower = margins
    crop = image.crop((
        int(width * max(0.0, start + left)),
        int(height * max(0.0, top + upper)),
        int(width * min(1.0, end + right)),
        int(height * min(1.0, bottom + lower)),
    ))
    crop = ImageEnhance.Contrast(ImageOps.grayscale(crop).resize((crop.width * 3, crop.height * 3))).enhance(3.0)
    # Sparse-text mode preserves the vertical order of individual cards much
    # better than a single paragraph for this ornate client background.
    raw_lines = [_normal(line) for line in pytesseract.image_to_string(crop, config="--psm 11").splitlines() if _normal(line)]
    # The client frequently puts multi-word stats on two OCR lines.
    join_heads = {"tormentor", "roshan", "tower", "courier", "madstone", "creep", "teamfight", "first", "runes", "watchers", "camps", "smokes"}
    ordered: list[str] = []
    index = 0
    while index < len(raw_lines):
        line = raw_lines[index]
        if line in join_heads and index + 1 < len(raw_lines):
            next_line = raw_lines[index + 1]
            candidate = f"{line} {next_line}"
            if _nearest(candidate, STATS):
                ordered.append(candidate)
                index += 2
                continue
        ordered.append(line)
        index += 1
    found: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in ordered:
        stat = _nearest(line, STATS)
        if stat:
            if current and current.get("stat_name"):
                found.append(current)
            current = {"stat_name": stat}
            continue
        tier_match = re.search(r"tier\s*(iii|ii|iv|v|i|il)\b", line)
        if tier_match and current is not None:
            tier = tier_match.group(1).replace("il", "ii")
            current["quality_tier"] = TIERS[tier]
            continue
        quality_bonus = re.search(r"\b(10|30|60|100|150)\b", line)
        if quality_bonus and current is not None and "quality_tier" not in current:
            current["quality_tier"] = TIER_FROM_BONUS[quality_bonus.group(1)]
            continue
        trait = _nearest(line, {trait: trait for trait in TRAITS}, minimum=.82)
        if trait and current is not None:
            current["trait_name"] = trait
    if current and current.get("stat_name"):
        found.append(current)
    return found[:5]


def _role_layout_score(roles: dict[str, list[dict[str, str]]]) -> int:
    return sum(
        len(items) * 4 + sum(len({"stat_name", "quality_tier", "trait_name"}.intersection(item)) for item in items)
        for items in roles.values()
    )


def _role_score(items: list[dict[str, str]]) -> int:
    """Prefer five distinct, fully identified emblems over noisy extra text."""
    complete = sum({"stat_name", "quality_tier", "trait_name"}.issubset(item) for item in items)
    distinct_stats = len({item.get("stat_name") for item in items if item.get("stat_name")})
    return complete * 20 + len(items) * 4 + distinct_stats * 3


def _complete_role(items: list[dict[str, str]]) -> bool:
    return len(items) == 5 and all(
        {"stat_name", "quality_tier", "trait_name"}.issubset(item)
        for item in items
    )


TOKEN_LAYOUTS = (
    # Official client with a persistent left navigation panel.
    ((.39, .53), (.532, .667), (.67, .806)),
    # Captures without that panel, plus common cropped 16:9 screenshots.
    ((.22, .41), (.415, .60), (.605, .79)),
)


def _button_score(text: str) -> int:
    keywords = ("reroll", "stat", "quality", "trait", "emblem", "increase", "reduce", "random")
    return sum(text.count(word) * (3 if word in {"reroll", "increase", "quality"} else 1) for word in keywords)


def _read_button_text(image: Image.Image, start: float, end: float, pytesseract: Any) -> str:
    width, height = image.size
    # Buttons move slightly between UI scale modes. Reading three overlapping
    # vertical crops is much more robust than assuming one fixed baseline.
    attempts: list[str] = []
    for top, bottom in ((.775, .865), (.795, .885), (.815, .905), (.875, .985), (.895, 1.0)):
        crop = image.crop((int(width * start), int(height * top), int(width * end), int(height * bottom)))
        enlarged = crop.resize((crop.width * 6, crop.height * 6))
        # Gold lettering separates from the brown button better in colour than
        # grayscale; grayscale removed precisely the contrast we need here.
        attempts.extend(pytesseract.image_to_string(enlarged, config=config) for config in ("--psm 6", "--psm 7", "--psm 11"))
    normalized = [_normal(text) for text in attempts]
    return max(normalized, key=lambda text: (_button_score(text), sum(char.isalpha() for char in text)), default="")


def _token_from_button_text(text: str) -> tuple[str, str | None]:
    """Map OCR text to an exact token ID whenever scope is visible."""
    compact = _normal(text).replace(" ", "")
    if "increasetwo" in compact and ("reduceone" in compact or "reduce" in compact):
        return "quality_shift_plus2_minus1", None
    if "increaseone" in compact or "improveone" in compact:
        return "quality_shift_plus1", None

    family = next((name for name in ("stat", "quality", "trait") if name in compact), "")
    color = next((name for name in ("red", "green", "blue") if name in compact), "")
    if not family or not color:
        return "", None
    if "last" in compact:
        scope = "last"
    elif "first" in compact:
        scope = "first"
    elif "random" in compact or "oneemblem" in compact:
        scope = "random_one"
    else:
        # The client wording "for red emblems" denotes the color-wide action.
        scope = "all"
    note = None if scope != "all" or "emblems" in compact else "Scope inferred as all; verify the client wording."
    return f"{family}_{scope}_{color}", note


def _token_suggestions(image: Image.Image, pytesseract: Any) -> tuple[list[str], list[str], list[str], int | None]:
    width, height = image.size
    layouts = [[_read_button_text(image, start, end, pytesseract) for start, end in layout] for layout in TOKEN_LAYOUTS]
    # Pick one layout globally. Mixing positions across layouts could assign a
    # left button from one layout and a right button from another.
    button_texts = max(layouts, key=lambda texts: sum(_button_score(text) for text in texts))
    suggested: list[str] = []
    notes: list[str] = []
    for text in button_texts:
        token, note = _token_from_button_text(text)
        if token:
            suggested.append(token)
        if note:
            notes.append(f"{token}: {note}")
    count_crop = image.crop((int(width * .52), int(height * .86), int(width * .82), int(height * .91)))
    count_text = _normal(pytesseract.image_to_string(ImageOps.autocontrast(ImageOps.grayscale(count_crop).resize((count_crop.width * 4, count_crop.height * 4))), config="--psm 11"))
    token_count_match = re.search(r"(?:roll\s*)?tokens?\s*(\d{1,2})", count_text)
    return suggested[:3], notes, button_texts, int(token_count_match.group(1)) if token_count_match else None


def parse_fantasy_screenshot(data: bytes) -> dict[str, Any]:
    pytesseract = _ocr()
    image = Image.open(io.BytesIO(data)).convert("RGB")
    base_columns, base_top, base_bottom = ROLE_LAYOUTS[0]
    roles = {
        role: _role_card(image, role, base_columns, base_top, base_bottom, pytesseract)
        for role in ROLE_NAMES
    }
    # Most full client screenshots use the first layout. Avoid six additional
    # OCR passes when it has already found all 15 complete emblems.
    if not all(_complete_role(items) for items in roles.values()):
        role_candidates = {role: [items] for role, items in roles.items()}
        for columns, top, bottom in ROLE_LAYOUTS:
            for margins in ROLE_CROP_VARIANTS:
                if (columns, top, bottom) == ROLE_LAYOUTS[0] and margins == ROLE_CROP_VARIANTS[0]:
                    continue
                for role in ROLE_NAMES:
                    role_candidates[role].append(_role_card(image, role, columns, top, bottom, pytesseract, margins))
        roles = {role: max(candidates, key=_role_score) for role, candidates in role_candidates.items()}
    slots = []
    incomplete = []
    for role, items in roles.items():
        if len(items) != 5 or any(not {"stat_name", "quality_tier", "trait_name"}.issubset(item) for item in items):
            incomplete.append(role)
        for index, item in enumerate(items, start=1):
            slots.append({"role_scope": role, "slot_index": index, **item})
    tokens, notes, button_texts, token_count = _token_suggestions(image, pytesseract)
    return {"slots": slots, "roles": roles, "tokens": tokens, "token_button_texts": button_texts, "roll_tokens_remaining": token_count, "complete": not incomplete, "incomplete_roles": incomplete, "notes": notes}
