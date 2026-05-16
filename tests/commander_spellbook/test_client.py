import pytest
import respx
import httpx
from scryfallmcp.commander_spellbook.client import CommanderSpellbookClient

SPELLBOOK_BASE = "https://backend.commanderspellbook.com"

MOCK_VARIANT = {
    "id": "abc-123",
    "uses": [
        {"card": {"name": "Thassa's Oracle"}, "quantity": 1, "zoneLocations": ["B"]},
        {"card": {"name": "Demonic Consultation"}, "quantity": 1, "zoneLocations": ["H"]},
    ],
    "produces": [
        {"feature": {"name": "Win the game"}, "quantity": 1}
    ],
    "description": "Cast Demonic Consultation naming a card not in your deck. Cast Thassa's Oracle.",
    "easyPrerequisites": "2UB available",
    "notablePrerequisites": "",
    "identity": "UB",
    "legalities": {"commander": True},
    "prices": {"tcgplayer": "5.00"},
}

MOCK_VARIANTS_RESPONSE = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [MOCK_VARIANT],
}

MOCK_FIND_MY_COMBOS_GET = {
    "csrfToken": "test-csrf-token-12345",
}

MOCK_FIND_MY_COMBOS_RESPONSE = {
    "count": None,
    "next": None,
    "previous": None,
    "results": {
        "identity": "UB",
        "included": [MOCK_VARIANT],
        "almostIncluded": [
            {
                **MOCK_VARIANT,
                "id": "near-miss-1",
                "uses": [
                    {"card": {"name": "Thassa's Oracle"}, "quantity": 1, "zoneLocations": ["B"]},
                    {"card": {"name": "Jace, Wielder of Mysteries"}, "quantity": 1, "zoneLocations": ["B"]},
                    {"card": {"name": "Demonic Consultation"}, "quantity": 1, "zoneLocations": ["H"]},
                ],
            }
        ],
        "almostIncludedByAddingColors": [],
        "almostIncludedByChangingCommanders": [],
        "includedByChangingCommanders": [],
        "almostIncludedByAddingColorsAndChangingCommanders": [],
    },
}


@pytest.fixture
async def client():
    async with CommanderSpellbookClient() as c:
        yield c


@respx.mock
async def test_find_combos_with_card_returns_list(client):
    respx.get(f"{SPELLBOOK_BASE}/variants/").mock(
        return_value=httpx.Response(200, json=MOCK_VARIANTS_RESPONSE)
    )
    result = await client.find_combos_with_card("Thassa's Oracle")
    assert isinstance(result, list)
    assert len(result) == 1
    combo = result[0]
    assert combo["id"] == "abc-123"
    assert "Thassa's Oracle" in combo["pieces"]
    assert "Demonic Consultation" in combo["pieces"]
    assert combo["color_identity"] == "UB"
    assert "Win the game" in combo["produces"]


@respx.mock
async def test_find_combos_in_colors_filters_by_color(client):
    respx.get(f"{SPELLBOOK_BASE}/variants/").mock(
        return_value=httpx.Response(200, json=MOCK_VARIANTS_RESPONSE)
    )
    result = await client.find_combos_in_colors("UB")
    assert isinstance(result, list)


@respx.mock
async def test_find_combos_in_colors_filters_by_max_pieces(client):
    respx.get(f"{SPELLBOOK_BASE}/variants/").mock(
        return_value=httpx.Response(200, json=MOCK_VARIANTS_RESPONSE)
    )
    # MOCK_VARIANT has 2 pieces; max_pieces=1 should exclude it
    result = await client.find_combos_in_colors("UB", max_pieces=1)
    assert result == []


@respx.mock
async def test_find_combos_in_decklist(client):
    respx.get(f"{SPELLBOOK_BASE}/find-my-combos/").mock(
        return_value=httpx.Response(200, json=MOCK_FIND_MY_COMBOS_GET)
    )
    respx.post(f"{SPELLBOOK_BASE}/find-my-combos/").mock(
        return_value=httpx.Response(200, json=MOCK_FIND_MY_COMBOS_RESPONSE)
    )
    result = await client.find_combos_in_decklist(["Thassa's Oracle", "Demonic Consultation"])
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "abc-123"


@respx.mock
async def test_find_near_misses_annotates_missing_pieces(client):
    respx.get(f"{SPELLBOOK_BASE}/find-my-combos/").mock(
        return_value=httpx.Response(200, json=MOCK_FIND_MY_COMBOS_GET)
    )
    respx.post(f"{SPELLBOOK_BASE}/find-my-combos/").mock(
        return_value=httpx.Response(200, json=MOCK_FIND_MY_COMBOS_RESPONSE)
    )
    # Deck has Oracle but NOT Demonic Consultation or Jace
    result = await client.find_near_misses(["Thassa's Oracle"])
    assert isinstance(result, list)
    assert len(result) == 1
    near = result[0]
    assert "missing_pieces" in near
    # Should be missing Jace and Demonic Consultation
    assert "Demonic Consultation" in near["missing_pieces"] or "Jace, Wielder of Mysteries" in near["missing_pieces"]


@respx.mock
async def test_get_combo_details(client):
    respx.get(f"{SPELLBOOK_BASE}/variants/abc-123/").mock(
        return_value=httpx.Response(200, json=MOCK_VARIANT)
    )
    result = await client.get_combo_details("abc-123")
    assert result["id"] == "abc-123"
    assert result["steps"] == MOCK_VARIANT["description"]


@respx.mock
async def test_get_combo_details_not_found(client):
    respx.get(f"{SPELLBOOK_BASE}/variants/bad-id/").mock(
        return_value=httpx.Response(404)
    )
    result = await client.get_combo_details("bad-id")
    assert result == {"error": "combo_not_found", "combo_id": "bad-id"}
