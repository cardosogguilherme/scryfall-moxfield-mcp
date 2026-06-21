# ScryfallMCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server exposing 4 tools for Scryfall card search.

**Architecture:** Modular Python package (`scryfallmcp/`) with an async Scryfall client (`scryfall/client.py`) and a FastMCP server entry point (`server.py`). All HTTP via `httpx` async, rate-limit protected by `asyncio.sleep` + `tenacity`.

**Tech Stack:** Python 3.11+, `mcp[cli]` (FastMCP), `httpx`, `tenacity`. Tests: `pytest`, `pytest-asyncio`, `respx`.

---

## File Map

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Package metadata, deps, entry point |
| `.gitignore` | Ignore .env, __pycache__, .pytest_cache |
| `scryfallmcp/__init__.py` | Empty package marker |
| `scryfallmcp/server.py` | FastMCP instance, all 4 tool registrations, `main()` entry point |
| `scryfallmcp/scryfall/__init__.py` | Empty |
| `scryfallmcp/scryfall/client.py` | Async Scryfall API client: search, by-name, by-set, bulk |
| `tests/__init__.py` | Empty |
| `tests/scryfall/__init__.py` | Empty |
| `tests/scryfall/test_client.py` | Tests for all 4 Scryfall tools (mocked with respx) |

> **Note:** `README.md` is referenced in the spec architecture but is out of scope for this plan. Add it manually after initial implementation.

> **Note on `mcp[cli]`:** The plan uses `mcp[cli]` (not just `mcp` as in the spec). This intentionally includes the `mcp dev` CLI tool needed for Task 6's integration testing step.

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `scryfallmcp/__init__.py`
- Create: `scryfallmcp/scryfall/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/scryfall/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "scryfallmcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]",
    "httpx",
    "tenacity",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "respx"]

[project.scripts]
scryfallmcp = "scryfallmcp.server:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
.venv/
dist/
*.egg-info/
```

- [ ] **Step 3: Create all empty `__init__.py` files**

```bash
mkdir -p scryfallmcp/scryfall tests/scryfall
touch scryfallmcp/__init__.py scryfallmcp/scryfall/__init__.py
touch tests/__init__.py tests/scryfall/__init__.py
```

- [ ] **Step 4: Install dependencies**

```bash
pip install -e ".[dev]"
```

Expected: No errors. `python -c "import mcp; import httpx"` should succeed.

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml .gitignore scryfallmcp/ tests/
git commit -m "chore: project scaffolding and dependencies"
```

---

## Task 2: Scryfall Client — Base + `search_cards`

**Files:**
- Create: `scryfallmcp/scryfall/client.py`
- Create: `tests/scryfall/test_client.py`

- [ ] **Step 1: Write failing test for `search_cards`**

```python
# tests/scryfall/test_client.py
import pytest
import respx
import httpx
from scryfallmcp.scryfall.client import ScryfallClient

SCRYFALL_BASE = "https://api.scryfall.com"

@pytest.fixture
def client():
    return ScryfallClient()

@respx.mock
async def test_search_cards_returns_card_list(client):
    respx.get(f"{SCRYFALL_BASE}/cards/search").mock(return_value=httpx.Response(200, json={
        "data": [{
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "colors": ["R"],
            "cmc": 1.0,
            "legalities": {"modern": "legal"},
            "set": "leb",
            "image_uris": {"normal": "https://example.com/img.jpg"},
            "prices": {"usd": "0.50"},
        }],
        "has_more": False,
        "total_cards": 1,
    }))
    result = await client.search_cards("t:instant c:r")
    assert len(result) == 1
    assert result[0]["name"] == "Lightning Bolt"
    assert result[0]["mana_cost"] == "{R}"

