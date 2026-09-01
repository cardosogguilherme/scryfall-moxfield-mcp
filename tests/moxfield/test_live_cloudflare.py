"""Opt-in live checks against Moxfield's real endpoints.

Deselected by default (`-m "not live"` in pyproject) — they need network access
and they exercise the one thing the offline suite structurally cannot: whether
Cloudflare lets *this* host through. Run them from a machine or a deploy you
want to test the egress of:

    pytest tests/moxfield/test_live_cloudflare.py -m live -v

A 403 here is the signal to read `cf-ray` / `cf-mitigated` off the raised error.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from scryfallmcp.moxfield.client import MoxfieldClient

pytestmark = pytest.mark.live

# A long-lived public deck. If it is ever deleted the test 404s rather than
# 403s, which is still a clear signal that Cloudflare was not the problem.
STABLE_PUBLIC_DECK_ID = "WPVM1b8WUEuMQ0PbiMEK5A"


@pytest.fixture
async def unauth_client():
    """No credentials — the path the cloud deploy actually takes."""
    no_creds = MagicMock()
    no_creds.get_valid_credentials = AsyncMock(
        side_effect=RuntimeError("Moxfield credentials not found.")
    )
    client = MoxfieldClient(credential_manager=no_creds)
    try:
        yield client
    finally:
        await client.close()


async def test_live_search_decks_is_reachable(unauth_client):
    result = await unauth_client.search_decks("atraxa", page_size=3)
    assert result["decks"], "search returned no decks"
    assert any("atraxa" in (d["name"] or "").lower() for d in result["decks"])


async def test_live_get_deck_is_reachable(unauth_client):
    deck = await unauth_client.get_deck(
        STABLE_PUBLIC_DECK_ID, enrich_with_scryfall=False
    )
    assert "error" not in deck, deck
    assert deck["boards"]["mainboard"]


async def test_live_double_faced_cards_are_enriched(unauth_client):
    """The deck above contains two transform cards named "A // B"."""
    deck = await unauth_client.get_deck(STABLE_PUBLIC_DECK_ID)
    dfcs = [c for c in deck["boards"]["mainboard"] if " // " in (c["name"] or "")]
    assert dfcs, "fixture deck no longer contains a double-faced card"
    for card in dfcs:
        assert card.get("oracle_text"), f"{card['name']} lost its oracle text"
        assert card.get("type_line"), f"{card['name']} lost its type line"
    assert deck["price_total_usd"] is not None
