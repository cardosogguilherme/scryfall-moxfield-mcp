import pytest
import respx
import httpx
from scryfallmcp.scryfall.client import ScryfallClient

SCRYFALL_BASE = "https://api.scryfall.com"


@pytest.fixture
async def client():
    async with ScryfallClient() as c:
        yield c


def _raw_card(name="Lightning Bolt", **overrides) -> dict:
    """Minimal raw Scryfall card payload."""
    base = {
        "name": name,
        "mana_cost": "{R}",
        "cmc": 1.0,
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "colors": ["R"],
        "color_identity": ["R"],
        "keywords": [],
        "set": "leb",
        "rarity": "common",
        "legalities": {"commander": "legal", "modern": "legal"},
        "prices": {"usd": "0.50", "usd_foil": None},
    }
    base.update(overrides)
    return base


@respx.mock
async def test_search_cards_returns_card_list(client):
    respx.get(f"{SCRYFALL_BASE}/cards/search").mock(return_value=httpx.Response(200, json={
        "data": [_raw_card()],
        "has_more": False,
        "total_cards": 1,
    }))
    result = await client.search_cards("t:instant c:r")
    assert len(result) == 1
    card = result[0]
    assert card["name"] == "Lightning Bolt"
    assert card["mana_cost"] == "{R}"
    assert card["commander_legal"] is True
    assert card["price_usd"] == "0.50"
    assert "legalities" not in card
    assert "prices" not in card
    assert "colors" not in card


@respx.mock
async def test_search_cards_404_returns_error(client):
    respx.get(f"{SCRYFALL_BASE}/cards/search").mock(return_value=httpx.Response(404, json={
        "object": "error", "code": "not_found", "details": "No cards found."
    }))
    result = await client.search_cards("t:nonexistenttype12345")
    assert result == {"error": "card not found", "query": "t:nonexistenttype12345"}


@respx.mock
async def test_get_card_by_name_fuzzy(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json=_raw_card()))
    result = await client.get_card_by_name("ligntning bolt", fuzzy=True)
    assert result["name"] == "Lightning Bolt"
    assert result["commander_legal"] is True
    assert result["price_usd"] == "0.50"


@respx.mock
async def test_get_card_by_name_not_found(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(404, json={
        "object": "error", "details": "Not found."
    }))
    result = await client.get_card_by_name("xyzxyzxyz")
    assert result == {"error": "card not found", "query": "xyzxyzxyz"}


@respx.mock
async def test_get_card_by_name_exact(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json=_raw_card()))
    result = await client.get_card_by_name("Lightning Bolt", fuzzy=False)
    assert result["name"] == "Lightning Bolt"


@respx.mock
async def test_get_card_by_name_include_all_legalities(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json=_raw_card()))
    result = await client.get_card_by_name("Lightning Bolt", include_all_legalities=True)
    assert "legalities" in result
    assert "commander_legal" not in result
    assert result["legalities"]["commander"] == "legal"


@respx.mock
async def test_get_card_by_name_include_all_prices(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json=_raw_card()))
    result = await client.get_card_by_name("Lightning Bolt", include_all_prices=True)
    assert "prices" in result
    assert "price_usd" not in result


@respx.mock
async def test_get_card_by_set(client):
    raw = _raw_card(
        name="Black Lotus", mana_cost="{0}", type_line="Artifact",
        oracle_text="Tap, Sacrifice Black Lotus: Add three mana.",
        colors=[], color_identity=[], cmc=0.0,
        legalities={"commander": "banned"}, prices={"usd": "50000.00"},
        set="leb", rarity="rare",
    )
    respx.get(f"{SCRYFALL_BASE}/cards/leb/1").mock(return_value=httpx.Response(200, json=raw))
    result = await client.get_card_by_set("leb", "1")
    assert result["name"] == "Black Lotus"
    assert result["commander_legal"] is False
    assert result["price_usd"] == "50000.00"


@respx.mock
async def test_null_fields_omitted(client):
    """power/toughness/loyalty should be absent for non-creature cards."""
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json=_raw_card()))
    result = await client.get_card_by_name("Lightning Bolt")
    assert "power" not in result
    assert "toughness" not in result
    assert "loyalty" not in result


@respx.mock
async def test_combat_stats_present_for_creatures(client):
    raw = _raw_card(
        name="Goblin Guide", type_line="Creature — Goblin Scout",
        power="2", toughness="2", loyalty=None,
    )
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json=raw))
    result = await client.get_card_by_name("Goblin Guide")
    assert result["power"] == "2"
    assert result["toughness"] == "2"
    assert "loyalty" not in result


@respx.mock
async def test_get_cards_bulk_retries_on_429(client):
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"object": "error", "code": "too_many_requests"})
        return httpx.Response(200, json={"data": [
            _raw_card(name="Sol Ring", mana_cost="{1}", type_line="Artifact",
                      oracle_text="", colors=[], color_identity=[], cmc=1.0,
                      legalities={"commander": "legal"}, prices={"usd": "1.00"},
                      set="lea", rarity="uncommon")
        ]})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    result = await client.get_cards_bulk(["Sol Ring"])
    assert call_count == 2
    assert result[0]["name"] == "Sol Ring"
    assert result[0]["commander_legal"] is True


@respx.mock
async def test_get_cards_bulk_single_chunk(client):
    names = ["Lightning Bolt", "Counterspell"]
    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(return_value=httpx.Response(200, json={
        "data": [
            _raw_card(name="Lightning Bolt"),
            _raw_card(name="Counterspell", mana_cost="{U}{U}",
                      colors=["U"], color_identity=["U"], cmc=2.0,
                      legalities={"commander": "legal"}, prices={"usd": "1.00"},
                      rarity="common"),
        ]
    }))
    result = await client.get_cards_bulk(names)
    assert len(result) == 2
    assert {c["name"] for c in result} == {"Lightning Bolt", "Counterspell"}
    assert all("commander_legal" in c for c in result)
    assert all("price_usd" in c for c in result)


@respx.mock
async def test_get_cards_bulk_chunks_at_75(client):
    names = [f"Card {i}" for i in range(76)]
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": []})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    await client.get_cards_bulk(names)
    assert call_count == 2
