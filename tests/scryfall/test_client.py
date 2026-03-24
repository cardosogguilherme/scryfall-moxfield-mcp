import pytest
import respx
import httpx
from scryfallmcp.scryfall.client import ScryfallClient

SCRYFALL_BASE = "https://api.scryfall.com"


@pytest.fixture
def client():
    return ScryfallClient()


@respx.mock
async def test_search_cards_returns_card_list(client):
    respx.get(f"{SCRYFALL_BASE}/cards/search").mock(return_value=httpx.Response(200, json={
        "data": [{
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "colors": ["R"],
            "cmc": 1.0,
            "legalities": {"modern": "legal"},
            "set": "leb",
            "image_uris": {"normal": "https://example.com/img.jpg"},
            "prices": {"usd": "0.50"},
        }],
        "has_more": False,
        "total_cards": 1,
    }))
    result = await client.search_cards("t:instant c:r")
    assert len(result) == 1
    assert result[0]["name"] == "Lightning Bolt"
    assert result[0]["mana_cost"] == "{R}"


@respx.mock
async def test_search_cards_404_returns_error(client):
    respx.get(f"{SCRYFALL_BASE}/cards/search").mock(return_value=httpx.Response(404, json={
        "object": "error", "code": "not_found", "details": "No cards found."
    }))
    result = await client.search_cards("t:nonexistenttype12345")
    assert result == {"error": "card not found", "query": "t:nonexistenttype12345"}
