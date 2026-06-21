# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Python MCP (Model Context Protocol) server that gives Claude access to Scryfall card data. It is registered in Claude Desktop as an MCP server and communicates over stdio (or `streamable-http` / `sse` when deployed via Docker for network access).

## Commands

```bash
# Install (once)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run the server locally (opens MCP Inspector at http://localhost:5173)
mcp dev scryfallmcp/server.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/scryfall/test_client.py -v

# Run a single test by name
pytest tests/scryfall/test_client.py::test_get_card_by_name_exact -v
```

## Architecture

```
scryfallmcp/
  server.py          — FastMCP app; registers all tools; entry point (main())
  scryfall/
    client.py        — ScryfallClient: async httpx + tenacity retry on 429; _card_to_dict trims fields
```

`server.py` creates **one shared instance** of `ScryfallClient`, used directly by the Scryfall tools and passed into `RulingsClient`, so the rate-limit semaphore and HTTP connection pool are shared across all tools.

## Key behaviours to know

**Scryfall rate limiting** — `ScryfallClient._get/_post` sleep 100ms before every request and retry on 429 with exponential backoff (up to 3 attempts). `get_cards_bulk` chunks at 75 names and runs up to 3 chunks concurrently via a semaphore.

**Transport** — `MCP_TRANSPORT` env var selects `stdio` (default), `streamable-http`, or `sse`. Docker deployment sets this to `streamable-http` on port 8000. `server.py` also exposes a module-level ASGI app `http_app = mcp.streamable_http_app()` (mounted at `/mcp`); when `MCP_TRANSPORT=streamable-http`, `main()` serves it via `uvicorn` on `0.0.0.0:$PORT` (default 8080) instead of `mcp.run(...)`.

**Render deployment** — the server can be deployed publicly to Render (at `https://<service-name>.onrender.com/mcp`) for use as a claude.ai custom connector. `render.yaml` (free-tier blueprint) runs `uvicorn scryfallmcp.server:http_app`; `requirements.txt` holds pinned deps (no `fastmcp` — this uses the SDK's bundled `mcp.server.fastmcp`). `FastMCP` is constructed with `TransportSecuritySettings(enable_dns_rebinding_protection=False)` so the external `*.onrender.com` Host header isn't rejected with `421` (FastMCP auto-enables that protection on localhost binds). In the cloud, all tools work unauthenticated.

## Testing conventions

Tests use `respx` to mock `httpx` at the transport level (no real HTTP). `pytest-asyncio` is configured with `asyncio_mode = "auto"` so all `async def` test functions run automatically.
