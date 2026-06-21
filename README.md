# ScryfallMCP

A Python MCP server that exposes Scryfall card data to Claude.

## Tools

### Scryfall
| Tool | Description |
|------|-------------|
| `search_cards` | Search cards using full Scryfall syntax (`t:dragon c:r`, `o:"draw a card" cmc<=2`) |
| `get_card_by_name` | Fetch a single card by name, with optional fuzzy matching |
| `get_card_by_set` | Fetch a specific printing by set code and collector number |
| `get_cards_bulk` | Fetch multiple cards by name in one call |

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

The server communicates over stdio.

```bash
docker run --rm -i scryfallmcp
```

### Claude Desktop integration (Docker)

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "scryfallmcp": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "scryfallmcp"]
    }
  }
}
```

After editing the config, **restart Claude Desktop** (`Cmd+Q` then reopen).

### Network deployment (NUC / home server)

Run the server once on your NUC and connect to it from Claude on any machine on your network.

**On the NUC:**

```bash
git clone <repo>
cd scryfallmcp
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
    environment:
      MCP_TRANSPORT: streamable-http
      FASTMCP_HOST: 0.0.0.0
```

4. Click **Deploy the stack**

Portainer will build the image and start the container. You can redeploy after pulling new code via **Stacks → scryfallmcp → Editor → Update the stack**.

---

## Render (public HTTP deployment)

The server can be deployed to Render as a public Streamable-HTTP endpoint so it can be added to **claude.ai** as a custom connector (no local install needed). After deploying, your endpoint is:

```
https://<your-service-name>.onrender.com/mcp
```

Add it in claude.ai via **Customize → Connectors → Add custom connector** using your endpoint URL (no trailing slash — the endpoint is an exact-match route).

### How it's wired

- **`render.yaml`** (repo root) — Render blueprint: free-tier web service that runs `uvicorn scryfallmcp.server:http_app --host 0.0.0.0 --port $PORT`.
- **`requirements.txt`** (repo root) — pinned runtime deps for the Render build (`mcp[cli]`, `httpx`, `tenacity`, `uvicorn`).
- **`scryfallmcp/server.py`** — exposes a module-level ASGI app, `http_app = mcp.streamable_http_app()` (mounted at `/mcp`), and `main()` serves it via uvicorn when `MCP_TRANSPORT=streamable-http`. `stdio` remains the default for Claude Desktop.
- DNS-rebinding protection is disabled via `TransportSecuritySettings(enable_dns_rebinding_protection=False)`. FastMCP auto-enables it for localhost binds, which makes it reject the external `*.onrender.com` Host header with `421 Invalid Host header`. Disabling it is correct for a public hosted endpoint.

### What works in the cloud

All tools work fully — Scryfall, EDHREC, Commander Spellbook, and Rulings need no auth.

> Render's free tier spins down when idle — the first request after a quiet period cold-starts (~30–60s). This is expected, not a bug.

### Deploying

Render auto-redeploys on every push to `main` (it reads `render.yaml`). To create the service initially: Render → **New + → Blueprint** → connect this repo → it reads `render.yaml` → instance type **Free** → create.

### Local HTTP run (mirrors the Render setup)

```bash
MCP_TRANSPORT=streamable-http PORT=8080 python -m scryfallmcp.server
# then GET http://localhost:8080/mcp should return 406 (live), not 404
```

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
