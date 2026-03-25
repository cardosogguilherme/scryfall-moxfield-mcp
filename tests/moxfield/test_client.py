import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from scryfallmcp.moxfield.auth import Credentials
from scryfallmcp.moxfield.client import MoxfieldClient

MOXFIELD_API = "https://api2.moxfield.com"

@pytest.fixture
def mock_creds():
    creds = Credentials(
        token="Bearer testtoken123",
        cookies={"_moxfield_session": "abc123"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    mock_manager = MagicMock()
    mock_manager.get_valid_credentials = AsyncMock(return_value=creds)
    return mock_manager

@pytest.fixture
def client(mock_creds):
    return MoxfieldClient(credential_manager=mock_creds)

@respx.mock
async def test_get_user_decks_returns_list(client):
    respx.get(f"{MOXFIELD_API}/v2/users/johndoe/decks").mock(return_value=httpx.Response(200, json={
        "data": [
            {"publicId": "deck1", "name": "Mono-Red Burn", "format": "modern", "lastUpdatedAtUtc": "2026-01-01T00:00:00Z"},
            {"publicId": "deck2", "name": "Control", "format": "legacy", "lastUpdatedAtUtc": "2026-01-02T00:00:00Z"},
        ]
    }))
    result = await client.get_user_decks("johndoe")
    assert len(result) == 2
    assert result[0]["id"] == "deck1"
    assert result[0]["name"] == "Mono-Red Burn"
    assert result[0]["format"] == "modern"


MOCK_DECK_RESPONSE = {
    "id": "deck1",
    "name": "Mono-Red Burn",
    "format": "modern",
    "description": "Fast red deck",
    "createdByUser": {"userName": "johndoe"},
    "mainboard": {
        "Lightning Bolt": {"quantity": 4, "card": {"name": "Lightning Bolt"}},
        "Goblin Guide": {"quantity": 4, "card": {"name": "Goblin Guide"}},
    },
    "sideboard": {},
    "commanders": {},
    "companions": {},
}

@respx.mock
async def test_get_deck_no_enrichment(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )
    result = await client.get_deck("deck1", enrich_with_scryfall=False)
    assert result["id"] == "deck1"
    assert result["name"] == "Mono-Red Burn"
    assert result["author"] == "johndoe"
    mainboard = result["boards"]["mainboard"]
    assert len(mainboard) == 2
    bolt = next(c for c in mainboard if c["name"] == "Lightning Bolt")
    assert bolt["quantity"] == 4


@respx.mock
async def test_get_deck_404_returns_error(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/notexist").mock(
        return_value=httpx.Response(404, json={"message": "Not found"})
    )
    result = await client.get_deck("notexist", enrich_with_scryfall=False)
    assert result == {"error": "deck not found", "deck_id": "notexist"}


@respx.mock
async def test_get_deck_401_triggers_reauth_and_retries(client, mock_creds):
    """On 401, the client calls login() and retries once with fresh credentials."""
    fresh_creds = Credentials(
        token="Bearer freshtoken",
        cookies={"_moxfield_session": "freshed"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    mock_creds.login = AsyncMock(return_value=fresh_creds)

    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(401, json={"message": "Unauthorized"})
        return httpx.Response(200, json=MOCK_DECK_RESPONSE)

    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(side_effect=handler)
    result = await client.get_deck("deck1", enrich_with_scryfall=False)
    assert call_count == 2
    mock_creds.login.assert_called_once()
    assert result["name"] == "Mono-Red Burn"


@respx.mock
async def test_get_deck_with_enrichment(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )

    scryfall_data = [
        {"name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
         "oracle_text": "Deal 3 damage.", "colors": ["R"], "cmc": 1.0,
         "legalities": {}, "set": "leb", "image_uris": {}, "prices": {"usd": "0.50"},
         "collector_number": "61"},
        {"name": "Goblin Guide", "mana_cost": "{R}", "type_line": "Creature",
         "oracle_text": "Haste.", "colors": ["R"], "cmc": 1.0,
         "legalities": {}, "set": "zen", "image_uris": {}, "prices": {"usd": "5.00"},
         "collector_number": "134"},
    ]

    with patch(
        "scryfallmcp.moxfield.client.ScryfallClient.get_cards_bulk",
        new_callable=AsyncMock,
        return_value=scryfall_data,
    ):
        result = await client.get_deck("deck1", enrich_with_scryfall=True)

    mainboard = result["boards"]["mainboard"]
    bolt = next(c for c in mainboard if c["name"] == "Lightning Bolt")
    assert bolt["mana_cost"] == "{R}"
    assert bolt["oracle_text"] == "Deal 3 damage."
    assert bolt["prices"] == {"usd": "0.50"}
    # 4 × $0.50 (Lightning Bolt) + 4 × $5.00 (Goblin Guide) = $22.00
    assert result["price_total_usd"] == "22.00"
