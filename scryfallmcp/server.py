# scryfallmcp/server.py
from mcp.server.fastmcp import FastMCP
from scryfallmcp.scryfall.client import ScryfallClient
from scryfallmcp.moxfield.client import MoxfieldClient
from scryfallmcp.moxfield.auth import CredentialManager

mcp = FastMCP("scryfallmcp")

_scryfall = ScryfallClient()
_cred_manager = CredentialManager()
_moxfield = MoxfieldClient(credential_manager=_cred_manager, scryfall_client=_scryfall)


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
async def get_user_decks(username: str) -> list[dict]:
    """List all decks for a Moxfield user.

    username: the display name / URL slug (e.g. 'johndoe' from moxfield.com/users/johndoe)
    """
    return await _moxfield.get_user_decks(username)


@mcp.tool()
async def get_deck(deck_id: str, enrich_with_scryfall: bool = True) -> dict:
    """Fetch a Moxfield deck by its public ID.

    Returns full card list with quantities, board breakdown, and (optionally)
    Scryfall card data and price totals.
    """
    return await _moxfield.get_deck(deck_id, enrich_with_scryfall=enrich_with_scryfall)


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


def main():
    mcp.run()


if __name__ == "__main__":
    main()
