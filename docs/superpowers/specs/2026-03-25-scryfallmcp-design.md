# ScryfallMCP Design Spec
_Date: 2026-03-25_

## Purpose

Build a Python MCP (Model Context Protocol) server that exposes Scryfall card data and Moxfield deck data to Claude. The server enables Claude to look up Magic: The Gathering cards (with full Scryfall syntax support), fetch user decks from Moxfield (with Scryfall enrichment and price data), and handle Moxfield authentication automatically via Playwright when credentials expire.

## Architecture

```
scryfallmcp/
├── server.py                  # MCP entry point, registers all tools
├── scryfall/
│   └── client.py              # Async Scryfall API client
├── moxfield/
│   ├── client.py              # Async Moxfield API client
│   └── auth.py                # Playwright-based login + credential management
├── credentials.json           # Persisted token + cookies (gitignored)
├── .env                       # MOXFIELD_USERNAME, MOXFIELD_PASSWORD
├── pyproject.toml
└── README.md
```

**Stack:**
- Python 3.11+
- `mcp` SDK (Python MCP server framework)
- `httpx` (async HTTP client)
- `playwright` (browser automation for Moxfield re-auth)
- `python-dotenv` (env var loading)

## MCP Tools

### Scryfall Tools

| Tool | Parameters | Returns |
|------|------------|---------|
| `search_cards` | `query: str`, `page: int = 1` | List of cards matching Scryfall syntax query |
| `get_card_by_name` | `name: str`, `fuzzy: bool = True` | Single card object |
| `get_card_by_set` | `set_code: str`, `collector_number: str` | Single card object (specific printing) |
| `get_cards_bulk` | `names: list[str]` | List of card objects, batched via `/cards/collection` |

Card objects include: name, mana cost, type line, oracle text, colors, CMC, legalities, set, image URIs, prices.

**Deck object shape** (returned by `get_deck`):
```json
{
  "id": "abc123",
  "name": "Mono-Red Burn",
  "format": "modern",
  "description": "...",
  "author": "johndoe",
  "boards": {
    "mainboard": [
      { "quantity": 4, "name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant", "oracle_text": "...", "prices": { "usd": "0.50" } }
    ],
    "sideboard": [],
    "commanders": [],
    "companions": []
  },
  "price_total_usd": "120.50"
}
```

### Moxfield Tools

| Tool | Parameters | Returns |
|------|------------|---------|
| `get_user_decks` | `username: str` (Moxfield display name / URL slug, e.g. `"johndoe"` from `moxfield.com/users/johndoe`) | List of deck summaries (id, name, format, updated_at) |
| `get_deck` | `deck_id: str`, `enrich_with_scryfall: bool = True` | Full deck object (see shape below) |
| `refresh_moxfield_credentials` | _(none)_ | Success/failure status |

## Authentication Flow

### Credential Storage
`credentials.json` at project root (gitignored):
```json
{
  "token": "Bearer eyJ...",
  "cookies": { "session": "...", "cf_clearance": "..." },
  "expires_at": "2026-03-26T10:00:00Z"
}
```

### Auto-refresh Trigger
1. Every Moxfield API request loads credentials from `credentials.json` (created on first successful login; absent file triggers initial login)
2. If `expires_at` is in the past OR the response is HTTP 401 → trigger re-auth
3. Playwright launches headless Chromium, navigates to `https://www.moxfield.com/account/login`
4. Fills `MOXFIELD_USERNAME` / `MOXFIELD_PASSWORD` from `.env`
5. Waits for navigation to an authenticated page (URL no longer contains `/login`)
6. Intercepts outgoing requests via `page.on("request", ...)` to capture the `Authorization: Bearer ...` header from API calls made by the app (e.g. to `api2.moxfield.com`)
7. Captures session cookies from `browser_context.cookies()`; relevant cookies are likely `_moxfield_session` and any Cloudflare cookies (`cf_clearance`) — exact names confirmed at implementation time via browser DevTools inspection
8. Writes fresh credentials to `credentials.json` with mode `0o600` and `expires_at = now + CREDENTIALS_TTL_HOURS`
9. Retries the original request with new credentials

> **Note:** Moxfield has no public API. The auth extraction (step 6-7) requires reverse-engineering network requests. The implementation must inspect actual browser traffic to confirm header names and cookie names before hardcoding them.

### Manual Trigger
`refresh_moxfield_credentials` MCP tool exposes the same flow for on-demand refresh.

## Data Flow — Deck Enrichment

When `get_deck(enrich_with_scryfall=True)`:
1. Fetch deck JSON from Moxfield → extract card list (name, quantity, board: main/side/commander/companion)
2. Collect all unique card names
3. Chunk into groups of ≤75 (Scryfall `/cards/collection` hard limit)
4. Fire `POST /cards/collection` requests with concurrency capped at 3 simultaneous requests (`asyncio.Semaphore(3)`) with 100ms delay between each, respecting Scryfall rate limits
5. Merge Scryfall fields onto each card entry
6. Return unified deck object with metadata, boards, enriched cards, and price totals

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
- Moxfield 401 → auto re-auth (once), then surface error if still failing
- Moxfield 404 → return `{"error": "deck not found", "deck_id": ...}`
- Playwright login failure → return `{"error": "moxfield_auth_failed", "reason": "..."}`

## Configuration

`.env` file:
```
MOXFIELD_USERNAME=your@email.com
MOXFIELD_PASSWORD=yourpassword
CREDENTIALS_TTL_HOURS=24
```

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "scryfallmcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp",
    "httpx",
    "playwright",
    "tenacity",
    "python-dotenv",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "respx"]

[project.scripts]
scryfallmcp = "scryfallmcp.server:main"
```

## Credential File Security

- `credentials.json` is gitignored via `.gitignore`
- Written with `os.chmod(path, 0o600)` after creation/update
- On first run (file absent): automatically triggers Playwright login flow to create it
- Plaintext storage is acceptable for local development; OS keychain integration is out of scope

## Verification

1. Install: `pip install -e ".[dev]"` + `playwright install chromium`
2. Run server: `mcp run server.py` (or `python server.py`)
3. Test Scryfall: call `search_cards` with `q="t:dragon c:r"` — should return red dragons
4. Test `get_card_by_name` with `name="Lightning Bolt"` — should return full card data
5. Test `get_cards_bulk` with a list of 5+ card names
6. Set up `.env`, test `refresh_moxfield_credentials` — should complete without error
7. Test `get_user_decks` with a known Moxfield username
8. Test `get_deck` with a deck ID, verify Scryfall-enriched card data is present
