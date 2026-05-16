import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock
from scryfallmcp.rulings.client import RulingsClient, _parse_rules

SCRYFALL_BASE = "https://api.scryfall.com"
RULES_URL = "https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.txt"

SAMPLE_RULES_TEXT = """
1. Game Concepts
100. General
100.1. These Magic rules apply to any Magic game with two or more players.
100.1a A match of Magic consists of games.

702. Keyword Abilities
702.1. Most keyword abilities are activated or triggered abilities.
702.19. Cascade
702.19a Cascade is a triggered ability.
702.19b When a player casts a spell with cascade, that player exiles cards.

701. Keyword Actions
701.1. Most keyword actions are self-defining.
"""


@pytest.fixture
def mock_scryfall():
    scryfall = MagicMock()
    scryfall.get_card_by_name = AsyncMock(return_value={
        "name": "Lightning Bolt",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    })
    scryfall._get = AsyncMock(return_value={
        "rulings_uri": "https://api.scryfall.com/cards/lightning-bolt-id/rulings",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    })
    return scryfall


@pytest.fixture
async def client(mock_scryfall):
    c = RulingsClient(scryfall_client=mock_scryfall)
    # Pre-load rules so tests don't need to mock the WotC URL
    c._rules = _parse_rules(SAMPLE_RULES_TEXT)
    return c


def test_parse_rules_extracts_numbered_entries():
    rules = _parse_rules(SAMPLE_RULES_TEXT)
    assert "100" in rules
    assert "100.1" in rules
    assert "100.1a" in rules
    assert "702.19" in rules
    assert "702.19a" in rules
    assert "702.19b" in rules


async def test_search_comprehensive_rules_finds_matches(client):
    results = await client.search_comprehensive_rules("cascade")
    assert any("702.19" in r["rule"] for r in results)


async def test_search_comprehensive_rules_section_filter(client):
    results = await client.search_comprehensive_rules("cascade", section="702")
    assert all(r["rule"].startswith("702") for r in results)
    # Should not include 700 or 701 results
    assert not any(r["rule"].startswith("701") for r in results)


async def test_get_rule_returns_text_and_parent(client):
    result = await client.get_rule("702.19a")
    assert result["rule"] == "702.19a"
    assert "cascade" in result["text"].lower() or "triggered" in result["text"].lower()
    # Parent should be 702.19
    assert result["parent"]["rule"] == "702.19"


async def test_get_rule_not_found(client):
    result = await client.get_rule("999.99")
    assert result == {"error": "rule_not_found", "rule": "999.99"}


async def test_get_keyword_definition_finds_keyword(client):
    result = await client.get_keyword_definition("cascade")
    assert result["keyword"] == "cascade"
    assert len(result["definitions"]) > 0
    assert any("702.19" in d["rule"] for d in result["definitions"])


async def test_cache_status_before_and_after_load(mock_scryfall):
    c = RulingsClient(scryfall_client=mock_scryfall)
    assert c.cache_status() == {"loaded": False, "rule_count": 0}
    c._rules = _parse_rules(SAMPLE_RULES_TEXT)
    status = c.cache_status()
    assert status["loaded"] is True
    assert status["rule_count"] > 0


@respx.mock
async def test_get_card_rulings_calls_scryfall(client, mock_scryfall):
    respx.get(f"{SCRYFALL_BASE}/cards/lightning-bolt-id/rulings").mock(
        return_value=httpx.Response(200, json={
            "data": [
                {"published_at": "2022-01-01", "comment": "Can target players or permanents."}
            ]
        })
    )
    # Override _get to use actual httpx for the rulings fetch, but use the path-only form
    async def fake_get(path, **kwargs):
        if "rulings" in path:
            # Use respx-mocked httpx
            async with httpx.AsyncClient(base_url=SCRYFALL_BASE) as http:
                r = await http.get(path)
                return r.json()
        return {"rulings_uri": f"https://api.scryfall.com/cards/lightning-bolt-id/rulings"}

    mock_scryfall._get = AsyncMock(side_effect=fake_get)

    result = await client.get_card_rulings("Lightning Bolt")
    assert result["card"] == "Lightning Bolt"
    assert isinstance(result["rulings"], list)
