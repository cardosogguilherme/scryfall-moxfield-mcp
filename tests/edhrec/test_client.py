import pytest
import respx
import httpx
from scryfallmcp.edhrec.client import EDHRecClient, _to_slug

EDHREC_BASE = "https://json.edhrec.com/pages"

MOCK_COMMANDER_PAGE = {
    "container": {
        "json_dict": {
            "cardlists": [
                {
                    "header": "High Synergy Cards",
                    "tag": "highsynergycards",
                    "cardviews": [
                        {
                            "name": "Goblin Warchief",
                            "synergy": 0.72,
                            "inclusion": 33767,
                            "num_decks": 33767,
                            "potential_decks": 38563,
                            "trend_zscore": -0.237,
                        },
                        {
                            "name": "Skirk Prospector",
                            "synergy": 0.65,
                            "inclusion": 28000,
                            "num_decks": 28000,
                            "potential_decks": 38563,
                            "trend_zscore": 0.1,
                        },
                    ],
                },
                {
                    "header": "Top Cards",
                    "tag": "topcards",
                    "cardviews": [
                        {
                            "name": "Sol Ring",
                            "synergy": 0.01,
                            "inclusion": 37000,
                            "num_decks": 37000,
                            "potential_decks": 38563,
                            "trend_zscore": 0.0,
                        }
                    ],
                },
            ],
            "panels": {
                "taglinks": [
                    {"value": "Goblins", "slug": "goblins", "count": 8237},
                    {"value": "Tokens", "slug": "tokens", "count": 2178},
                ]
            },
        }
    }
}


@pytest.fixture
async def client():
    async with EDHRecClient() as c:
        yield c


def test_to_slug():
    assert _to_slug("Krenko, Mob Boss") == "krenko-mob-boss"
    assert _to_slug("Atraxa, Praetors' Voice") == "atraxa-praetors-voice"
    assert _to_slug("Thassa's Oracle") == "thassas-oracle"


@respx.mock
async def test_get_commander_recommendations_returns_categories(client):
    respx.get(f"{EDHREC_BASE}/commanders/krenko-mob-boss.json").mock(
        return_value=httpx.Response(200, json=MOCK_COMMANDER_PAGE)
    )
    result = await client.get_commander_recommendations("Krenko, Mob Boss")
    assert isinstance(result, list)
    assert len(result) == 2
    first = result[0]
    assert first["category"] == "High Synergy Cards"
    assert len(first["cards"]) == 2
    card = first["cards"][0]
    assert card["name"] == "Goblin Warchief"
    assert card["synergy_score"] == 0.72
    assert card["inclusion_percent"] == round(33767 / 38563 * 100, 1)


@respx.mock
async def test_get_commander_recommendations_with_theme(client):
    respx.get(f"{EDHREC_BASE}/commanders/krenko-mob-boss/tokens.json").mock(
        return_value=httpx.Response(200, json=MOCK_COMMANDER_PAGE)
    )
    result = await client.get_commander_recommendations("Krenko, Mob Boss", theme="tokens")
    assert isinstance(result, list)


@respx.mock
async def test_get_commander_recommendations_404(client):
    respx.get(f"{EDHREC_BASE}/commanders/nonexistent-commander.json").mock(
        return_value=httpx.Response(404)
    )
    result = await client.get_commander_recommendations("Nonexistent Commander")
    assert result == {"error": "commander_not_found", "query": "Nonexistent Commander"}


@respx.mock
async def test_get_commander_themes(client):
    respx.get(f"{EDHREC_BASE}/commanders/krenko-mob-boss.json").mock(
        return_value=httpx.Response(200, json=MOCK_COMMANDER_PAGE)
    )
    themes = await client.get_commander_themes("Krenko, Mob Boss")
    assert isinstance(themes, list)
    assert len(themes) == 2
    assert themes[0] == {"theme": "Goblins", "slug": "goblins", "deck_count": 8237}
    assert themes[1] == {"theme": "Tokens", "slug": "tokens", "deck_count": 2178}


@respx.mock
async def test_get_average_deck_returns_top_cards(client):
    respx.get(f"{EDHREC_BASE}/commanders/krenko-mob-boss.json").mock(
        return_value=httpx.Response(200, json=MOCK_COMMANDER_PAGE)
    )
    result = await client.get_average_deck("Krenko, Mob Boss")
    assert isinstance(result, list)
    assert result[0]["name"] == "Sol Ring"


@respx.mock
async def test_get_card_top_commanders_not_found(client):
    respx.get(f"{EDHREC_BASE}/cards/lightning-bolt.json").mock(
        return_value=httpx.Response(404)
    )
    result = await client.get_card_top_commanders("Lightning Bolt")
    assert result == {"error": "card_not_found", "query": "Lightning Bolt"}
