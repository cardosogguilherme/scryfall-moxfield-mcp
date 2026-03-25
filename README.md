# ScryfallMCP

A Python MCP server that exposes Scryfall card data and Moxfield deck data to Claude.

## Tools

### Scryfall
| Tool | Description |
|------|-------------|
| `search_cards` | Search cards using full Scryfall syntax (`t:dragon c:r`, `o:"draw a card" cmc<=2`) |
| `get_card_by_name` | Fetch a single card by name, with optional fuzzy matching |
| `get_card_by_set` | Fetch a specific printing by set code and collector number |
| `get_cards_bulk` | Fetch multiple cards by name in one call |

### Moxfield
| Tool | Description |
|------|-------------|
| `get_user_decks` | List all decks for a Moxfield user |
| `get_deck` | Fetch a deck by ID, with optional Scryfall enrichment and price totals |
| `refresh_moxfield_credentials` | Re-authenticate via browser (unreliable due to Cloudflare — use the manual script instead) |

---

## Installation

```bash
git clone <repo>
cd scryfallmcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

---

## Configuration

Copy the example env file and fill in your Moxfield credentials:

```bash
cp .env.example .env
```

`.env`:
```
MOXFIELD_USERNAME=your@email.com
MOXFIELD_PASSWORD=yourpassword
CREDENTIALS_TTL_HOURS=24
```

---

## Moxfield Authentication

Moxfield has no public API. The server uses your session token and cookies extracted from your browser. Cloudflare blocks automated logins, so you need to extract credentials manually.

### First-time setup (and when credentials expire)

**Step 1 — Get your token from the browser**

1. Open [moxfield.com/decks](https://www.moxfield.com/decks) while logged in
2. Open DevTools (`F12`) → **Network** tab
3. In the filter box, type `api2`
4. Refresh the page (`Cmd+R` / `F5`)
5. Click any request that appears in the list
6. In the right panel → **Headers** → **Request Headers**
7. Copy the `authorization` value (starts with `Bearer eyJ...`)

**Step 2 — Get your cookies (optional but recommended)**

In the same DevTools window:
- Click the **Application** tab
- In the left sidebar: **Storage → Cookies → https://www.moxfield.com**
- Find `_moxfield_session` and any `cf_clearance` entries
- Format them as: `_moxfield_session=VALUE; cf_clearance=VALUE`

> Cookies are optional — the Bearer token alone may be sufficient.

**Step 3 — Save the credentials**

```bash
source .venv/bin/activate
python save_moxfield_credentials.py
```

Paste your token and cookies when prompted. This writes `credentials.json` with `chmod 600`.

Credentials last 24 hours by default (configurable via `CREDENTIALS_TTL_HOURS`). Re-run this script when they expire.

---

## Running the server

```bash
source .venv/bin/activate
mcp dev scryfallmcp/server.py
```

This opens the MCP Inspector at `http://localhost:5173`.

---

## Testing

### Unit tests

```bash
pytest tests/ -v
```

### Manual — Scryfall tools

| Tool | Example parameters |
|------|--------------------|
| `search_cards` | `query = "t:dragon c:r"` |
| `get_card_by_name` | `name = "Lightning Bolt"` |
| `get_card_by_set` | `set_code = "lea"`, `collector_number = "1"` |
| `get_cards_bulk` | `names = ["Sol Ring", "Cultivate", "Command Tower"]` |

### Manual — Moxfield tools

1. Call `get_user_decks` with your Moxfield username (the slug from `moxfield.com/users/<slug>`)
2. Copy an `id` from the results
3. Call `get_deck` with that `id` and `enrich_with_scryfall = true`

The enriched deck response includes `mana_cost`, `oracle_text`, `prices` per card, and a `price_total_usd` field.

---

## Claude Desktop integration

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "scryfallmcp": {
      "command": "/absolute/path/to/scryfallmcp/.venv/bin/python",
      "args": ["-m", "scryfallmcp.server"],
      "cwd": "/absolute/path/to/scryfallmcp"
    }
  }
}
```

Replace `/absolute/path/to/scryfallmcp` with the actual path on your machine.

---

## Notes

- **Moxfield API endpoints** are inferred from browser traffic — they are undocumented and may change
- **`refresh_moxfield_credentials`** is unreliable due to Cloudflare Turnstile blocking headless browsers — use `save_moxfield_credentials.py` instead
- `credentials.json` is gitignored and written with `chmod 600`
