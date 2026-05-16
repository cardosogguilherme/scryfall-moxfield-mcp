"""
Regression tests for JSON payload size.

Target: lean card < 600 bytes; 100-card enriched deck < 35KB.
These guard against transformer regressions that silently bloat context usage.
"""

import json
import pytest
from scryfallmcp.scryfall.client import _card_to_dict

# Representative raw Scryfall cards (worst-case oracle text, realistic prices)
_AURELIA = {
    "name": "Aurelia, the Warleader",
    "mana_cost": "{2}{R}{R}{W}{W}",
    "cmc": 6.0,
    "type_line": "Legendary Creature — Angel",
    "oracle_text": (
        "Flying, vigilance, haste\n"
        "Whenever Aurelia, the Warleader attacks for the first time each turn, "
        "untap all creatures you control. After this phase, there is an "
        "additional combat phase."
    ),
    "colors": ["R", "W"],
    "color_identity": ["R", "W"],
    "keywords": ["Flying", "Vigilance", "Haste"],
    "set": "rtr",
    "rarity": "mythic",
    "power": "3",
    "toughness": "5",
    "loyalty": None,
    "legalities": {"commander": "legal", "modern": "not_legal", "legacy": "legal",
                   "vintage": "legal", "pauper": "not_legal", "standard": "not_legal",
                   "pioneer": "not_legal", "explorer": "not_legal", "alchemy": "not_legal",
                   "historic": "legal", "timeless": "legal", "oathbreaker": "legal",
                   "paupercommander": "not_legal", "duel": "legal",
                   "penny": "not_legal", "oldschool": "not_legal",
                   "premodern": "not_legal", "predh": "not_legal",
                   "gladiator": "legal", "brawl": "not_legal", "standardbrawl": "not_legal",
                   "future": "not_legal", "alchemy": "not_legal"},
    "prices": {"usd": "2.50", "usd_foil": "8.00", "usd_etched": None, "eur": "2.20",
               "eur_foil": None, "tix": "0.05"},
}

_PLAINS = {
    "name": "Plains",
    "mana_cost": None,
    "cmc": 0.0,
    "type_line": "Basic Land — Plains",
    "oracle_text": "({T}: Add {W}.)",
    "colors": [],
    "color_identity": ["W"],
    "keywords": [],
    "set": "lea",
    "rarity": "land",
    "power": None,
    "toughness": None,
    "loyalty": None,
    "legalities": {"commander": "legal", "modern": "legal"},
    "prices": {"usd": "0.15", "usd_foil": None, "usd_etched": None, "eur": None, "tix": None},
}

_SOL_RING = {
    "name": "Sol Ring",
    "mana_cost": "{1}",
    "cmc": 1.0,
    "type_line": "Artifact",
    "oracle_text": "{T}: Add {C}{C}.",
    "colors": [],
    "color_identity": [],
    "keywords": [],
    "set": "lea",
    "rarity": "uncommon",
    "power": None,
    "toughness": None,
    "loyalty": None,
    "legalities": {"commander": "legal", "modern": "not_legal"},
    "prices": {"usd": "1.50", "usd_foil": None, "usd_etched": None, "eur": None, "tix": "0.10"},
}


def _bytes(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def test_lean_creature_under_600_bytes():
    """Aurelia (complex creature) must fit under 600 bytes in lean mode."""
    result = _card_to_dict(_AURELIA)
    size = _bytes(result)
    assert size < 600, f"Lean creature card too large: {size} bytes (target < 600)"


def test_lean_land_under_300_bytes():
    """Basic land (minimal text) must fit under 300 bytes in lean mode."""
    result = _card_to_dict(_PLAINS)
    size = _bytes(result)
    assert size < 300, f"Lean land card too large: {size} bytes (target < 300)"


def test_lean_artifact_under_300_bytes():
    """Simple artifact must fit under 300 bytes in lean mode."""
    result = _card_to_dict(_SOL_RING)
    size = _bytes(result)
    assert size < 300, f"Lean artifact card too large: {size} bytes (target < 300)"


def test_lean_omits_fat_fields():
    """Lean mode must not contain legalities object or prices object."""
    for raw in (_AURELIA, _PLAINS, _SOL_RING):
        result = _card_to_dict(raw)
        assert "legalities" not in result, "legalities must be absent in lean mode"
        assert "prices" not in result, "prices must be absent in lean mode"
        assert "colors" not in result, "colors must be absent in lean mode"
        assert "commander_legal" in result
        assert "price_usd" in result


def test_full_mode_restores_legalities_and_prices():
    result = _card_to_dict(_AURELIA, include_all_legalities=True, include_all_prices=True)
    assert "legalities" in result
    assert "prices" in result
    assert "commander_legal" not in result
    assert "price_usd" not in result


def test_100_card_deck_under_35kb():
    """
    Simulated 100-card enriched deck payload must stay under 35KB.
    Baseline before optimization: ~80KB. Target: ≥60% reduction → ~32KB.
    35KB is a safe guard rail.
    """
    # Mix representative cards to simulate a Commander deck
    raw_pool = [_AURELIA, _PLAINS, _SOL_RING]
    cards = [_card_to_dict(raw_pool[i % len(raw_pool)]) for i in range(100)]
    deck_payload = {
        "id": "test-deck",
        "name": "Test Commander",
        "format": "commander",
        "boards": {"mainboard": [{"name": c["name"], "quantity": 1, **c} for c in cards]},
        "price_total_usd": "150.00",
    }
    size = _bytes(deck_payload)
    assert size < 35_000, f"100-card deck payload too large: {size} bytes (target < 35 000)"