@respx.mock
async def test_search_cards_404_returns_error(client):
    respx.get(f"{SCRYFALL_BASE}/cards/search").mock(return_value=httpx.Response(404, json={
        "object": "error", "code": "not_found", "details": "No cards found."
    }))
    result = await client.search_cards("t:nonexistenttype12345")
    assert result == {"error": "card not found", "query": "t:nonexistenttype12345"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/scryfall/test_client.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `ScryfallClient` doesn't exist yet.

- [ ] **Step 3: Implement `ScryfallClient` with `search_cards`**

```python
# scryfallmcp/scryfall/client.py
import asyncio
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

BASE_URL = "https://api.scryfall.com"
RATE_LIMIT_DELAY = 0.1  # 100ms between requests


def _is_rate_limited(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _card_to_dict(card: dict) -> dict:
    """Extract the fields we care about from a raw Scryfall card object."""
    return {
        "name": card.get("name"),
        "mana_cost": card.get("mana_cost"),
        "type_line": card.get("type_line"),
        "oracle_text": card.get("oracle_text"),
        "colors": card.get("colors", []),
        "cmc": card.get("cmc"),
        "legalities": card.get("legalities", {}),
        "set": card.get("set"),
        "collector_number": card.get("collector_number"),
        "image_uris": card.get("image_uris") or (
            card.get("card_faces", [{}])[0].get("image_uris")
        ),
        "prices": card.get("prices", {}),
    }


class ScryfallClient:
    def __init__(self):
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

    @retry(
        retry=retry_if_exception(_is_rate_limited),
        wait=wait_exponential(multiplier=1, min=0.2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _get(self, path: str, **params) -> dict:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        r = await self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    @retry(
        retry=retry_if_exception(_is_rate_limited),
        wait=wait_exponential(multiplier=1, min=0.2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _post(self, path: str, json: dict) -> dict:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        r = await self._http.post(path, json=json, timeout=30.0)
        r.raise_for_status()
        return r.json()

    async def search_cards(self, query: str, page: int = 1) -> list[dict] | dict:
        try:
            data = await self._get("/cards/search", q=query, page=page)
            return [_card_to_dict(c) for c in data.get("data", [])]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card not found", "query": query}
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/scryfall/test_client.py -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scryfallmcp/scryfall/client.py tests/scryfall/test_client.py
git commit -m "feat: scryfall client with search_cards"
```

---

## Task 3: Scryfall Client — `get_card_by_name` and `get_card_by_set`

**Files:**
- Modify: `scryfallmcp/scryfall/client.py`
- Modify: `tests/scryfall/test_client.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/scryfall/test_client.py

@respx.mock
async def test_get_card_by_name_fuzzy(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(200, json={
        "name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
        "oracle_text": "Deal 3.", "colors": ["R"], "cmc": 1.0,
        "legalities": {}, "set": "leb", "image_uris": {}, "prices": {},
    }))
    result = await client.get_card_by_name("ligntning bolt", fuzzy=True)
    assert result["name"] == "Lightning Bolt"

@respx.mock
async def test_get_card_by_name_not_found(client):
    respx.get(f"{SCRYFALL_BASE}/cards/named").mock(return_value=httpx.Response(404, json={
        "object": "error", "details": "Not found."
    }))
    result = await client.get_card_by_name("xyzxyzxyz")
    assert result == {"error": "card not found", "query": "xyzxyzxyz"}

@respx.mock
async def test_get_card_by_set(client):
    respx.get(f"{SCRYFALL_BASE}/cards/leb/1").mock(return_value=httpx.Response(200, json={
        "name": "Black Lotus", "mana_cost": "{0}", "type_line": "Artifact",
        "oracle_text": "Tap, Sacrifice Black Lotus: Add three mana.", "colors": [],
        "cmc": 0.0, "legalities": {}, "set": "leb", "image_uris": {}, "prices": {},
    }))
    result = await client.get_card_by_set("leb", "1")
    assert result["name"] == "Black Lotus"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/scryfall/test_client.py::test_get_card_by_name_fuzzy -v
```

Expected: `AttributeError` — method not yet defined.

- [ ] **Step 3: Implement `get_card_by_name` and `get_card_by_set`**

```python
# Add to ScryfallClient in scryfallmcp/scryfall/client.py

    async def get_card_by_name(self, name: str, fuzzy: bool = True) -> dict:
        param_key = "fuzzy" if fuzzy else "exact"
        try:
            data = await self._get("/cards/named", **{param_key: name})
            return _card_to_dict(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card not found", "query": name}
            raise

    async def get_card_by_set(self, set_code: str, collector_number: str) -> dict:
        try:
            data = await self._get(f"/cards/{set_code}/{collector_number}")
            return _card_to_dict(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card not found", "query": f"{set_code}/{collector_number}"}
            raise
```

- [ ] **Step 4: Run all Scryfall tests**

```bash
pytest tests/scryfall/test_client.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scryfallmcp/scryfall/client.py tests/scryfall/test_client.py
git commit -m "feat: scryfall get_card_by_name and get_card_by_set"
```

---

## Task 4: Scryfall Client — `get_cards_bulk`

**Files:**
- Modify: `scryfallmcp/scryfall/client.py`
- Modify: `tests/scryfall/test_client.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/scryfall/test_client.py

@respx.mock
async def test_get_cards_bulk_single_chunk(client):
    names = ["Lightning Bolt", "Counterspell"]
    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(return_value=httpx.Response(200, json={
        "data": [
            {"name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
             "oracle_text": "", "colors": ["R"], "cmc": 1.0, "legalities": {},
             "set": "leb", "image_uris": {}, "prices": {}},
            {"name": "Counterspell", "mana_cost": "{U}{U}", "type_line": "Instant",
             "oracle_text": "", "colors": ["U"], "cmc": 2.0, "legalities": {},
             "set": "leb", "image_uris": {}, "prices": {}},
        ]
    }))
    result = await client.get_cards_bulk(names)
    assert len(result) == 2
    assert {c["name"] for c in result} == {"Lightning Bolt", "Counterspell"}

@respx.mock
async def test_get_cards_bulk_retries_on_429(client):
    """Verifies that a 429 on the collection endpoint triggers a retry."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"object": "error", "code": "too_many_requests"})
        return httpx.Response(200, json={"data": [
            {"name": "Sol Ring", "mana_cost": "{1}", "type_line": "Artifact",
             "oracle_text": "", "colors": [], "cmc": 1.0, "legalities": {},
             "set": "lea", "image_uris": {}, "prices": {}}
        ]})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    result = await client.get_cards_bulk(["Sol Ring"])
    assert call_count == 2  # first call 429, second succeeds
    assert result[0]["name"] == "Sol Ring"

@respx.mock
async def test_get_cards_bulk_chunks_at_75(client):
    """Verifies that 76 names produce exactly 2 API calls."""
    names = [f"Card {i}" for i in range(76)]
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        ids = request.content  # just need it to succeed
        return httpx.Response(200, json={"data": []})

    respx.post(f"{SCRYFALL_BASE}/cards/collection").mock(side_effect=handler)
    await client.get_cards_bulk(names)
    assert call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/scryfall/test_client.py::test_get_cards_bulk_single_chunk -v
```

Expected: `AttributeError`.

- [ ] **Step 3: Implement `get_cards_bulk`**

```python
# Add to ScryfallClient in scryfallmcp/scryfall/client.py

    async def get_cards_bulk(self, names: list[str]) -> list[dict]:
        CHUNK_SIZE = 75
        semaphore = asyncio.Semaphore(3)
        chunks = [names[i:i + CHUNK_SIZE] for i in range(0, len(names), CHUNK_SIZE)]

        async def fetch_chunk(chunk: list[str]) -> list[dict]:
            async with semaphore:
                payload = {"identifiers": [{"name": n} for n in chunk]}
                data = await self._post("/cards/collection", json=payload)
                return [_card_to_dict(c) for c in data.get("data", [])]

        results = await asyncio.gather(*[fetch_chunk(c) for c in chunks])
        return [card for batch in results for card in batch]
```

- [ ] **Step 4: Run all Scryfall tests**

```bash
pytest tests/scryfall/test_client.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scryfallmcp/scryfall/client.py tests/scryfall/test_client.py
git commit -m "feat: scryfall get_cards_bulk with chunking and semaphore"
```

---

## Task 5: MCP Server — Register All 4 Tools

**Files:**
- Create: `scryfallmcp/server.py`

> No unit tests for the server layer — FastMCP tool registration is framework-level wiring. Integration-tested manually per the Verification section.

- [ ] **Step 1: Create `scryfallmcp/server.py`**

```python
# scryfallmcp/server.py
from mcp.server.fastmcp import FastMCP
from scryfallmcp.scryfall.client import ScryfallClient

mcp = FastMCP("scryfallmcp")

_scryfall = ScryfallClient()


# ── Scryfall Tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def search_cards(query: str, page: int = 1) -> list[dict] | dict:
    """Search for Magic: The Gathering cards using full Scryfall syntax.

    Examples: 't:dragon c:r', 'o:"draw a card" cmc<=2', 'is:commander identity:gruul'
    """
    return await _scryfall.search_cards(query, page=page)


@mcp.tool()
async def get_card_by_name(name: str, fuzzy: bool = True) -> dict:
    """Fetch a single card by name. Set fuzzy=False for exact matching."""
    return await _scryfall.get_card_by_name(name, fuzzy=fuzzy)


@mcp.tool()
async def get_card_by_set(set_code: str, collector_number: str) -> dict:
    """Fetch a specific card printing by set code and collector number.

    Example: set_code='mh3', collector_number='237'
    """
    return await _scryfall.get_card_by_set(set_code, collector_number)


@mcp.tool()
async def get_cards_bulk(names: list[str]) -> list[dict]:
    """Fetch multiple cards by name in one call. Handles batching automatically."""
    return await _scryfall.get_cards_bulk(names)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify server starts without errors**

```bash
python -c "from scryfallmcp.server import mcp; print('Server loaded OK')"
```

Expected: `Server loaded OK` with no import errors.

- [ ] **Step 3: Commit**

```bash
git add scryfallmcp/server.py
git commit -m "feat: mcp server with all 4 tools registered"
```

---

## Task 6: End-to-End Verification

- [ ] **Step 1: Run all unit tests one final time**

```bash
pytest tests/ -v
```

Expected: All tests PASS, no failures.

- [ ] **Step 2: Test Scryfall tools via MCP dev mode**

```bash
mcp dev scryfallmcp/server.py
```

In the MCP inspector, call:
- `search_cards` with `query="t:dragon c:r"` → should return a list of red dragons with full card data
- `get_card_by_name` with `name="Lightning Bolt"` → should return Lightning Bolt's full card data
- `get_cards_bulk` with `names=["Sol Ring", "Cultivate", "Command Tower"]` → should return 3 cards
- `get_card_by_set` with `set_code="leb"`, `collector_number="1"` → should return Black Lotus

---

## Notes for Implementer

1. **Double-faced cards** — `_card_to_dict` falls back to `card_faces[0].image_uris` for DFCs. This may need adjustment for split cards or adventures.
