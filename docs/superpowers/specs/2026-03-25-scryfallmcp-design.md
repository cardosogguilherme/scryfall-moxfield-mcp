# ScryfallMCP Design Spec
_Date: 2026-03-25_

## Purpose

Build a Python MCP (Model Context Protocol) server that exposes Scryfall card data to Claude. The server enables Claude to look up Magic: The Gathering cards with full Scryfall syntax support.

## Architecture

```
scryfallmcp/
├── server.py                  # MCP entry point, registers all tools
├── scryfall/
│   └── client.py              # Async Scryfall API client
├── pyproject.toml
└── README.md
```

**Stack:**
- Python 3.11+
- `mcp` SDK (Python MCP server framework)
- `httpx` (async HTTP client)

## MCP Tools

### Scryfall Tools

| Tool | Parameters | Returns |
|------|------------|---------|
| `search_cards` | `query: str`, `page: int = 1` | List of cards matching Scryfall syntax query |
| `get_card_by_name` | `name: str`, `fuzzy: bool = True` | Single card object |
| `get_card_by_set` | `set_code: str`, `collector_number: str` | Single card object (specific printing) |
| `get_cards_bulk` | `names: list[str]` | List of card objects, batched via `/cards/collection` |

Card objects include: name, mana cost, type line, oracle text, colors, CMC, legalities, set, image URIs, prices.

## Scryfall Client Details

- Base URL: `https://api.scryfall.com`
- No authentication required
- Rate limiting: 50–100ms `asyncio.sleep` between all requests (proactive, per Scryfall policy). On 429 response, exponential backoff with `tenacity` (max 3 retries, starting at 200ms).
- `search_cards` maps directly to `GET /cards/search?q=<query>&page=<page>`
- `get_card_by_name` uses `GET /cards/named?fuzzy=<name>` or `exact=<name>`
- `get_card_by_set` uses `GET /cards/<set>/<number>`
- `get_cards_bulk` uses `POST /cards/collection` with `{ "identifiers": [{"name": "..."}, ...] }` — max 75 identifiers per request

## Error Handling

- Scryfall 404 → return `{"error": "card not found", "query": ...}`
- Scryfall rate limit (429) → exponential backoff, max 3 retries

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "scryfallmcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp",
    "httpx",
    "tenacity",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "respx"]

[project.scripts]
scryfallmcp = "scryfallmcp.server:main"
```

## Verification

1. Install: `pip install -e ".[dev]"`
2. Run server: `mcp run server.py` (or `python server.py`)
3. Test Scryfall: call `search_cards` with `q="t:dragon c:r"` — should return red dragons
4. Test `get_card_by_name` with `name="Lightning Bolt"` — should return full card data
5. Test `get_cards_bulk` with a list of 5+ card names
