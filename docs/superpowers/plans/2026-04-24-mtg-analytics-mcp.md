# mtg-analytics-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the six deck analytics tools from `scryfallmcp` into a standalone `mtg-analytics-mcp` package where all functions accept pre-fetched card dicts and have zero external HTTP dependencies.

**Architecture:** New repo at `D:\repos\mtg-analytics-mcp\` containing a pure-Python `DeckAnalytics` class with sync methods (no async, no Scryfall client). A `FastMCP` server wraps the class as sync tools. The original `scryfallmcp` drops the `deck_analytics` module and all six analytics tools.

**Tech Stack:** Python 3.11+, `mcp[cli]`, `pytest`, `pytest-asyncio`, `hatchling`

---

### Task 1: Bootstrap new repo

**Files:**
- Create: `D:\repos\mtg-analytics-mcp\pyproject.toml`
- Create: `D:\repos\mtg-analytics-mcp\mtganalytics\__init__.py`
- Create: `D:\repos\mtg-analytics-mcp\tests\__init__.py`

- [ ] **Step 1: Create directories and init git**

```bash
mkdir D:\repos\mtg-analytics-mcp
cd D:\repos\mtg-analytics-mcp
git init
mkdir mtganalytics tests
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mtg-analytics-mcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["mcp[cli]"]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio>=0.21"]

[project.scripts]
mtg-analytics-mcp = "mtganalytics.server:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create empty package init files**

`mtganalytics/__init__.py` — empty file

`tests/__init__.py` — empty file

- [ ] **Step 4: Create venv and install**

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected output ends with: `Successfully installed mtg-analytics-mcp-0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml mtganalytics/__init__.py tests/__init__.py
git commit -m "chore: bootstrap mtg-analytics-mcp package"
```

---

### Task 2: Write failing tests

**Files:**
- Create: `D:\repos\mtg-analytics-mcp\tests\test_analytics.py`

- [ ] **Step 1: Create `tests/test_analytics.py`**

