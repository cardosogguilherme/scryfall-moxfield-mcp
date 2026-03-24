import pytest
import respx
import httpx
from scryfallmcp.scryfall.client import ScryfallClient

SCRYFALL_BASE = "https://api.scryfall.com"


@pytest.fixture
async def client():
    async with ScryfallClient() as c:
        yield c


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


@respx.mock
async def test_get_card_by_name_fuzzy(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json={
        "name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
        "oracle_text": "Deal 3.", "colors": ["R"], "cmc": 1.0,
        "legalities": {}, "set": "leb", "image_uris": {}, "prices": {},
    }))
    result = await client.get_card_by_name("ligntning bolt", fuzzy=True)
    assert result["name"] == "Lightning Bolt"


@respx.mock
async def test_get_card_by_name_not_found(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(404, json={
        "object": "error", "details": "Not found."
    }))
    result = await client.get_card_by_name("xyzxyzxyz")
    assert result == {"error": "card not found", "query": "xyzxyzxyz"}


@respx.mock
async def test_get_card_by_name_exact(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json={
        "name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
        "oracle_text": "Deal 3.", "colors": ["R"], "cmc": 1.0,
        "legalities": {}, "set": "leb", "image_uris": {}, "prices": {},
    }))
    result = await client.get_card_by_name("Lightning Bolt", fuzzy=False)
    assert result["name"] == "Lightning Bolt"


@respx.mock
async def test_get_card_by_set(client):
    respx.get(f"{SCRYFALL_BASE}/cards/leb/1").mock(return_value=httpx.Response(200, json={
        "name": "Black Lotus", "mana_cost": "{0}", "type_line": "Artifact",
        "oracle_text": "Tap, Sacrifice Black Lotus: Add three mana.", "colors": [],
        "cmc": 0.0, "legalities": {}, "set": "leb", "image_uris": {}, "prices": {},
    }))
    result = await client.get_card_by_set("leb", "1")
    assert result["name"] == "Black Lotus"


@respx.mock
async def test_get_cards_bulk_retries_on_429(client):
    """Verifies that a 429 on the collection endpoint triggers a retry."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"object": "error", "code": "too_many_requests"})
        return httpx.Response(200, json={"data": [
            {"name": "Sol Ring", "mana_cost": "{1}", "type_line": "Artifact",
             "oracle_text": "", "colors": [], "cmc": 1.0, "legalities": {},
             "set": "lea", "image_uris": {}, "prices": {}}
        ]})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    result = await client.get_cards_bulk(["Sol Ring"])
    assert call_count == 2  # first call 429, second succeeds
    assert result[0]["name"] == "Sol Ring"


@respx.mock
async def test_get_cards_bulk_single_chunk(client):
    names = ["Lightning Bolt", "Counterspell"]
    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(return_value=httpx.Response(200, json={
        "data": [
            {"name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
             "oracle_text": "", "colors": ["R"], "cmc": 1.0, "legalities": {},
             "set": "leb", "image_uris": {}, "prices": {}},
            {"name": "Counterspell", "mana_cost": "{U}{U}", "type_line": "Instant",
             "oracle_text": "", "colors": ["U"], "cmc": 2.0, "legalities": {},
             "set": "leb", "image_uris": {}, "prices": {}},
        ]
    }))
    result = await client.get_cards_bulk(names)
    assert len(result) == 2
    assert {c["name"] for c in result} == {"Lightning Bolt", "Counterspell"}


@respx.mock
async def test_get_cards_bulk_chunks_at_75(client):
    """Verifies that 76 names produce exactly 2 API calls."""
    names = [f"Card {i}" for i in range(76)]
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": []})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    await client.get_cards_bulk(names)
    assert call_count == 2
