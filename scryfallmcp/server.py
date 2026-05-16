from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP
from scryfallmcp.scryfall.client import ScryfallClient
from scryfallmcp.moxfield.client import MoxfieldClient
from scryfallmcp.moxfield.auth import CredentialManager
from scryfallmcp.edhrec.client import EDHRecClient
from scryfallmcp.commander_spellbook.client import CommanderSpellbookClient
from scryfallmcp.rulings.client import RulingsClient

mcp = FastMCP("scryfallmcp")

_scryfall = ScryfallClient()
_cred_manager = CredentialManager()
_moxfield = MoxfieldClient(credential_manager=_cred_manager, scryfall_client=_scryfall)
_edhrec = EDHRecClient()
_spellbook = CommanderSpellbookClient()
_rulings = RulingsClient(scryfall_client=_scryfall)


# ── Scryfall ────────────────────────────────────────────────────────────────────

@mcp.tool()
async def search_cards(
    query: Annotated[str, "Scryfall search syntax, e.g. 't:dragon c:r', 'is:commander identity:gruul'"],
    page: Annotated[int, "Page number for paginated results"] = 1,
) -> list[dict] | dict:
    """Search cards using full Scryfall syntax."""
    return await _scryfall.search_cards(query, page=page)


@mcp.tool()
async def get_card_by_set(
    set_code: Annotated[str, "Three-letter set code, e.g. 'mh3'"],
    collector_number: Annotated[str, "Collector number, e.g. '237'"],
    include_all_legalities: Annotated[bool, "Return full legalities object instead of commander_legal boolean"] = False,
    include_all_prices: Annotated[bool, "Return full prices object instead of price_usd string"] = False,
) -> dict:
    """Fetch a specific card printing by set code and collector number."""
    return await _scryfall.get_card_by_set(
        set_code, collector_number,
        include_all_legalities=include_all_legalities,
        include_all_prices=include_all_prices,
    )


@mcp.tool()
async def get_cards_bulk(
    names: list[str],
    include_all_legalities: Annotated[bool, "Return full legalities object instead of commander_legal boolean"] = False,
    include_all_prices: Annotated[bool, "Return full prices object instead of price_usd string"] = False,
) -> list[dict]:
    """Fetch multiple cards by name in one call; batching is handled automatically."""
    return await _scryfall.get_cards_bulk(
        names,
        include_all_legalities=include_all_legalities,
        include_all_prices=include_all_prices,
    )


# ── Moxfield ────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_user_decks(
    username: Annotated[str, "Moxfield display name / URL slug, e.g. 'johndoe'"],
    name_filter: Annotated[str | None, "Case-insensitive name fragment; returns only matching decks when provided"] = None,
) -> list[dict] | dict:
    """List a user's Moxfield decks, optionally filtered by name fragment."""
    try:
        if name_filter:
            return await _moxfield.find_deck(name_filter, username)
        return await _moxfield.get_user_decks(username)
    except RuntimeError as e:
        return {"error": "moxfield_auth_required", "reason": str(e)}


@mcp.tool()
async def get_deck(
    deck_id: Annotated[str, "Public deck ID from the Moxfield URL"],
    enrich_with_scryfall: Annotated[
        Literal["lean", "full", False],
        "'lean' (default): trimmed Scryfall data, commander_legal + price_usd. 'full': all fields. False: skip enrichment.",
    ] = "lean",
) -> dict:
    """Fetch a Moxfield deck by public ID, enriched with Scryfall card data."""
    try:
        return await _moxfield.get_deck(deck_id, enrich_with_scryfall=enrich_with_scryfall)
    except RuntimeError as e:
        return {"error": "moxfield_auth_required", "reason": str(e)}


# ── EDHREC ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_commander_recommendations(
    commander_name: Annotated[str, "Full card name, e.g. 'Krenko, Mob Boss'"],
    theme: Annotated[str | None, "Theme slug, e.g. 'tokens'; use get_commander_themes to list"] = None,
    budget: Annotated[str | None, "Price filter: 'budget' or 'expensive'"] = None,
) -> list[dict] | dict:
    """Get EDHREC card recommendations for a Commander grouped by category."""
    return await _edhrec.get_commander_recommendations(commander_name, theme=theme, budget=budget)


@mcp.tool()
async def get_commander_themes(
    commander_name: Annotated[str, "Full card name"],
) -> list[dict] | dict:
    """List available themes and strategies for a Commander on EDHREC."""
    return await _edhrec.get_commander_themes(commander_name)


@mcp.tool()
async def get_card_top_commanders(card_name: str) -> list[dict] | dict:
    """Reverse EDHREC lookup: which Commanders most frequently run this card."""
    return await _edhrec.get_card_top_commanders(card_name)


@mcp.tool()
async def get_average_deck(
    commander_name: Annotated[str, "Full card name"],
    theme: Annotated[str | None, "Optional theme slug to filter the average deck"] = None,
) -> list[dict] | dict:
    """Return the statistical average 99-card EDHREC decklist for a Commander."""
    return await _edhrec.get_average_deck(commander_name, theme=theme)