```python
import pytest
from mtganalytics.analytics import DeckAnalytics, _count_pips

MOCK_CARDS = [
    {
        "name": "Lightning Bolt",
        "mana_cost": "{R}",
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "colors": ["R"],
        "cmc": 1.0,
    },
    {
        "name": "Counterspell",
        "mana_cost": "{U}{U}",
        "type_line": "Instant",
        "oracle_text": "Counter target spell.",
        "colors": ["U"],
        "cmc": 2.0,
    },
    {
        "name": "Sol Ring",
        "mana_cost": "{1}",
        "type_line": "Artifact",
        "oracle_text": "Tap: Add {C}{C}.",
        "colors": [],
        "cmc": 1.0,
    },
    {
        "name": "Cultivate",
        "mana_cost": "{2}{G}",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for a basic land card and put it onto the battlefield.",
        "colors": ["G"],
        "cmc": 3.0,
    },
    {
        "name": "Command Tower",
        "mana_cost": None,
        "type_line": "Land",
        "oracle_text": "Tap: Add one mana of any color in your commander's color identity.",
        "colors": [],
        "cmc": 0.0,
    },
    {
        "name": "Wrath of God",
        "mana_cost": "{2}{W}{W}",
        "type_line": "Sorcery",
        "oracle_text": "Destroy all creatures. They can't be regenerated.",
        "colors": ["W"],
        "cmc": 4.0,
    },
]


@pytest.fixture
def analytics():
    return DeckAnalytics()


def test_count_pips():
    assert _count_pips("{R}") == {"R": 1}
    assert _count_pips("{U}{U}") == {"U": 2}
    assert _count_pips("{2}{W}{W}") == {"W": 2}
    assert _count_pips("{W}{U}{B}{R}{G}") == {"W": 1, "U": 1, "B": 1, "R": 1, "G": 1}
    assert _count_pips(None) == {}
    assert _count_pips("{1}") == {}


def test_analyze_mana_curve(analytics):
    result = analytics.analyze_mana_curve(MOCK_CARDS)
    assert "distribution" in result
    assert "avg_cmc" in result
    assert "avg_cmc_excl_lands" in result
    dist = result["distribution"]
    assert dist["1"] == 2  # Lightning Bolt + Sol Ring
    assert dist["2"] == 1  # Counterspell
    assert dist["3"] == 1  # Cultivate
    assert dist["4"] == 1  # Wrath of God
    assert dist["0"] == 1  # Command Tower (CMC 0)
    # avg CMC excl lands: (1+2+1+3+4)/5 = 2.2
    assert result["avg_cmc_excl_lands"] == 2.2


def test_analyze_color_requirements(analytics):
    result = analytics.analyze_color_requirements(MOCK_CARDS)
    colors = result["colors"]
    assert "W" in colors
    assert colors["W"]["max_pips_in_cost"] == 2
    assert colors["W"]["sources_recommended"] == 20
    assert "U" in colors
    assert colors["U"]["max_pips_in_cost"] == 2
    assert "R" in colors
    assert colors["R"]["max_pips_in_cost"] == 1
    assert colors["R"]["sources_recommended"] == 12


def test_hypergeometric_probability(analytics):
    result = analytics.hypergeometric_probability(
        deck_size=99, successes_in_deck=1, sample_size=7, min_successes=1
    )
    assert result["probability"] == pytest.approx(
        1 - (98 * 97 * 96 * 95 * 94 * 93 * 92) / (99 * 98 * 97 * 96 * 95 * 94 * 93), abs=0.001
    )
    assert 0 < result["probability"] < 1
    assert result["probability_pct"] == round(result["probability"] * 100, 2)


def test_hypergeometric_probability_invalid_params(analytics):
    result = analytics.hypergeometric_probability(
        deck_size=10, successes_in_deck=20, sample_size=7, min_successes=1
    )
    assert "error" in result


def test_categorize_deck(analytics):
    result = analytics.categorize_deck(MOCK_CARDS)
    counts = result["counts"]
    cards = result["cards"]
    assert counts["Lands"] == 1
    assert "Command Tower" in cards["Lands"]
    assert counts["Board Wipes"] == 1
    assert "Wrath of God" in cards["Board Wipes"]
    assert "Cultivate" in cards["Ramp"]
    assert "targets" in result
    assert "flags" in result


def test_suggest_land_count_with_cards(analytics):
    result = analytics.suggest_land_count(cards=MOCK_CARDS)
    assert "recommended_lands" in result
    assert 30 <= result["recommended_lands"] <= 45
    assert "reasoning" in result


def test_suggest_land_count_manual_inputs(analytics):
    result = analytics.suggest_land_count(avg_cmc=3.5, ramp_count=8)
    assert "recommended_lands" in result
    # base 37 + cmc_adjustment round((3.5-3.0)*2)=1, ramp_adjustment -min(8,10)=-8 → 30
    assert result["recommended_lands"] == 30


def test_goldfish_opening_hands(analytics):
    result = analytics.goldfish_opening_hands(MOCK_CARDS, num_hands=100)
    assert "avg_lands_in_kept_hand" in result
    assert "ramp_in_opening_hand_pct" in result
    assert result["num_hands"] == 100
    assert result["mulligan_rule"] == "london"
    assert 0 <= result["ramp_in_opening_hand_pct"] <= 100
```

- [ ] **Step 2: Run tests to verify they all fail with ImportError**

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: all tests fail with `ModuleNotFoundError: No module named 'mtganalytics.analytics'`

---

### Task 3: Port analytics module (make tests pass)

**Files:**
- Create: `D:\repos\mtg-analytics-mcp\mtganalytics\analytics.py`

- [ ] **Step 1: Create `mtganalytics/analytics.py`**

