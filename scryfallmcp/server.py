# scryfallmcp/server.py
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
# Share the same ScryfallClient instance so deck enrichment reuses the HTTP connection pool
# and the rate-limit semaphore in get_cards_bulk is shared across all callers.
_moxfield = MoxfieldClient(credential_manager=_cred_manager, scryfall_client=_scryfall)
_edhrec = EDHRecClient()
_spellbook = CommanderSpellbookClient()
_rulings = RulingsClient(scryfall_client=_scryfall)


# ── Scryfall Tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def search_cards(query: str, page: int = 1) -> list[dict] | dict:
    """Search for Magic: The Gathering cards using full Scryfall syntax.

    Examples: 't:dragon c:r', 'o:"draw a card" cmc<=2', 'is:commander identity:gruul'
    """
    return await _scryfall.search_cards(query, page=page)


@mcp.tool()
async def get_card_by_name(name: str, fuzzy: bool = True) -> dict:
    """Fetch a single card by name. Set fuzzy=False for exact matching."""
    return await _scryfall.get_card_by_name(name, fuzzy=fuzzy)


@mcp.tool()
async def get_card_by_set(set_code: str, collector_number: str) -> dict:
    """Fetch a specific card printing by set code and collector number.

    Example: set_code='mh3', collector_number='237'
    """
    return await _scryfall.get_card_by_set(set_code, collector_number)


@mcp.tool()
async def get_cards_bulk(names: list[str]) -> list[dict]:
    """Fetch multiple cards by name in one call. Handles batching automatically."""
    return await _scryfall.get_cards_bulk(names)


# ── Moxfield Tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_user_decks(username: str) -> list[dict] | dict:
    """List all decks for a Moxfield user.

    username: the display name / URL slug (e.g. 'johndoe' from moxfield.com/users/johndoe)
    """
    try:
        return await _moxfield.get_user_decks(username)
    except RuntimeError as e:
        return {"error": "moxfield_auth_required", "reason": str(e)}


@mcp.tool()
async def get_deck(deck_id: str, enrich_with_scryfall: bool = True) -> dict:
    """Fetch a Moxfield deck by its public ID.

    Returns full card list with quantities, board breakdown, and (optionally)
    Scryfall card data and price totals.
    """
    try:
        return await _moxfield.get_deck(deck_id, enrich_with_scryfall=enrich_with_scryfall)
    except RuntimeError as e:
        return {"error": "moxfield_auth_required", "reason": str(e)}


@mcp.tool()
async def refresh_moxfield_credentials() -> dict:
    """Manually trigger Moxfield re-authentication via browser login.

    Use this if Moxfield calls are returning authentication errors.
    """
    try:
        creds = await _cred_manager.login()
        return {"status": "success", "expires_at": creds.expires_at.isoformat()}
    except Exception as e:
        return {"error": "moxfield_auth_failed", "reason": str(e)}


# ── EDHREC Tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_commander_recommendations(
    commander_name: str,
    theme: str | None = None,
    budget: str | None = None,
) -> list[dict] | dict:
    """Get card recommendations for a Commander from EDHREC, grouped by category.

    commander_name: full card name, e.g. 'Krenko, Mob Boss'
    theme: optional theme slug, e.g. 'tokens', 'voltron' (use get_commander_themes to list)
    budget: optional filter — 'budget' or 'expensive'
    """
    return await _edhrec.get_commander_recommendations(commander_name, theme=theme, budget=budget)


@mcp.tool()
async def get_commander_themes(commander_name: str) -> list[dict] | dict:
    """List available themes/strategies for a Commander on EDHREC.

    Returns [{theme, slug, deck_count}]. Feed slug back to get_commander_recommendations.
    """
    return await _edhrec.get_commander_themes(commander_name)


@mcp.tool()
async def get_card_top_commanders(card_name: str) -> list[dict] | dict:
    """Find which Commanders most frequently run a given card (reverse lookup via EDHREC)."""
    return await _edhrec.get_card_top_commanders(card_name)


@mcp.tool()
async def get_average_deck(
    commander_name: str, theme: str | None = None
) -> list[dict] | dict:
    """Return the statistical average 99-card decklist for a Commander from EDHREC.

    Useful as a baseline — 'what does a generic version of this deck look like?'
    """
    return await _edhrec.get_average_deck(commander_name, theme=theme)


