import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
from scryfallmcp.moxfield.auth import Credentials
from scryfallmcp.moxfield.client import MoxfieldClient, _MAX_QUERY_LEN

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
    mock_scryfall = MagicMock()
    mock_scryfall.get_cards_bulk = AsyncMock()
    return MoxfieldClient(
        credential_manager=mock_creds,
        scryfall_client=mock_scryfall,
        http_client=httpx.AsyncClient(),
    )

@respx.mock
async def test_get_user_decks_returns_list(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(return_value=httpx.Response(200, json={
        "data": [
            {"publicId": "deck1", "name": "Mono-Red Burn", "format": "modern",
             "createdByUser": {"userName": "johndoe"}, "colorIdentity": ["R"],
             "lastUpdatedAtUtc": "2026-01-01T00:00:00Z"},
            {"publicId": "deck2", "name": "Control", "format": "legacy",
             "createdByUser": {"userName": "johndoe"}, "colorIdentity": ["U"],
             "lastUpdatedAtUtc": "2026-01-02T00:00:00Z"},
        ]
    }))
    result = await client.get_user_decks("johndoe")
    assert len(result) == 2
    assert result[0]["id"] == "deck1"
    assert result[0]["name"] == "Mono-Red Burn"
    assert result[0]["format"] == "modern"
    assert result[0]["author"] == "johndoe"


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
async def test_find_deck_returns_matching_decks(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(return_value=httpx.Response(200, json={
        "data": [
            {"publicId": "deck1", "name": "Mono-Red Burn", "format": "modern", "lastUpdatedAtUtc": "2026-01-01T00:00:00Z"},
            {"publicId": "deck2", "name": "Blue Control", "format": "legacy", "lastUpdatedAtUtc": "2026-01-02T00:00:00Z"},
            {"publicId": "deck3", "name": "Red-Green Ramp", "format": "standard", "lastUpdatedAtUtc": "2026-01-03T00:00:00Z"},
        ]
    }))
    result = await client.find_deck("red", "johndoe")
    assert len(result) == 2
    names = {d["name"] for d in result}
    assert "Mono-Red Burn" in names
    assert "Red-Green Ramp" in names
    assert "Blue Control" not in names


@respx.mock
async def test_find_deck_no_match_returns_empty(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(return_value=httpx.Response(200, json={
        "data": [
            {"publicId": "deck1", "name": "Mono-Red Burn", "format": "modern", "lastUpdatedAtUtc": "2026-01-01T00:00:00Z"},
        ]
    }))
    result = await client.find_deck("eldrazi", "johndoe")
    assert result == []


@respx.mock
async def test_get_deck_with_enrichment(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )

    scryfall_data = [
        {"name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
         "oracle_text": "Deal 3 damage.", "color_identity": ["R"],
         "cmc": 1.0, "keywords": [], "commander_legal": True,
         "set": "leb", "rarity": "common", "price_usd": "0.50"},
        {"name": "Goblin Guide", "mana_cost": "{R}", "type_line": "Creature — Goblin Scout",
         "oracle_text": "Haste.", "color_identity": ["R"],
         "cmc": 1.0, "power": "2", "toughness": "2",
         "keywords": ["Haste"], "commander_legal": True,
         "set": "zen", "rarity": "rare", "price_usd": "5.00"},
    ]

    client._scryfall.get_cards_bulk.return_value = scryfall_data
    result = await client.get_deck("deck1", enrich_with_scryfall="lean")

    mainboard = result["boards"]["mainboard"]
    bolt = next(c for c in mainboard if c["name"] == "Lightning Bolt")
    assert bolt["mana_cost"] == "{R}"
    assert bolt["oracle_text"] == "Deal 3 damage."
    assert bolt["price_usd"] == "0.50"
    assert bolt["name"] == "Lightning Bolt"  # name not overwritten
    guide = next(c for c in mainboard if c["name"] == "Goblin Guide")
    assert guide["mana_cost"] == "{R}"
    # 4 × $0.50 (Lightning Bolt) + 4 × $5.00 (Goblin Guide) = $22.00
    assert result["price_total_usd"] == "22.00"


@respx.mock
async def test_search_decks_returns_parsed_results(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(return_value=httpx.Response(200, json={
        "pageNumber": 1,
        "pageSize": 20,
        "totalResults": 2,
        "totalPages": 1,
        "data": [
            {"publicId": "abc123", "name": "Elfball", "format": "commander",
             "createdByUser": {"userName": "elfmaster"},
             "publicUrl": "https://moxfield.com/decks/abc123",
             "colorIdentity": ["G"], "likeCount": 42, "viewCount": 900,
             "lastUpdatedAtUtc": "2026-02-01T00:00:00Z"},
            {"publicId": "def456", "name": "Selesnya Elves", "format": "commander",
             "createdByUser": {"userName": "gwplayer"},
             "publicUrl": "https://moxfield.com/decks/def456",
             "colorIdentity": ["G", "W"], "likeCount": 7, "viewCount": 100,
             "lastUpdatedAtUtc": "2026-02-02T00:00:00Z"},
        ],
    }))
    result = await client.search_decks("elves", fmt="commander")
    assert result["total_results"] == 2
    assert result["total_pages"] == 1
    assert len(result["decks"]) == 2
    first = result["decks"][0]
    assert first["id"] == "abc123"
    assert first["name"] == "Elfball"
    assert first["url"] == "https://moxfield.com/decks/abc123"
    assert first["author"] == "elfmaster"
    assert first["likes"] == 42


@respx.mock
async def test_get_deck_accepts_full_url(client):
    route = respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )
    result = await client.get_deck(
        "https://moxfield.com/decks/deck1", enrich_with_scryfall=False
    )
    assert route.called
    assert result["id"] == "deck1"


async def test_get_deck_rejects_invalid_id(client):
    with respx.mock:
        route = respx.get(url__regex=rf"{MOXFIELD_API}/v2/decks/all/.*")
        result = await client.get_deck("foo/../bar", enrich_with_scryfall=False)
        assert result == {"error": "invalid deck id", "deck_id": "foo/../bar"}
        assert not route.called


@respx.mock
async def test_get_deck_works_without_credentials():
    """With no valid credentials, public deck retrieval still succeeds and sends no auth."""
    no_creds = MagicMock()
    no_creds.get_valid_credentials = AsyncMock(
        side_effect=RuntimeError("Moxfield credentials not found.")
    )
    mock_scryfall = MagicMock()
    mock_scryfall.get_cards_bulk = AsyncMock()
    unauth_client = MoxfieldClient(
        credential_manager=no_creds,
        scryfall_client=mock_scryfall,
        http_client=httpx.AsyncClient(),
    )

    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )
    result = await unauth_client.get_deck("deck1", enrich_with_scryfall=False)
    assert result["id"] == "deck1"

    sent_headers = respx.calls.last.request.headers
    assert "authorization" not in sent_headers
    assert "cookie" not in sent_headers


# --- search_decks wire params ------------------------------------------------
#
# Regression for the bug where search_decks sent `q=`, which /v2/decks/search
# silently ignores, returning the unfiltered recent-decks feed. The endpoint's
# real filter param is `deckName=` (verified live: a nonsense deckName returns
# totalResults 0, while `q` never changes the result set).

_EMPTY_SEARCH = {"totalResults": 0, "pageNumber": 1, "totalPages": 0, "data": []}


def _mock_search():
    return respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(
        return_value=httpx.Response(200, json=_EMPTY_SEARCH)
    )


@respx.mock
async def test_search_decks_sends_deckname_not_q(client):
    _mock_search()
    await client.search_decks("atraxa")
    params = respx.calls.last.request.url.params
    assert params["deckName"] == "atraxa"
    # `q` is the param the endpoint ignores - it must not be sent at all
    assert "q" not in params


@respx.mock
async def test_search_decks_sends_paging(client):
    _mock_search()
    await client.search_decks("atraxa", page=3, page_size=5)
    params = respx.calls.last.request.url.params
    assert params["pageNumber"] == "3"
    assert params["pageSize"] == "5"


@respx.mock
async def test_search_decks_omits_optional_filters_when_unset(client):
    _mock_search()
    await client.search_decks("atraxa")
    params = respx.calls.last.request.url.params
    for key in ("fmt", "sortType", "sortDirection"):
        assert key not in params


@respx.mock
async def test_search_decks_forwards_valid_filters(client):
    _mock_search()
    await client.search_decks(
        "atraxa", fmt="commander", sort_type="views", sort_direction="ascending"
    )
    params = respx.calls.last.request.url.params
    assert params["fmt"] == "commander"
    assert params["sortType"] == "views"
    assert params["sortDirection"] == "ascending"


@respx.mock
async def test_search_decks_rejects_unknown_sort_values(client):
    """Unknown sort values are dropped, not forwarded - an unrecognised value
    makes Moxfield fall back to the unfiltered feed, which is this bug's shape."""
    _mock_search()
    await client.search_decks("atraxa", sort_type="bogus", sort_direction="sideways")
    params = respx.calls.last.request.url.params
    assert "sortType" not in params
    assert "sortDirection" not in params


@respx.mock
async def test_search_decks_rejects_malformed_format(client):
    """fmt is bounded by shape (letters only, length-capped) rather than by an
    allowlist - Moxfield's format vocabulary is larger than we could verify."""
    _mock_search()
    for bad in ("not-a-real-format", "commander; drop", "x" * 100, "fmt=1&evil=2"):
        _mock_search()
        await client.search_decks("atraxa", fmt=bad)
        assert "fmt" not in respx.calls.last.request.url.params


@respx.mock
async def test_search_decks_accepts_wellformed_format(client):
    _mock_search()
    await client.search_decks("atraxa", fmt="oathbreaker")
    assert respx.calls.last.request.url.params["fmt"] == "oathbreaker"


@respx.mock
async def test_search_decks_clamps_query_length(client):
    _mock_search()
    await client.search_decks("z" * 5000)
    assert len(respx.calls.last.request.url.params["deckName"]) == _MAX_QUERY_LEN


@respx.mock
async def test_get_user_decks_sends_author_filter(client):
    """get_user_decks already used the correct param - guard it stays correct."""
    _mock_search()
    await client.get_user_decks("Darrknar")
    params = respx.calls.last.request.url.params
    assert params["authorUserNames"] == "Darrknar"


# --- Double-faced cards in deck enrichment ------------------------------------
# Moxfield names DFCs with the full "A // B" form (confirmed on live decks, e.g.
# "Jin-Gitaxias // The Great Synthesis"). Scryfall answers with that same joined
# name, but a caller or another source may use the front face alone — so the
# index has to accept both forms or the card silently loses all enrichment.

_DFC_DECK_RESPONSE = {
    "id": "dfc1",
    "name": "Phyrexian Praetors",
    "format": "commander",
    "description": "",
    "createdByUser": {"userName": "johndoe"},
    "mainboard": {
        "Jin-Gitaxias // The Great Synthesis": {
            "quantity": 1,
            "card": {"name": "Jin-Gitaxias // The Great Synthesis"},
        },
        # The front-face-only form, to prove the index works in both directions
        "Fell the Profane": {"quantity": 2, "card": {"name": "Fell the Profane"}},
    },
    "sideboard": {},
    "commanders": {},
    "companions": {},
}

_DFC_SCRYFALL_DATA = [
    {"name": "Jin-Gitaxias // The Great Synthesis", "mana_cost": "{5}{U}",
     "type_line": "Legendary Creature — Phyrexian Praetor // Enchantment — Saga",
     "oracle_text": "Whenever you cast a spell...\n//\nDraw cards.",
     "color_identity": ["U"], "cmc": 6.0, "keywords": [], "layout": "transform",
     "commander_legal": True, "set": "mom", "rarity": "mythic", "price_usd": "10.00"},
    {"name": "Fell the Profane // Fell Mire", "mana_cost": "{2}{B}{B}",
     "type_line": "Instant // Land",
     "oracle_text": "Destroy target creature.\n//\nAs this land enters...",
     "color_identity": ["B"], "cmc": 4.0, "keywords": [], "layout": "modal_dfc",
     "commander_legal": True, "set": "mh3", "rarity": "uncommon", "price_usd": "4.00"},
]


@respx.mock
async def test_enrichment_matches_double_faced_names(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/dfc1").mock(
        return_value=httpx.Response(200, json=_DFC_DECK_RESPONSE)
    )
    client._scryfall.get_cards_bulk.return_value = _DFC_SCRYFALL_DATA
    result = await client.get_deck("dfc1", enrich_with_scryfall="lean")

    mainboard = result["boards"]["mainboard"]
    jin = next(c for c in mainboard if c["name"].startswith("Jin-Gitaxias"))
    assert jin["oracle_text"] is not None
    assert jin["type_line"] == (
        "Legendary Creature — Phyrexian Praetor // Enchantment — Saga"
    )
    assert jin["layout"] == "transform"

    # Requested by front face, answered by Scryfall with the joined name
    fell = next(c for c in mainboard if c["name"] == "Fell the Profane")
    assert fell["type_line"] == "Instant // Land"
    assert fell["oracle_text"] is not None

    # 1 × $10.00 + 2 × $4.00 — both DFCs contributed instead of being dropped
    assert result["price_total_usd"] == "18.00"


@respx.mock
async def test_enrichment_skips_not_found_entries(client):
    """A `card not found` entry must not paste an `error` key into the deck."""
    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )
    client._scryfall.get_cards_bulk.return_value = [
        {"name": "Lightning Bolt", "price_usd": "0.50", "oracle_text": "Deal 3 damage."},
        {"name": "Goblin Guide", "error": "card not found"},
    ]
    result = await client.get_deck("deck1", enrich_with_scryfall="lean")

    mainboard = result["boards"]["mainboard"]
    guide = next(c for c in mainboard if c["name"] == "Goblin Guide")
    assert "error" not in guide
    assert result["price_total_usd"] == "2.00"  # 4 × $0.50, the miss adds nothing


# --- Cloudflare diagnostics ---------------------------------------------------


@respx.mock
async def test_http_error_carries_cloudflare_signal(client):
    """A bare "HTTP 403" cannot distinguish an edge block from a Moxfield error."""
    respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(
        return_value=httpx.Response(
            403,
            headers={
                "cf-ray": "8f2c1a0000abcdef-SYD",
                "cf-mitigated": "challenge",
                "server": "cloudflare",
            },
            text="<!DOCTYPE html><html>Attention Required! | Cloudflare</html>",
        )
    )
    with pytest.raises(Exception) as exc:
        await client.search_decks("atraxa")

    msg = str(exc.value)
    assert "HTTP 403" in msg
    assert "cf-mitigated=challenge" in msg
    assert "cf-ray=8f2c1a0000abcdef-SYD" in msg
    assert "server=cloudflare" in msg
    assert "Attention Required" in msg


@respx.mock
async def test_http_error_body_is_truncated(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(
        return_value=httpx.Response(403, text="x" * 5000)
    )
    with pytest.raises(Exception) as exc:
        await client.search_decks("atraxa")
    assert len(str(exc.value)) < 400


@respx.mock
async def test_http_error_never_echoes_request_headers(client):
    """The Bearer token and session cookies must not reach an error message."""
    respx.get(f"{MOXFIELD_API}/v2/decks/search").mock(
        return_value=httpx.Response(403, text="blocked")
    )
    with pytest.raises(Exception) as exc:
        await client.search_decks("atraxa")
    msg = str(exc.value)
    assert "testtoken123" not in msg
    assert "_moxfield_session" not in msg


async def test_close_supports_curl_cffi_session():
    """curl_cffi's AsyncSession has close(), not aclose() — closing must not raise."""
    curl_cffi_shaped = MagicMock(spec=["get", "close"])
    curl_cffi_shaped.close = AsyncMock()
    mock_scryfall = MagicMock()
    mock_scryfall.close = AsyncMock()

    client = MoxfieldClient(
        credential_manager=MagicMock(),
        scryfall_client=mock_scryfall,
        http_client=curl_cffi_shaped,
    )
    await client.close()

    curl_cffi_shaped.close.assert_awaited_once()
    mock_scryfall.close.assert_awaited_once()


async def test_close_supports_httpx_client():
    httpx_shaped = MagicMock(spec=["get", "aclose"])
    httpx_shaped.aclose = AsyncMock()
    mock_scryfall = MagicMock()
    mock_scryfall.close = AsyncMock()

    client = MoxfieldClient(
        credential_manager=MagicMock(),
        scryfall_client=mock_scryfall,
        http_client=httpx_shaped,
    )
    await client.close()

    httpx_shaped.aclose.assert_awaited_once()
