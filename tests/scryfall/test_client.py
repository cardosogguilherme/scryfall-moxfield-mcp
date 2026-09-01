import json
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


# --- Multi-face cards (transform, modal_dfc, adventure, split, Room) ---------
#
# Scryfall leaves top-level oracle_text null on every multi-face layout, and
# additionally leaves mana_cost/power/toughness null on transform + modal_dfc.
# Those values live in card_faces[]. Payloads below mirror the live API.


def _raw_faced(name, layout, faces, **overrides) -> dict:
    """Raw Scryfall payload for a multi-face card.

    Top-level oracle_text is always None (Scryfall's behaviour on every
    multi-face layout); other top-level fields are supplied per-layout.
    """
    base = {
        "name": name,
        "layout": layout,
        "mana_cost": None,
        "cmc": 3.0,
        "type_line": " // ".join(f["type_line"] for f in faces),
        "oracle_text": None,
        "colors": None,
        "color_identity": ["B"],
        "keywords": [],
        "set": "fin",
        "rarity": "mythic",
        "legalities": {"commander": "legal"},
        "prices": {"usd": "1.00"},
        "card_faces": faces,
    }
    base.update(overrides)
    return base


_SEPHIROTH = _raw_faced(
    "Sephiroth, Fabled SOLDIER // Sephiroth, One-Winged Angel",
    "transform",
    [
        {
            "name": "Sephiroth, Fabled SOLDIER",
            "mana_cost": "{2}{B}",
            "type_line": "Legendary Creature - Human Avatar Soldier",
            "oracle_text": "Whenever Sephiroth enters or attacks, you draw a card.",
            "colors": ["B"],
            "power": "3",
            "toughness": "3",
        },
        {
            "name": "Sephiroth, One-Winged Angel",
            "mana_cost": "",
            "type_line": "Legendary Creature - Angel Nightmare Avatar",
            "oracle_text": "Flying\nSuper Nova - As this creature transforms.",
            "colors": ["B"],
            "power": "5",
            "toughness": "5",
        },
    ],
    keywords=["Flying", "Transform", "Super Nova"],
)

_FELL_THE_PROFANE = _raw_faced(
    "Fell the Profane // Fell Mire",
    "modal_dfc",
    [
        {
            "name": "Fell the Profane",
            "mana_cost": "{2}{B}{B}",
            "type_line": "Instant",
            "oracle_text": "Destroy target creature or planeswalker.",
            "colors": ["B"],
        },
        {
            "name": "Fell Mire",
            "mana_cost": "",
            "type_line": "Land",
            "oracle_text": "As this land enters, you may pay 3 life.",
            "colors": [],
        },
    ],
)

# Adventure/split already carry a joined mana_cost and real colors at top level.
_THRANDUIL = _raw_faced(
    "Thranduil, Sindarin Liege // Silvan Rally",
    "adventure",
    [
        {
            "name": "Thranduil, Sindarin Liege",
            "mana_cost": "{2}{G/U}{G/U}",
            "type_line": "Legendary Creature - Elf Noble",
            "oracle_text": "Other Elves you control get +1/+1.\nLandfall.",
            "power": "2",
            "toughness": "3",
        },
        {
            "name": "Silvan Rally",
            "mana_cost": "{1}{G/U}{G/U}",
            "type_line": "Sorcery - Adventure",
            "oracle_text": "Mill four cards, then put up to two lands into your hand.",
        },
    ],
    mana_cost="{2}{G/U}{G/U} // {1}{G/U}{G/U}",
    colors=["G", "U"],
    color_identity=["G", "U"],
    power="2",
    toughness="3",
)

_FIRE_ICE = _raw_faced(
    "Fire // Ice",
    "split",
    [
        {
            "name": "Fire",
            "mana_cost": "{1}{R}",
            "type_line": "Instant",
            "oracle_text": "Fire deals 2 damage divided as you choose.",
        },
        {
            "name": "Ice",
            "mana_cost": "{1}{U}",
            "type_line": "Instant",
            "oracle_text": "Tap target permanent.\nDraw a card.",
        },
    ],
    mana_cost="{1}{R} // {1}{U}",
    colors=["R", "U"],
    color_identity=["R", "U"],
)

_ROOM = _raw_faced(
    "Bottomless Pool // Locker Room",
    "split",
    [
        {
            "name": "Bottomless Pool",
            "mana_cost": "{U}",
            "type_line": "Enchantment - Room",
            "oracle_text": "When you unlock this door, return up to one creature.",
        },
        {
            "name": "Locker Room",
            "mana_cost": "{4}{U}",
            "type_line": "Enchantment - Room",
            "oracle_text": "Whenever one or more creatures you control deal damage.",
        },
    ],
    mana_cost="{U} // {4}{U}",
    colors=["U"],
    color_identity=["U"],
)


async def _fetch_faced(client, raw):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(
        return_value=httpx.Response(200, json=raw)
    )
    return await client.get_card_by_name(raw["name"])


@respx.mock
async def test_transform_dfc_joins_both_faces(client):
    card = await _fetch_faced(client, _SEPHIROTH)
    assert card["oracle_text"] is not None
    # Text from BOTH faces must be present
    assert "Whenever Sephiroth enters or attacks" in card["oracle_text"]
    assert "Super Nova" in card["oracle_text"]
    assert card["oracle_text"] == (
        "Whenever Sephiroth enters or attacks, you draw a card."
        "\n//\n"
        "Flying\nSuper Nova - As this creature transforms."
    )
    # mana_cost is null at top level on transform; back face has no cost, so the
    # join yields only the front face's cost.
    assert card["mana_cost"] == "{2}{B}"
    # Combat stats come from the FRONT face, kept scalar for numeric consumers
    assert card["power"] == "3"
    assert card["toughness"] == "3"
    assert card["layout"] == "transform"