```python
import math
import random
import re

_CATEGORY_PATTERNS: dict[str, list[str]] = {
    "Ramp": ["add {", "add mana", "search your library for a", "land card", "mana rock"],
    "Card Draw": ["draw a card", "draw two", "draw three", "draw cards", "draw x"],
    "Targeted Removal": [
        "destroy target",
        "exile target",
        "return target",
        "tap target",
        "counter target spell",
    ],
    "Board Wipes": [
        "destroy all",
        "exile all",
        "return all",
        "each creature",
        "deals damage to each",
    ],
    "Tutors": [
        "search your library",
        "reveal it",
        "put it into your hand",
        "put it onto the battlefield",
    ],
    "Protection": [
        "hexproof",
        "shroud",
        "indestructible",
        "regenerate",
        "protection from",
        "can't be countered",
    ],
    "Win Conditions": [
        "you win the game",
        "lose the game",
        "infinite",
        "opponents lose",
        "each opponent loses",
    ],
}

COMMANDER_TARGETS = {
    "Ramp": 10,
    "Card Draw": 10,
    "Targeted Removal": 8,
    "Board Wipes": 3,
    "Tutors": 0,
    "Protection": 0,
    "Win Conditions": 0,
    "Lands": 36,
}


def _count_pips(mana_cost: str | None) -> dict[str, int]:
    if not mana_cost:
        return {}
    pips: dict[str, int] = {}
    for symbol in re.findall(r"\{([^}]+)\}", mana_cost):
        for ch in symbol.upper():
            if ch in "WUBRG":
                pips[ch] = pips.get(ch, 0) + 1
    return pips


def _karsten_sources_needed(max_pips: int) -> int:
    if max_pips <= 1:
        return 12
    elif max_pips == 2:
        return 20
    elif max_pips >= 3:
        return 27
    return 12


class DeckAnalytics:
    def __init__(self):
        pass

    def _is_land(self, card: dict) -> bool:
        return "Land" in (card.get("type_line") or "")

    def _is_mana_source(self, card: dict) -> bool:
        oracle = (card.get("oracle_text") or "").lower()
        type_line = (card.get("type_line") or "").lower()
        return "land" in type_line or "add {" in oracle or "add mana" in oracle

    def analyze_mana_curve(self, cards: list[dict]) -> dict:
        buckets: dict[str, int] = {
            "0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7+": 0
        }
        total_cmc = 0.0
        nonland_cmc = 0.0
        nonland_count = 0
        total_count = 0

        for card in cards:
            cmc = card.get("cmc") or 0
            total_cmc += cmc
            total_count += 1
            bucket = str(int(cmc)) if cmc <= 6 else "7+"
            buckets[bucket] = buckets.get(bucket, 0) + 1
            if not self._is_land(card):
                nonland_cmc += cmc
                nonland_count += 1

        return {
            "distribution": buckets,
            "avg_cmc": round(total_cmc / total_count, 2) if total_count else 0,
            "avg_cmc_excl_lands": round(nonland_cmc / nonland_count, 2) if nonland_count else 0,
            "total_cards": total_count,
        }

    def analyze_color_requirements(self, cards: list[dict]) -> dict:
        pip_counts: dict[str, int] = {}
        actual_sources: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}

        for card in cards:
            pips = _count_pips(card.get("mana_cost"))
            for color, count in pips.items():
                pip_counts[color] = max(pip_counts.get(color, 0), count)
            if self._is_mana_source(card):
                for color in (card.get("colors") or []):
                    if color in actual_sources:
                        actual_sources[color] += 1

        analysis: dict[str, dict] = {}
        for color in "WUBRG":
            if color not in pip_counts and actual_sources.get(color, 0) == 0:
                continue
            max_pip = pip_counts.get(color, 0)
            needed = _karsten_sources_needed(max_pip) if max_pip > 0 else 0
            have = actual_sources.get(color, 0)
            analysis[color] = {
                "max_pips_in_cost": max_pip,
                "sources_recommended": needed,
                "sources_actual": have,
                "deficit": max(0, needed - have),
                "surplus": max(0, have - needed),
            }

        return {"colors": analysis}

    def hypergeometric_probability(
        self,
        deck_size: int,
        successes_in_deck: int,
        sample_size: int,
        min_successes: int = 1,
    ) -> dict:
        N, K, n, k_min = deck_size, successes_in_deck, sample_size, min_successes
        if K > N or n > N or k_min > K:
            return {"error": "invalid_parameters"}
        prob = sum(
            math.comb(K, k) * math.comb(N - K, n - k) / math.comb(N, n)
            for k in range(k_min, min(K, n) + 1)
        )
        return {
            "deck_size": N,
            "successes_in_deck": K,
            "sample_size": n,
            "min_successes": k_min,
            "probability": round(prob, 4),
            "probability_pct": round(prob * 100, 2),
        }

    def categorize_deck(self, cards: list[dict]) -> dict:
        categories: dict[str, list[str]] = {cat: [] for cat in _CATEGORY_PATTERNS}
        categories["Lands"] = []
        categories["Creatures"] = []
        categories["Other"] = []

        for card in cards:
            name = card.get("name") or ""
            oracle = (card.get("oracle_text") or "").lower()
            type_line = (card.get("type_line") or "").lower()

            if "land" in type_line:
                categories["Lands"].append(name)
                continue

            matched = False
            for category, patterns in _CATEGORY_PATTERNS.items():
                if any(p in oracle for p in patterns):
                    categories[category].append(name)
                    matched = True
                    break

            if not matched:
                if "creature" in type_line:
                    categories["Creatures"].append(name)
                else:
                    categories["Other"].append(name)

        counts = {cat: len(card_list) for cat, card_list in categories.items()}
        return {
            "counts": counts,
            "cards": categories,
            "targets": COMMANDER_TARGETS,
            "flags": {
                cat: f"You have {counts.get(cat, 0)}, target is {tgt}"
                for cat, tgt in COMMANDER_TARGETS.items()
                if tgt > 0 and counts.get(cat, 0) < tgt
            },
        }

    def suggest_land_count(
        self,
        cards: list[dict] | None = None,
        avg_cmc: float | None = None,
        ramp_count: int | None = None,
    ) -> dict:
        if cards:
            non_lands = [c for c in cards if not self._is_land(c)]
            if non_lands:
                avg_cmc = sum(c.get("cmc") or 0 for c in non_lands) / len(non_lands)
            ramp_count = sum(
                1 for c in cards
                if any(p in (c.get("oracle_text") or "").lower() for p in _CATEGORY_PATTERNS["Ramp"])
                and not self._is_land(c)
            )

        avg_cmc = avg_cmc or 3.0
        ramp_count = ramp_count or 0

        base = 37
        cmc_adjustment = round((avg_cmc - 3.0) * 2)
        ramp_adjustment = -min(ramp_count, 10)
        recommended = max(30, min(45, base + cmc_adjustment + ramp_adjustment))

        return {
            "recommended_lands": recommended,
            "inputs": {"avg_cmc": round(avg_cmc, 2), "ramp_count": ramp_count},
            "reasoning": (
                f"Base 37 lands, {cmc_adjustment:+d} for avg CMC of {avg_cmc:.1f}, "
                f"{ramp_adjustment:+d} for {ramp_count} ramp spells."
            ),
        }

    def goldfish_opening_hands(
        self,
        cards: list[dict],
        num_hands: int = 1000,
        mulligan_rule: str = "london",
    ) -> dict:
        card_names = [c.get("name") or "Unknown" for c in cards]
        is_land = {c.get("name"): self._is_land(c) for c in cards}
        colors_by_name = {c.get("name"): c.get("colors") or [] for c in cards}
        oracle_texts = {c.get("name"): (c.get("oracle_text") or "").lower() for c in cards}

        def hand_keepable(hand: list[str], hand_size: int) -> bool:
            land_count = sum(1 for c in hand if is_land.get(c, False))
            min_lands = max(1, hand_size - 5)
            max_lands = min(hand_size - 2, 5)
            return min_lands <= land_count <= max_lands

        land_totals = []
        color_hits: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
        ramp_hits = 0

        for _ in range(num_hands):
            deck = card_names.copy()
            random.shuffle(deck)

            if mulligan_rule == "london":
                hand = deck[:7]
                hand_size = 7
                while hand_size > 1 and not hand_keepable(hand, hand_size):
                    hand_size -= 1
                    hand = deck[:7]
                hand = hand[:hand_size]
            else:
                hand = deck[:7]
                hand_size = 7
                while hand_size > 1 and not hand_keepable(hand, hand_size):
                    hand_size -= 1
                    random.shuffle(deck)
                    hand = deck[:hand_size]

            land_totals.append(sum(1 for c in hand if is_land.get(c, False)))

            colors_present: set[str] = set()
            for card in hand:
                for color in colors_by_name.get(card, []):
                    colors_present.add(color)
            for c in colors_present:
                if c in color_hits:
                    color_hits[c] += 1

            for card in hand:
                if any(p in oracle_texts.get(card, "") for p in _CATEGORY_PATTERNS["Ramp"]):
                    ramp_hits += 1
                    break

        avg_lands = sum(land_totals) / len(land_totals) if land_totals else 0
        return {
            "num_hands": num_hands,
            "avg_lands_in_kept_hand": round(avg_lands, 2),
            "ramp_in_opening_hand_pct": round(ramp_hits / num_hands * 100, 1),
            "color_presence_pct": {
                color: round(hits / num_hands * 100, 1)
                for color, hits in color_hits.items()
                if hits > 0
            },
            "mulligan_rule": mulligan_rule,
        }
```

