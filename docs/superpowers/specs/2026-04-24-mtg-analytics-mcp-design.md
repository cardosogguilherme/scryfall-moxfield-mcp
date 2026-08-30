# Design: mtg-analytics-mcp — Separate Analytics MCP Server

**Date:** 2026-04-24  
**Status:** Approved

## Summary

Extract the six deck analytics tools from `scryfallmcp` into a standalone `mtg-analytics-mcp` package with its own FastMCP server. The new server is pure computation — no HTTP client, no Scryfall dependency. All functions that previously fetched card data by name now accept pre-fetched card dicts, making the server independently deployable and trivially testable.

---

## Motivation

The six analytics tools in `scryfallmcp/deck_analytics/` are conceptually different from the rest of the server: they do math and text heuristics, not API fetching. Separating them:

- Eliminates the Scryfall dependency from the analytics layer entirely
- Makes each server independently testable without mocking the other
- Lets the analytics server be registered, updated, or replaced without touching the Scryfall/EDHREC server

---

## New Repo: `mtg-analytics-mcp`

```
mtg-analytics-mcp/
  mtganalytics/
    __init__.py
    analytics.py     ← math/logic only; no httpx, no ScryfallClient
    server.py        ← FastMCP app; wraps analytics.py tools
  tests/
    test_analytics.py
  pyproject.toml
```

**Runtime dependencies:** `mcp` only. No `httpx`, no `respx`, no Scryfall client. Stdlib: `math`, `random`, `re`.

**Registered in Claude Desktop** as a second MCP server alongside `scryfallmcp`.

---

## Signature Changes

All functions that previously accepted `decklist: list[str]` (card names to fetch) now accept `cards: list[dict]` (pre-fetched card objects). The internal `_fetch_cards()` call and `ScryfallClient` injection are removed.

| Tool | Old | New |
|------|-----|-----|
| `analyze_mana_curve` | `(decklist: list[str])` | `(cards: list[dict])` |
| `analyze_color_requirements` | `(decklist: list[str])` | `(cards: list[dict])` |
| `categorize_deck` | `(decklist: list[str])` | `(cards: list[dict])` |
| `suggest_land_count` | `(decklist: list[str] \| None, avg_cmc, ramp_count)` | `(cards: list[dict] \| None, avg_cmc, ramp_count)` |
| `goldfish_opening_hands` | `(decklist: list[str], num_hands, mulligan_rule)` | `(cards: list[dict], num_hands, mulligan_rule)` |
| `hypergeometric_probability` | unchanged | unchanged |

Each card dict is expected to contain the fields already returned by `scryfallmcp`'s `get_cards_bulk`: `name`, `cmc`, `type_line`, `oracle_text`, `colors`, `mana_cost`.

---

## LLM Workflow

The analytics tools now require a two-step call pattern:

```
# Step 1: fetch card objects from scryfallmcp
cards = get_cards_bulk(["Sol Ring", "Command Tower", ...])

# Step 2: pass to mtg-analytics-mcp
result = analyze_mana_curve(cards=cards)
```

This is explicit and composable. The LLM can reuse the same `cards` result across multiple analytics calls without re-fetching.

---

## Changes to `scryfallmcp`

Three deletions, nothing else:

1. Remove `scryfallmcp/deck_analytics/` (entire directory)
2. Remove `tests/deck_analytics/` (entire directory)
3. Remove 6 analytics tools, their imports, and the `_deck_analytics` instance from `server.py`

All other modules (edhrec, commander_spellbook, rulings, scryfall) are untouched.

---

## Testing

Tests move from `tests/deck_analytics/test_analytics.py` in `scryfallmcp` to `tests/test_analytics.py` in `mtg-analytics-mcp`. The mock pattern changes: instead of mocking `scryfall.get_cards_bulk`, tests pass `MOCK_CARDS` dicts directly to the functions — simpler and faster.

---

## Out of Scope

- No shared library (`mtg-analytics-core`) — two consumers doesn't justify a third artifact
- No field-typed card schemas — full card dicts from `get_cards_bulk` are always available
- No changes to EDHREC, Commander Spellbook, Rulings, or Scryfall modules
