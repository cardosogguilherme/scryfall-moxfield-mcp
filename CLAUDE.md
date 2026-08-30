# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Python MCP (Model Context Protocol) server that gives Claude access to Scryfall card data and Moxfield deck data. It is registered in Claude Desktop as an MCP server and communicates over stdio (or `streamable-http` / `sse` when deployed via Docker for network access).

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
pytest tests/moxfield/test_client.py::test_get_deck_with_enrichment -v

# Renew Moxfield credentials (interactive — paste Bearer token from browser DevTools)
python save_moxfield_credentials.py
```

## Architecture

```
scryfallmcp/
  server.py          — FastMCP app; registers all tools; entry point (main())
  scryfall/
    client.py        — ScryfallClient: async httpx + tenacity retry on 429; _card_to_dict trims fields
  moxfield/
    client.py        — MoxfieldClient: wraps CredentialManager + ScryfallClient; _enrich_deck merges data
    auth.py          — CredentialManager: loads/saves credentials.json; get_valid_credentials raises on missing/expired
```

`server.py` creates **one shared instance** of `ScryfallClient` and passes it into `MoxfieldClient` so the rate-limit semaphore and HTTP connection pool are shared across all tools.

## Key behaviours to know

**Moxfield auth flow** — Moxfield has no public API and is Cloudflare-protected. Auth is **optional**: `MoxfieldClient._get()` tries `get_valid_credentials()` but falls through to an unauthenticated request (browser headers only) when creds are missing/expired; it only attaches the Bearer token + cookies (needed for private decks) when valid creds exist, and only runs the 401→`login()` retry when creds were present. `credentials.json` is written manually via `save_moxfield_credentials.py` (paste Bearer token from browser DevTools). The `refresh_moxfield_credentials` MCP tool uses the Playwright path which is unreliable — the manual script is the canonical approach.

**Moxfield public tools (`search_decks`, `get_deck`, `get_user_decks`/`find_deck`)** hit read-only `api2.moxfield.com/v2/*` endpoints (`/v2/decks/search`, `/v2/decks/all/{id}`; `get_user_decks` uses `search?authorUserNames=`). `get_deck` accepts a full `moxfield.com/decks/...` URL and validates the id against `^[A-Za-z0-9_-]+$` before interpolating it into the path (path-injection guard); pagination and query length are clamped. **Cloudflare TLS-fingerprint caveat:** these unauthenticated calls succeed via a browser TLS stack (curl/Schannel → 200) but Cloudflare 403s plain `httpx` (OpenSSL fingerprint) — verified locally on Windows. They still work whenever valid creds are present (the `cf_clearance` cookie satisfies Cloudflare), and *may* work unauthenticated from Render's Linux egress (unverified). If the unauthenticated path proves blocked in the cloud, the known fix is routing Moxfield HTTP through `curl_cffi` (`impersonate="chrome"`) — deliberately not adopted to avoid a compiled dependency.

**Scryfall rate limiting** — `ScryfallClient._get/_post` sleep 100ms before every request and retry on 429 with exponential backoff (up to 3 attempts). `get_cards_bulk` chunks at 75 names and runs up to 3 chunks concurrently via a semaphore.

**Transport** — `MCP_TRANSPORT` env var selects `stdio` (default), `streamable-http`, or `sse`. Docker deployment sets this to `streamable-http` on port 8000. `server.py` also exposes a module-level ASGI app `http_app = mcp.streamable_http_app()` (mounted at `/mcp`); when `MCP_TRANSPORT=streamable-http`, `main()` serves it via `uvicorn` on `0.0.0.0:$PORT` (default 8080) instead of `mcp.run(...)`.

**Render deployment** — the server can be deployed publicly to Render (at `https://<service-name>.onrender.com/mcp`) for use as a claude.ai custom connector. `render.yaml` (free-tier blueprint) runs `uvicorn scryfallmcp.server:http_app`; `requirements.txt` holds pinned deps (no `fastmcp` — this uses the SDK's bundled `mcp.server.fastmcp`; no `cloudscraper` — Moxfield uses plain `httpx`). `FastMCP` is constructed with `TransportSecuritySettings(enable_dns_rebinding_protection=False)` so the external `*.onrender.com` Host header isn't rejected with `421` (FastMCP auto-enables that protection on localhost binds). In the cloud, `admin_action: refresh_moxfield_credentials` and private-deck access don't work (no `credentials.json`, no headful browser). The public Moxfield tools (`search_decks`, `get_deck`, `get_user_decks`) are auth-optional and *may* work unauthenticated from Render subject to the Cloudflare TLS-fingerprint caveat above; Scryfall/EDHREC/Spellbook/Rulings tools work unauthenticated. Note the endpoint is public and unauthenticated with DNS-rebinding protection disabled — if the `*.onrender.com` URL ever leaks, add a shared-secret header check on `http_app` to prevent it being used as an open Moxfield/Scryfall proxy.

**`credentials.json`** — stored at the project root (resolved via `Path(__file__).parent.parent.parent` in `auth.py`). It is gitignored and written with `chmod 600`. Tests mock `CredentialManager` entirely — never hit real credentials.

## Testing conventions

Tests use `respx` to mock `httpx` at the transport level (no real HTTP). `pytest-asyncio` is configured with `asyncio_mode = "auto"` so all `async def` test functions run automatically. Moxfield tests mock `CredentialManager` via `MagicMock` + `AsyncMock` and inject a fake `ScryfallClient` — the two clients are always tested independently.