- [ ] **Step 2: Run tests — expect all to pass**

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: `9 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_analytics.py mtganalytics/analytics.py
git commit -m "feat: add DeckAnalytics with card-dict input signatures"
```

---

### Task 4: Create FastMCP server

**Files:**
- Create: `D:\repos\mtg-analytics-mcp\mtganalytics\server.py`

- [ ] **Step 1: Create `mtganalytics/server.py`**

```python
from mcp.server.fastmcp import FastMCP
from mtganalytics.analytics import DeckAnalytics

mcp = FastMCP("mtg-analytics-mcp")
_analytics = DeckAnalytics()


@mcp.tool()
def analyze_mana_curve(cards: list[dict]) -> dict:
    """Analyze the mana curve of a decklist.

    cards: list of card objects from get_cards_bulk (needs 'cmc', 'type_line')
    Returns CMC distribution (0–7+), average CMC, and average CMC excluding lands.
    """
    return _analytics.analyze_mana_curve(cards)


@mcp.tool()
def analyze_color_requirements(cards: list[dict]) -> dict:
    """Analyze mana base requirements using Frank Karsten's pip-counting model.

    cards: list of card objects from get_cards_bulk (needs 'mana_cost', 'colors', 'oracle_text', 'type_line')
    Flags color deficits: 'you want 18 W sources, you have 14.'
    """
    return _analytics.analyze_color_requirements(cards)


@mcp.tool()
def hypergeometric_probability(
    deck_size: int,
    successes_in_deck: int,
    sample_size: int,
    min_successes: int = 1,
) -> dict:
    """Calculate the probability of drawing at least min_successes copies in sample_size draws.

    Example: chance of seeing at least 1 ramp piece in your opening hand of 7.
    """
    return _analytics.hypergeometric_probability(
        deck_size, successes_in_deck, sample_size, min_successes
    )


@mcp.tool()
def categorize_deck(cards: list[dict]) -> dict:
    """Classify cards into functional categories (Ramp, Draw, Removal, Wipes, etc.).

    cards: list of card objects from get_cards_bulk (needs 'name', 'oracle_text', 'type_line')
    Returns counts, card lists per category, and Commander rule-of-thumb targets.
    """
    return _analytics.categorize_deck(cards)


@mcp.tool()
def suggest_land_count(
    cards: list[dict] | None = None,
    avg_cmc: float | None = None,
    ramp_count: int | None = None,
) -> dict:
    """Recommend a land count based on Frank Karsten's Commander formula.

    Pass either cards (from get_cards_bulk) OR avg_cmc + ramp_count directly.
    """
    return _analytics.suggest_land_count(cards=cards, avg_cmc=avg_cmc, ramp_count=ramp_count)


@mcp.tool()
def goldfish_opening_hands(
    cards: list[dict],
    num_hands: int = 1000,
    mulligan_rule: str = "london",
) -> dict:
    """Simulate N opening hands and return statistics (avg lands, ramp presence, colors).

    cards: list of card objects from get_cards_bulk
    mulligan_rule: 'london' (default) or 'vancouver'
    """
    return _analytics.goldfish_opening_hands(cards, num_hands=num_hands, mulligan_rule=mulligan_rule)


def main():
    import os
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify server imports cleanly**

```bash
.venv\Scripts\python.exe -c "from mtganalytics.server import mcp; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add mtganalytics/server.py
git commit -m "feat: add FastMCP server wrapping DeckAnalytics"
```

---

### Task 5: Clean up scryfallmcp

**Files:**
- Delete: `D:\repos\scryfall-moxfield-mcp\scryfallmcp\deck_analytics\` (entire directory)
- Delete: `D:\repos\scryfall-moxfield-mcp\tests\deck_analytics\` (entire directory)
- Modify: `D:\repos\scryfall-moxfield-mcp\scryfallmcp\server.py`

Working directory for this task: `D:\repos\scryfall-moxfield-mcp`

- [ ] **Step 1: Delete deck_analytics module and tests**

```bash
rm -r scryfallmcp/deck_analytics
rm -r tests/deck_analytics
```

- [ ] **Step 2: Update `scryfallmcp/server.py`**

Remove this import (line 9):
```python
from scryfallmcp.deck_analytics.analytics import DeckAnalytics
```

Remove this instantiation (line 21):
```python
_deck_analytics = DeckAnalytics(scryfall_client=_scryfall)
```

Remove the entire `# ── Deck Analytics Tools ──` section (lines 264–339):
```python
# ── Deck Analytics Tools ───────────────────────────────────────────────────────

@mcp.tool()
async def analyze_mana_curve(decklist: list[str]) -> dict:
    ...

@mcp.tool()
async def analyze_color_requirements(decklist: list[str]) -> dict:
    ...

@mcp.tool()
async def hypergeometric_probability(
    deck_size: int,
    successes_in_deck: int,
    sample_size: int,
    min_successes: int = 1,
) -> dict:
    ...

@mcp.tool()
async def categorize_deck(decklist: list[str]) -> dict:
    ...

@mcp.tool()
async def suggest_land_count(
    decklist: list[str] | None = None,
    avg_cmc: float | None = None,
    ramp_count: int | None = None,
) -> dict:
    ...

@mcp.tool()
async def goldfish_opening_hands(
    decklist: list[str],
    num_hands: int = 1000,
    mulligan_rule: str = "london",
) -> dict:
    ...
```

The resulting `server.py` should end with the `# ── Rulings & Oracle Tools ──` section followed by `def main()`.

- [ ] **Step 3: Run scryfallmcp tests — expect 39 pass, 1 pre-existing failure**

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: `39 passed, 1 failed` (the pre-existing `test_save_sets_file_permissions` Windows chmod failure — unrelated to this change)

- [ ] **Step 4: Commit**

```bash
git add scryfallmcp/server.py
git rm -r scryfallmcp/deck_analytics tests/deck_analytics
git commit -m "feat: remove deck analytics tools (moved to mtg-analytics-mcp)"
```
