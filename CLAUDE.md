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

**Moxfield public tools (`search_decks`, `get_deck`, `get_user_decks`/`find_deck`)** hit read-only `api2.moxfield.com/v2/*` endpoints (`/v2/decks/search`, `/v2/decks/all/{id}`; `get_user_decks` uses `search?authorUserNames=`). `get_deck` accepts a full `moxfield.com/decks/...` URL and validates the id against `^[A-Za-z0-9_-]+$` before interpolating it into the path (path-injection guard); pagination and query length are clamped. **Cloudflare:** Moxfield HTTP goes through `curl_cffi`'s `AsyncSession(impersonate="chrome")`, not `httpx` — plain `httpx` is 403'd on *both* routes (OpenSSL TLS fingerprint). `"chrome"` (not a pinned `chromeNNN`) tracks the newest profile the installed `curl_cffi` ships, so bumping the pin refreshes the fingerprint. `_headers()` deliberately sends **no** `User-Agent`: `curl_cffi` supplies one matching the fingerprint it presents, and a hand-written UA contradicts it. Note `AsyncSession` spells shutdown `close()` while `httpx` spells it `aclose()` — `MoxfieldClient.close()` handles both.

**Egress caveat — works locally, 403s from Render.** Verified 2026-09-01: from a residential Windows IP, unauthenticated `/v2/decks/search`, `/v2/decks/all/{id}` and `/v3/decks/all/{id}` all return 200 under `curl_cffi` 0.9.0 *and* 0.13.0, with or without our headers. The same deployed code 403s from Render. The version pin and the header set are therefore both exonerated; the unexplained delta is the egress IP. `_MoxfieldHTTPError` captures `cf-ray` / `cf-mitigated` / `server` and a 200-char body snippet so the next cloud 403 says whether it is a Cloudflare edge block or a Moxfield application error. If it is the edge, the remaining options are a proxy with a clean IP, a different host, or serving the Moxfield tools over local stdio (which works today).

**Scryfall rate limiting** — `ScryfallClient._get/_post` sleep 100ms before every request and retry on 429 with exponential backoff (up to 3 attempts). `get_cards_bulk` chunks at 75 names and runs up to 3 chunks concurrently via a semaphore.

**Transport** — `MCP_TRANSPORT` env var selects `stdio` (default), `streamable-http`, or `sse`. Docker deployment sets this to `streamable-http` on port 8000. `server.py` also exposes a module-level ASGI app `http_app = mcp.streamable_http_app()` (mounted at `/mcp`); when `MCP_TRANSPORT=streamable-http`, `main()` serves it via `uvicorn` on `0.0.0.0:$PORT` (default 8080) instead of `mcp.run(...)`.

**Render deployment** — the server can be deployed publicly to Render (at `https://<service-name>.onrender.com/mcp`) for use as a claude.ai custom connector. `render.yaml` (free-tier blueprint) runs `uvicorn scryfallmcp.server:http_app`; `requirements.txt` holds pinned deps (no `fastmcp` — this uses the SDK's bundled `mcp.server.fastmcp`; `curl_cffi` is pinned there and is what Render actually builds, so bump it there, not only in `pyproject.toml`). `FastMCP` is constructed with `TransportSecuritySettings(enable_dns_rebinding_protection=False)` so the external `*.onrender.com` Host header isn't rejected with `421` (FastMCP auto-enables that protection on localhost binds). In the cloud, `admin_action: refresh_moxfield_credentials` and private-deck access don't work (no `credentials.json`, no headful browser). The public Moxfield tools (`search_decks`, `get_deck`, `get_user_decks`) are auth-optional but currently 403 from Render — see the egress caveat above; Scryfall/EDHREC/Spellbook/Rulings tools work unauthenticated. Note the endpoint is public and unauthenticated with DNS-rebinding protection disabled — if the `*.onrender.com` URL ever leaks, add a shared-secret header check on `http_app` to prevent it being used as an open Moxfield/Scryfall proxy.

**`credentials.json`** — stored at the project root (resolved via `Path(__file__).parent.parent.parent` in `auth.py`). It is gitignored and written with `chmod 600`. Tests mock `CredentialManager` entirely — never hit real credentials.

## Testing conventions

Tests use `respx` to mock `httpx` at the transport level (no real HTTP). `pytest-asyncio` is configured with `asyncio_mode = "auto"` so all `async def` test functions run automatically. Moxfield tests mock `CredentialManager` via `MagicMock` + `AsyncMock` and inject a fake `ScryfallClient` — the two clients are always tested independently.

`tests/moxfield/test_live_cloudflare.py` is the one exception: it hits the real endpoints and is deselected by default via `addopts = "-m 'not live'"`. Run it with `pytest tests/moxfield/test_live_cloudflare.py -m live -v` to check whether a given host's egress gets through Cloudflare — that is the question the mocked suite structurally cannot answer.