@mcp.tool()
async def get_budget_alternatives(
    card_name: Annotated[str, "Full card name"],
    max_price_usd: Annotated[float | None, "Maximum price in USD for alternatives"] = None,
) -> list[dict] | dict:
    """Find functionally similar, cheaper alternatives to a card via EDHREC."""
    return await _edhrec.get_budget_alternatives(card_name, max_price_usd=max_price_usd)


# ── Commander Spellbook ─────────────────────────────────────────────────────────

@mcp.tool()
async def combo_find(
    scope: Annotated[Literal["card", "colors", "decklist", "near_miss"], "Search mode: by card name, color identity, decklist membership, or near-miss"],
    target: Annotated[str | list[str], "Card name (card), color identity like 'WUB' (colors), or list of card names (decklist/near_miss)"],
    missing_max: Annotated[int, "Max missing pieces; near_miss scope only"] = 1,
    max_pieces: Annotated[int | None, "Max combo size filter; colors scope only"] = None,
    results_include: Annotated[str | None, "Effect text filter, e.g. 'infinite mana'; colors scope only"] = None,
    max_price_usd: Annotated[float | None, "Max total combo price; colors scope only"] = None,
    color_identity: Annotated[str | None, "Color identity filter for results; near_miss scope only"] = None,
) -> list[dict] | dict:
    """Find Commander Spellbook combos by card, color identity, decklist membership, or near-miss."""
    if scope == "card":
        return await _spellbook.find_combos_with_card(str(target))
    if scope == "colors":
        return await _spellbook.find_combos_in_colors(
            str(target),
            max_pieces=max_pieces,
            results_include=results_include,
            max_price_usd=max_price_usd,
        )
    names = target if isinstance(target, list) else [target]
    if scope == "decklist":
        return await _spellbook.find_combos_in_decklist(names)
    if scope == "near_miss":
        return await _spellbook.find_near_misses(names, missing_max=missing_max, color_identity=color_identity)
    return {"error": "invalid_scope", "valid": ["card", "colors", "decklist", "near_miss"]}


@mcp.tool()
async def get_combo_details(combo_id: str) -> dict:
    """Get full steps, prerequisites, and results for a Commander Spellbook combo by ID."""
    return await _spellbook.get_combo_details(combo_id)


# ── Rules & Oracle ──────────────────────────────────────────────────────────────

@mcp.tool()
async def search_comprehensive_rules(
    query: Annotated[str, "Search text"],
    section: Annotated[str | None, "Section prefix to narrow results, e.g. '702' for keyword abilities"] = None,
) -> list[dict]:
    """Full-text search of the Magic Comprehensive Rules."""
    return await _rulings.search_comprehensive_rules(query, section=section)


@mcp.tool()
async def get_rule(
    rule_number: Annotated[str, "Rule number, e.g. '702.19a' or '601.2'"],
) -> dict:
    """Look up a Comprehensive Rules entry by number; also returns the parent rule."""
    return await _rulings.get_rule(rule_number)


@mcp.tool()
async def get_keyword_definition(
    keyword: Annotated[str, "Keyword ability or action, e.g. 'cascade', 'myriad', 'protection'"],
) -> dict:
    """Return the Comprehensive Rules definition for a keyword ability or action."""
    return await _rulings.get_keyword_definition(keyword)


@mcp.tool()
async def get_card_rulings(
    card_name: str,
    limit: Annotated[int, "Maximum number of most-recent rulings to return; 0 for all"] = 5,
) -> dict:
    """Return official Scryfall rulings for a card, most recent first."""
    return await _rulings.get_card_rulings(card_name, limit=limit)


@mcp.tool()
async def explain_interaction(
    card_a: Annotated[str, "First card name"],
    card_b: Annotated[str, "Second card name"],
    scenario: Annotated[str | None, "Optional description of the specific interaction to focus on"] = None,
) -> dict:
    """Assemble oracle text, rulings, and relevant CR sections for two cards as a reasoning context bundle."""
    return await _rulings.explain_interaction(card_a, card_b, scenario=scenario)


# ── Admin ───────────────────────────────────────────────────────────────────────

@mcp.tool()
async def admin_action(
    action: Annotated[
        Literal["refresh_rules", "rules_cache_status", "refresh_moxfield_credentials"],
        "Admin action: refresh Comprehensive Rules cache, check rules cache status, or re-authenticate Moxfield",
    ],
) -> dict:
    """Perform an administrative action: refresh caches or re-authenticate Moxfield."""
    if action == "refresh_rules":
        return await _rulings.refresh_rules()
    if action == "rules_cache_status":
        return _rulings.cache_status()
    if action == "refresh_moxfield_credentials":
        try:
            creds = await _cred_manager.login()
            return {"status": "success", "expires_at": creds.expires_at.isoformat()}
        except Exception as e:
            return {"error": "moxfield_auth_failed", "reason": str(e)}
    return {"error": "unknown_action", "action": action}


def main():
    import os
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