@respx.mock
async def test_modal_dfc_joins_both_faces(client):
    card = await _fetch_faced(client, _FELL_THE_PROFANE)
    assert card["oracle_text"] is not None
    assert "Destroy target creature" in card["oracle_text"]
    assert "As this land enters" in card["oracle_text"]
    assert card["mana_cost"] == "{2}{B}{B}"
    assert card["layout"] == "modal_dfc"
    # The front face is an Instant - type_line must still expose both faces so a
    # downstream classifier can tell this is not a plain Land.
    assert card["type_line"] == "Instant // Land"


@respx.mock
async def test_adventure_joins_oracle_and_keeps_toplevel_mana_cost(client):
    card = await _fetch_faced(client, _THRANDUIL)
    assert card["oracle_text"] is not None
    assert "Other Elves you control get +1/+1." in card["oracle_text"]
    assert "Mill four cards" in card["oracle_text"]
    # Scryfall already populates these at top level for adventure - passthrough
    assert card["mana_cost"] == "{2}{G/U}{G/U} // {1}{G/U}{G/U}"
    assert card["power"] == "2"
    assert card["layout"] == "adventure"


@respx.mock
async def test_split_card_joins_both_halves(client):
    card = await _fetch_faced(client, _FIRE_ICE)
    assert card["oracle_text"] is not None
    assert "Fire deals 2 damage" in card["oracle_text"]
    assert "Tap target permanent." in card["oracle_text"]
    assert card["mana_cost"] == "{1}{R} // {1}{U}"
    assert "power" not in card  # neither half is a creature


@respx.mock
async def test_room_joins_both_doors(client):
    card = await _fetch_faced(client, _ROOM)
    assert card["oracle_text"] is not None
    assert "When you unlock this door" in card["oracle_text"]
    assert "Whenever one or more creatures" in card["oracle_text"]
    assert card["mana_cost"] == "{U} // {4}{U}"


@respx.mock
async def test_multiface_card_does_not_leak_card_faces(client):
    """The trimmed shape is preserved - card_faces would ~double the payload."""
    card = await _fetch_faced(client, _SEPHIROTH)
    assert "card_faces" not in card


@respx.mock
async def test_single_faced_card_is_unchanged(client):
    """Regression: the fall-through must not alter normal cards."""
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(
        return_value=httpx.Response(200, json=_raw_card(layout="normal"))
    )
    card = await client.get_card_by_name("Lightning Bolt")
    assert card["oracle_text"] == "Lightning Bolt deals 3 damage to any target."
    assert card["mana_cost"] == "{R}"
    # layout is emitted only for multi-face cards: carrying it on every card of
    # a 100-card deck added ~1.7KB and tripped the payload-size guard.
    assert "layout" not in card


# --- Double-faced names in get_cards_bulk ------------------------------------
# /cards/collection does not resolve a full "A // B" name: every such identifier
# comes back in `not_found`, while the front face alone resolves to the same
# card. Moxfield names DFCs with the full form, so before this the whole
# multi-face half of every deck was silently dropped from enrichment.


@respx.mock
async def test_get_cards_bulk_sends_front_face_name(client):
    """Verified live against Scryfall: the full joined name never resolves."""
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"data": [_FELL_THE_PROFANE], "not_found": []})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    result = await client.get_cards_bulk(["Fell the Profane // Fell Mire"])

    assert sent["identifiers"] == [{"name": "Fell the Profane"}]
    # The caller still gets Scryfall's full name back, not our truncated lookup key
    assert result[0]["name"] == "Fell the Profane // Fell Mire"
    assert "Destroy target creature" in result[0]["oracle_text"]
    assert result[0]["price_usd"] is not None


@respx.mock
async def test_get_cards_bulk_matches_result_to_requested_name(client):
    """A DFC requested by front face alone must still pair with its card."""
    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(
        return_value=httpx.Response(200, json={"data": [_FELL_THE_PROFANE]})
    )
    result = await client.get_cards_bulk(["Fell the Profane"])
    assert result[0]["name"] == "Fell the Profane // Fell Mire"


@respx.mock
async def test_get_cards_bulk_reports_missing_names(client):
    """A genuine miss is surfaced, not a silent hole in the list."""
    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(
        return_value=httpx.Response(200, json={
            "data": [_raw_card(name="Lightning Bolt")],
            "not_found": [{"name": "Definitely Not A Card"}],
        })
    )
    result = await client.get_cards_bulk(["Lightning Bolt", "Definitely Not A Card"])
    assert len(result) == 2
    assert result[0]["name"] == "Lightning Bolt"
    assert result[1] == {"name": "Definitely Not A Card", "error": "card not found"}


@respx.mock
async def test_get_cards_bulk_chunks_at_75_with_faced_names(client):
    """The name rewrite must not disturb chunking."""
    names = [f"Card {i} // Back {i}" for i in range(76)]
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        assert all(" // " not in i["name"] for i in json.loads(request.content)["identifiers"])
        return httpx.Response(200, json={"data": []})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    result = await client.get_cards_bulk(names)
    assert call_count == 2
    assert len(result) == 76
    assert all(c["error"] == "card not found" for c in result)
