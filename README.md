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

To extend the TTL, set in `.env`:
```
CREDENTIALS_TTL_HOURS=168
```

> Whether it stays valid that long depends on Moxfield's server-side session timeout. If they invalidate your session, you'll need to re-run the script regardless of the TTL setting.

---

## Running the server

```bash
source .venv/bin/activate
mcp dev scryfallmcp/server.py
```

This opens the MCP Inspector at `http://localhost:5173`.

---

## Docker

### Build the image

```bash
docker build -t scryfallmcp .
```

### Run (stdio mode, for Claude)

The server communicates over stdio. `credentials.json` is mounted from the host so it can be renewed without rebuilding the image.

```bash
docker run --rm -i \
  -v /path/to/scryfallmcp/credentials.json:/app/credentials.json \
  -e CREDENTIALS_TTL_HOURS=24 \
  scryfallmcp
```

> **Note:** `credentials.json` must exist on the host before running. Follow the [Moxfield Authentication](#moxfield-authentication) steps to create it.

### Claude Desktop integration (Docker)

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "scryfallmcp": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/path/to/scryfallmcp/credentials.json:/app/credentials.json",
        "-e", "CREDENTIALS_TTL_HOURS=24",
        "scryfallmcp"
      ]
    }
  }
}
```

Replace the volume path with the absolute path to your local `credentials.json`.

After editing the config, **restart Claude Desktop** (`Cmd+Q` then reopen).

### Network deployment (NUC / home server)

Run the server once on your NUC and connect to it from Claude on any machine on your network.

**On the NUC:**

```bash
git clone <repo>
cd scryfallmcp
# Create credentials.json first (follow Moxfield Authentication steps above)
docker compose up --build -d
```

The server starts in `streamable-http` mode and listens on port 8000.

**On any other machine — Claude Desktop config:**

```json
{
  "mcpServers": {
    "scryfallmcp": {
      "url": "http://<NUC_IP>:8000/mcp"
    }
  }
}
```

Replace `<NUC_IP>` with your NUC's local IP address (e.g. `192.168.1.100`).

> If your Claude Desktop version doesn't support `streamable-http`, change `docker-compose.yml` to `MCP_TRANSPORT: sse` and use `"url": "http://<NUC_IP>:8000/sse"` in the config instead.

**Renewing credentials on the NUC:**

Run `save_moxfield_credentials.py` on the NUC to update `credentials.json`. The running container will pick up the new file automatically via the volume mount — no restart needed.

```bash
cd scryfallmcp
python save_moxfield_credentials.py
```

#### Deploying via Portainer

If you manage your NUC with Portainer, deploy as a Stack instead of using `docker compose` directly.

1. In the Portainer UI go to **Stacks → Add stack**
2. Give it a name (e.g. `scryfallmcp`)
3. Choose **Web editor** and paste the contents of `docker-compose.yml`:

```yaml
services:
  scryfallmcp:
    image: scryfallmcp
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /path/on/nuc/scryfallmcp/credentials.json:/app/credentials.json
    environment:
      MCP_TRANSPORT: streamable-http
      FASTMCP_HOST: 0.0.0.0
      CREDENTIALS_TTL_HOURS: 24
```

> Replace `/path/on/nuc/scryfallmcp/credentials.json` with the absolute path to your `credentials.json` on the NUC. Portainer does not resolve relative paths, so it must be absolute.

4. Click **Deploy the stack**

Portainer will build the image and start the container. You can redeploy after pulling new code via **Stacks → scryfallmcp → Editor → Update the stack**.

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

After editing the config, **restart Claude Desktop** (`Cmd+Q` then reopen). The tools will appear automatically in your conversations.

### Renewing credentials

When your Moxfield credentials expire, Claude will respond with:
> `moxfield_auth_required: Moxfield credentials have expired. Run: python save_moxfield_credentials.py`

To renew:
1. Go to [moxfield.com/decks](https://www.moxfield.com/decks) in your browser
2. Open DevTools (`F12`) → **Network** tab → filter by `api2` → refresh the page
3. Click any request → **Headers** → **Request Headers** → copy `authorization`
4. Run the script and paste the new token:
   ```bash
   cd /Users/guilherme.cardoso/Development/scryfallmcp
   source .venv/bin/activate
   python save_moxfield_credentials.py
   ```
5. Restart Claude Desktop

---

## Notes

- **Moxfield API endpoints** are inferred from browser traffic — they are undocumented and may change
- **`refresh_moxfield_credentials`** is unreliable due to Cloudflare Turnstile blocking headless browsers — use `save_moxfield_credentials.py` instead
- `credentials.json` is gitignored and written with `chmod 600`