@mcp.tool()
async def get_budget_alternatives(
    card_name: str, max_price_usd: float | None = None
) -> list[dict] | dict:
    """Find functionally similar, cheaper alternatives to a card via EDHREC similarity data."""
    return await _edhrec.get_budget_alternatives(card_name, max_price_usd=max_price_usd)


# ── Commander Spellbook Tools ──────────────────────────────────────────────────

@mcp.tool()
async def find_combos_with_card(card_name: str) -> list[dict] | dict:
    """Find all combos in the Commander Spellbook database that include a specific card."""
    return await _spellbook.find_combos_with_card(card_name)


@mcp.tool()
async def find_combos_in_colors(
    color_identity: str,
    max_pieces: int | None = None,
    results_include: str | None = None,
    max_price_usd: float | None = None,
) -> list[dict] | dict:
    """Find combos legal in a given color identity (e.g. 'WUB', 'R', 'WUBRG').

    max_pieces: filter to combos with at most N cards
    results_include: filter by effect name, e.g. 'infinite mana'
    max_price_usd: filter by max total combo price
    """
    return await _spellbook.find_combos_in_colors(
        color_identity,
        max_pieces=max_pieces,
        results_include=results_include,
        max_price_usd=max_price_usd,
    )


@mcp.tool()
async def find_combos_in_decklist(card_names: list[str]) -> list[dict]:
    """Detect combos where every piece is already in the provided card list.

    Always run this when a user shares a decklist — catches both intentional and forgotten combos.
    """
    return await _spellbook.find_combos_in_decklist(card_names)


@mcp.tool()
async def find_near_misses(
    card_names: list[str],
    missing_max: int = 1,
    color_identity: str | None = None,
) -> list[dict]:
    """Find combos where the deck is short by at most `missing_max` pieces.

    Powers suggestions like 'adding X completes a two-card combo already in your deck.'
    Each result includes a missing_pieces field listing what to add.
    """
    return await _spellbook.find_near_misses(
        card_names, missing_max=missing_max, color_identity=color_identity
    )


@mcp.tool()
async def get_combo_details(combo_id: str) -> dict:
    """Get full details for a Commander Spellbook combo by ID (steps, prerequisites, results)."""
    return await _spellbook.get_combo_details(combo_id)


# ── Rulings & Oracle Tools ─────────────────────────────────────────────────────

@mcp.tool()
async def search_comprehensive_rules(query: str, section: str | None = None) -> list[dict]:
    """Search the Magic Comprehensive Rules for a query string.

    section: optional section prefix to narrow results, e.g. '702' for keyword abilities
    Returns [{rule, text}] sorted by rule number.
    """
    return await _rulings.search_comprehensive_rules(query, section=section)


@mcp.tool()
async def get_rule(rule_number: str) -> dict:
    """Look up a specific Comprehensive Rules entry by number (e.g. '702.19a', '601.2').

    Also returns the parent rule for context.
    """
    return await _rulings.get_rule(rule_number)


@mcp.tool()
async def get_keyword_definition(keyword: str) -> dict:
    """Return the Comprehensive Rules definition for a keyword ability or action.

    Examples: 'cascade', 'myriad', 'party', 'protection'
    """
    return await _rulings.get_keyword_definition(keyword)


@mcp.tool()
async def get_card_rulings(card_name: str) -> dict:
    """Return official Scryfall rulings for a card with their publication dates."""
    return await _rulings.get_card_rulings(card_name)


@mcp.tool()
async def explain_interaction(
    card_a: str, card_b: str, scenario: str | None = None
) -> dict:
    """Assemble oracle text, rulings, and relevant CR sections for two cards.

    Returns a context bundle — does not itself answer; provides what's needed to reason correctly.
    scenario: optional description of the specific interaction to focus on
    """
    return await _rulings.explain_interaction(card_a, card_b, scenario=scenario)


@mcp.tool()
async def refresh_comprehensive_rules() -> dict:
    """Clear the cached Comprehensive Rules and force a re-fetch on next use.

    Useful after a new set release when rules are updated.
    """
    return await _rulings.refresh_rules()


def main():
    import os
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
