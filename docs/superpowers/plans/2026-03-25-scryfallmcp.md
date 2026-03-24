# ScryfallMCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server exposing 7 tools for Scryfall card search and Moxfield deck fetching, with automatic Playwright-based Moxfield re-authentication.

**Architecture:** Modular Python package (`scryfallmcp/`) with two async clients (`scryfall/client.py`, `moxfield/client.py`), a Playwright credential manager (`moxfield/auth.py`), and a FastMCP server entry point (`server.py`). All HTTP via `httpx` async, rate-limit protected by `asyncio.sleep` + `tenacity`.

**Tech Stack:** Python 3.11+, `mcp[cli]` (FastMCP), `httpx`, `playwright`, `tenacity`, `python-dotenv`. Tests: `pytest`, `pytest-asyncio`, `respx`.

---

## File Map

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Package metadata, deps, entry point |
| `.gitignore` | Ignore credentials.json, .env, __pycache__, .pytest_cache |
| `.env.example` | Template for MOXFIELD_USERNAME / PASSWORD / CREDENTIALS_TTL_HOURS |
| `scryfallmcp/__init__.py` | Empty package marker |
| `scryfallmcp/server.py` | FastMCP instance, all 7 tool registrations, `main()` entry point |
| `scryfallmcp/scryfall/__init__.py` | Empty |
| `scryfallmcp/scryfall/client.py` | Async Scryfall API client: search, by-name, by-set, bulk |
| `scryfallmcp/moxfield/__init__.py` | Empty |
| `scryfallmcp/moxfield/auth.py` | CredentialManager: load/save credentials.json, Playwright login flow |
| `scryfallmcp/moxfield/client.py` | Async Moxfield client: get_user_decks, get_deck + Scryfall enrichment |
| `tests/__init__.py` | Empty |
| `tests/scryfall/__init__.py` | Empty |
| `tests/scryfall/test_client.py` | Tests for all 4 Scryfall tools (mocked with respx) |
| `tests/moxfield/__init__.py` | Empty |
| `tests/moxfield/test_auth.py` | Tests for CredentialManager load/save/expiry logic |
| `tests/moxfield/test_client.py` | Tests for get_user_decks, get_deck, enrichment (mocked) |

> **Note:** `README.md` is referenced in the spec architecture but is out of scope for this plan. Add it manually after initial implementation.

> **Note on `mcp[cli]`:** The plan uses `mcp[cli]` (not just `mcp` as in the spec). This intentionally includes the `mcp dev` CLI tool needed for Task 10's integration testing step.

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `scryfallmcp/__init__.py`
- Create: `scryfallmcp/scryfall/__init__.py`
- Create: `scryfallmcp/moxfield/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/scryfall/__init__.py`
- Create: `tests/moxfield/__init__.py`

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
    "playwright",
    "tenacity",
    "python-dotenv",
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
credentials.json
.env
__pycache__/
*.pyc
.pytest_cache/
.venv/
dist/
*.egg-info/
```

- [ ] **Step 3: Create `.env.example`**

```
MOXFIELD_USERNAME=your@email.com
MOXFIELD_PASSWORD=yourpassword
CREDENTIALS_TTL_HOURS=24
```

- [ ] **Step 4: Create all empty `__init__.py` files**

```bash
mkdir -p scryfallmcp/scryfall scryfallmcp/moxfield tests/scryfall tests/moxfield
touch scryfallmcp/__init__.py scryfallmcp/scryfall/__init__.py scryfallmcp/moxfield/__init__.py
touch tests/__init__.py tests/scryfall/__init__.py tests/moxfield/__init__.py
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -e ".[dev]"
playwright install chromium
```

Expected: No errors. `python -c "import mcp; import httpx; import playwright"` should succeed.

- [ ] **Step 6: Commit**

```bash
git init
git add pyproject.toml .gitignore .env.example scryfallmcp/ tests/
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

## Task 5: Moxfield Auth — CredentialManager

**Files:**
- Create: `scryfallmcp/moxfield/auth.py`
- Create: `tests/moxfield/test_auth.py`

- [ ] **Step 1: Write failing tests for credential loading/saving**

```python
# tests/moxfield/test_auth.py
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from scryfallmcp.moxfield.auth import CredentialManager, Credentials


@pytest.fixture
def creds_file(tmp_path):
    return tmp_path / "credentials.json"


def test_credentials_are_expired_when_past_expiry():
    creds = Credentials(
        token="Bearer abc",
        cookies={"session": "x"},
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    assert creds.is_expired()


def test_credentials_are_valid_when_future_expiry():
    creds = Credentials(
        token="Bearer abc",
        cookies={"session": "x"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert not creds.is_expired()


def test_load_returns_none_when_file_missing(creds_file):
    manager = CredentialManager(creds_path=creds_file)
    assert manager.load() is None


def test_save_and_load_roundtrip(creds_file):
    manager = CredentialManager(creds_path=creds_file)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    creds = Credentials(token="Bearer xyz", cookies={"_moxfield_session": "abc"}, expires_at=expires)
    manager.save(creds)
    loaded = manager.load()
    assert loaded.token == "Bearer xyz"
    assert loaded.cookies == {"_moxfield_session": "abc"}
    assert not loaded.is_expired()


def test_save_sets_file_permissions(creds_file):
    manager = CredentialManager(creds_path=creds_file)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    creds = Credentials(token="t", cookies={}, expires_at=expires)
    manager.save(creds)
    mode = oct(os.stat(creds_file).st_mode)[-3:]
    assert mode == "600"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/moxfield/test_auth.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `CredentialManager` and `Credentials`**

```python
# scryfallmcp/moxfield/auth.py
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

CREDENTIALS_PATH = Path("credentials.json")
DEFAULT_TTL_HOURS = int(os.getenv("CREDENTIALS_TTL_HOURS", "24"))


@dataclass
class Credentials:
    token: str
    cookies: dict
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class CredentialManager:
    def __init__(self, creds_path: Path = CREDENTIALS_PATH):
        self._path = Path(creds_path)

    def load(self) -> Optional[Credentials]:
        if not self._path.exists():
            return None
        with open(self._path) as f:
            data = json.load(f)
        return Credentials(
            token=data["token"],
            cookies=data["cookies"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    def save(self, creds: Credentials) -> None:
        data = {
            "token": creds.token,
            "cookies": creds.cookies,
            "expires_at": creds.expires_at.isoformat(),
        }
        self._path.write_text(json.dumps(data, indent=2))
        os.chmod(self._path, 0o600)

    async def login(self) -> Credentials:
        """Launch headless Chromium to log in to Moxfield and extract credentials."""
        username = os.getenv("MOXFIELD_USERNAME")
        password = os.getenv("MOXFIELD_PASSWORD")
        if not username or not password:
            raise RuntimeError("MOXFIELD_USERNAME and MOXFIELD_PASSWORD must be set in .env")

        from playwright.async_api import async_playwright

        captured_token: Optional[str] = None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Intercept API requests to capture the Authorization header
            async def on_request(request):
                nonlocal captured_token
                auth = request.headers.get("authorization")
                if auth and auth.startswith("Bearer ") and "api2.moxfield.com" in request.url:
                    captured_token = auth

            page.on("request", on_request)

            await page.goto("https://www.moxfield.com/account/login")
            await page.fill('input[name="username"], input[type="email"]', username)
            await page.fill('input[name="password"], input[type="password"]', password)
            await page.click('button[type="submit"]')

            # Wait until we're no longer on the login page (max 15s)
            await page.wait_for_url(lambda url: "/login" not in url, timeout=15000)

            # Trigger an authenticated API call to capture the token
            await page.goto("https://www.moxfield.com/decks")
            await asyncio.sleep(2)  # Let background API calls fire

            cookies_list = await context.cookies()
            await browser.close()

        if not captured_token:
            raise RuntimeError(
                "Failed to capture Authorization token from Moxfield. "
                "Check credentials or inspect Moxfield's login flow in a real browser."
            )

        cookies = {c["name"]: c["value"] for c in cookies_list}
        ttl = int(os.getenv("CREDENTIALS_TTL_HOURS", str(DEFAULT_TTL_HOURS)))
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)
        creds = Credentials(token=captured_token, cookies=cookies, expires_at=expires_at)
        self.save(creds)
        return creds

    async def get_valid_credentials(self) -> Credentials:
        """Return valid credentials, triggering login if expired or missing."""
        creds = self.load()
        if creds is None or creds.is_expired():
            creds = await self.login()
        return creds
```

- [ ] **Step 4: Run auth tests**

```bash
pytest tests/moxfield/test_auth.py -v
```

Expected: All 5 tests PASS. (The `login()` method is not tested here — it requires a real browser.)

- [ ] **Step 5: Commit**

```bash
git add scryfallmcp/moxfield/auth.py tests/moxfield/test_auth.py
git commit -m "feat: moxfield credential manager with playwright login"
```

---

## Task 6: Moxfield Client — `get_user_decks`

**Files:**
- Create: `scryfallmcp/moxfield/client.py`
- Create: `tests/moxfield/test_client.py`

- [ ] **Step 1: Write failing test**

> **Note:** Moxfield has no public API documentation. These endpoint paths (`/users/<username>/decks`) are inferred from browser traffic. Verify against actual network requests in DevTools before hardcoding. Adjust if needed.

```python
# tests/moxfield/test_client.py
import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
from scryfallmcp.moxfield.auth import Credentials
from scryfallmcp.moxfield.client import MoxfieldClient

MOXFIELD_API = "https://api2.moxfield.com"

@pytest.fixture
def mock_creds():
    creds = Credentials(
        token="Bearer testtoken123",
        cookies={"_moxfield_session": "abc123"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    mock_manager = MagicMock()
    mock_manager.get_valid_credentials = AsyncMock(return_value=creds)
    return mock_manager

@pytest.fixture
def client(mock_creds):
    return MoxfieldClient(credential_manager=mock_creds)

@respx.mock
async def test_get_user_decks_returns_list(client):
    respx.get(f"{MOXFIELD_API}/v2/users/johndoe/decks").mock(return_value=httpx.Response(200, json={
        "data": [
            {"publicId": "deck1", "name": "Mono-Red Burn", "format": "modern", "lastUpdatedAtUtc": "2026-01-01T00:00:00Z"},
            {"publicId": "deck2", "name": "Control", "format": "legacy", "lastUpdatedAtUtc": "2026-01-02T00:00:00Z"},
        ]
    }))
    result = await client.get_user_decks("johndoe")
    assert len(result) == 2
    assert result[0]["id"] == "deck1"
    assert result[0]["name"] == "Mono-Red Burn"
    assert result[0]["format"] == "modern"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/moxfield/test_client.py::test_get_user_decks_returns_list -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `MoxfieldClient` with `get_user_decks`**

```python
# scryfallmcp/moxfield/client.py
import httpx
from scryfallmcp.moxfield.auth import CredentialManager, Credentials

MOXFIELD_API = "https://api2.moxfield.com"


class MoxfieldClient:
    def __init__(self, credential_manager: CredentialManager = None):
        self._cred_manager = credential_manager or CredentialManager()
        self._http = httpx.AsyncClient(timeout=30.0)

    def _headers(self, creds: Credentials) -> dict:
        cookie_str = "; ".join(f"{k}={v}" for k, v in creds.cookies.items())
        return {
            "Authorization": creds.token,
            "Cookie": cookie_str,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

    async def _get(self, path: str, **params) -> dict:
        creds = await self._cred_manager.get_valid_credentials()
        headers = self._headers(creds)
        r = await self._http.get(f"{MOXFIELD_API}{path}", headers=headers, params=params)
        if r.status_code == 401:
            # Force re-auth once and retry
            creds = await self._cred_manager.login()
            headers = self._headers(creds)
            r = await self._http.get(f"{MOXFIELD_API}{path}", headers=headers, params=params)
        r.raise_for_status()
        return r.json()

    async def get_user_decks(self, username: str) -> list[dict]:
        data = await self._get(f"/v2/users/{username}/decks")
        return [
            {
                "id": d.get("publicId"),
                "name": d.get("name"),
                "format": d.get("format"),
                "updated_at": d.get("lastUpdatedAtUtc"),
            }
            for d in data.get("data", [])
        ]
```

- [ ] **Step 4: Run all Moxfield client tests**

```bash
pytest tests/moxfield/test_client.py -v
```

Expected: 1 test PASS.

- [ ] **Step 5: Commit**

```bash
git add scryfallmcp/moxfield/client.py tests/moxfield/test_client.py
git commit -m "feat: moxfield client with get_user_decks"
```

---

## Task 7: Moxfield Client — `get_deck` (without enrichment)

**Files:**
- Modify: `scryfallmcp/moxfield/client.py`
- Modify: `tests/moxfield/test_client.py`

- [ ] **Step 1: Write failing test**

> **Note:** The Moxfield deck response structure below is inferred. Verify `mainboard`, `sideboard`, `commanders` key names against actual API responses (inspect in browser DevTools on the deck page). Adjust field names if needed.

```python
# Add to tests/moxfield/test_client.py

MOCK_DECK_RESPONSE = {
    "id": "deck1",
    "name": "Mono-Red Burn",
    "format": "modern",
    "description": "Fast red deck",
    "createdByUser": {"userName": "johndoe"},
    "mainboard": {
        "Lightning Bolt": {"quantity": 4, "card": {"name": "Lightning Bolt"}},
        "Goblin Guide": {"quantity": 4, "card": {"name": "Goblin Guide"}},
    },
    "sideboard": {},
    "commanders": {},
    "companions": {},
}

@respx.mock
async def test_get_deck_no_enrichment(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )
    result = await client.get_deck("deck1", enrich_with_scryfall=False)
    assert result["id"] == "deck1"
    assert result["name"] == "Mono-Red Burn"
    assert result["author"] == "johndoe"
    mainboard = result["boards"]["mainboard"]
    assert len(mainboard) == 2
    bolt = next(c for c in mainboard if c["name"] == "Lightning Bolt")
    assert bolt["quantity"] == 4

@respx.mock
async def test_get_deck_404_returns_error(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/notexist").mock(
        return_value=httpx.Response(404, json={"message": "Not found"})
    )
    result = await client.get_deck("notexist", enrich_with_scryfall=False)
    assert result == {"error": "deck not found", "deck_id": "notexist"}

@respx.mock
async def test_get_deck_401_triggers_reauth_and_retries(client, mock_creds):
    """On 401, the client calls login() and retries once with fresh credentials."""
    fresh_creds = Credentials(
        token="Bearer freshtoken",
        cookies={"_moxfield_session": "freshed"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    mock_creds.login = AsyncMock(return_value=fresh_creds)

    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(401, json={"message": "Unauthorized"})
        return httpx.Response(200, json=MOCK_DECK_RESPONSE)

    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(side_effect=handler)
    result = await client.get_deck("deck1", enrich_with_scryfall=False)
    assert call_count == 2
    mock_creds.login.assert_called_once()
    assert result["name"] == "Mono-Red Burn"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/moxfield/test_client.py -v
```

Expected: Failures on the two new tests.

- [ ] **Step 3: Implement `get_deck`**

```python
# Add to MoxfieldClient in scryfallmcp/moxfield/client.py

    def _parse_deck(self, raw: dict) -> dict:
        """Convert raw Moxfield deck response into our unified deck object."""
        def parse_board(board_data: dict) -> list[dict]:
            return [
                {"name": entry["card"]["name"], "quantity": entry["quantity"]}
                for entry in board_data.values()
            ]

        return {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "format": raw.get("format"),
            "description": raw.get("description", ""),
            "author": raw.get("createdByUser", {}).get("userName"),
            "boards": {
                "mainboard": parse_board(raw.get("mainboard", {})),
                "sideboard": parse_board(raw.get("sideboard", {})),
                "commanders": parse_board(raw.get("commanders", {})),
                "companions": parse_board(raw.get("companions", {})),
            },
            "price_total_usd": None,  # populated by enrichment
        }

    async def get_deck(self, deck_id: str, enrich_with_scryfall: bool = True) -> dict:
        try:
            raw = await self._get(f"/v2/decks/all/{deck_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "deck not found", "deck_id": deck_id}
            raise

        deck = self._parse_deck(raw)

        if enrich_with_scryfall:
            deck = await self._enrich_deck(deck)

        return deck

    async def _enrich_deck(self, deck: dict) -> dict:
        # Implemented in Task 8
        return deck
```

- [ ] **Step 4: Run all Moxfield tests**

```bash
pytest tests/moxfield/test_client.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scryfallmcp/moxfield/client.py tests/moxfield/test_client.py
git commit -m "feat: moxfield get_deck parsing (without enrichment)"
```

---

## Task 8: Deck Enrichment — Merge Scryfall Data

**Files:**
- Modify: `scryfallmcp/moxfield/client.py`
- Modify: `tests/moxfield/test_client.py`

- [ ] **Step 1: Write failing test for enrichment**

```python
# Add to tests/moxfield/test_client.py
from unittest.mock import patch

@respx.mock
async def test_get_deck_with_enrichment(client):
    respx.get(f"{MOXFIELD_API}/v2/decks/all/deck1").mock(
        return_value=httpx.Response(200, json=MOCK_DECK_RESPONSE)
    )

    scryfall_data = [
        {"name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
         "oracle_text": "Deal 3 damage.", "colors": ["R"], "cmc": 1.0,
         "legalities": {}, "set": "leb", "image_uris": {}, "prices": {"usd": "0.50"},
         "collector_number": "61"},
        {"name": "Goblin Guide", "mana_cost": "{R}", "type_line": "Creature",
         "oracle_text": "Haste.", "colors": ["R"], "cmc": 1.0,
         "legalities": {}, "set": "zen", "image_uris": {}, "prices": {"usd": "5.00"},
         "collector_number": "134"},
    ]

    with patch(
        "scryfallmcp.moxfield.client.ScryfallClient.get_cards_bulk",
        new_callable=AsyncMock,
        return_value=scryfall_data,
    ):
        result = await client.get_deck("deck1", enrich_with_scryfall=True)

    mainboard = result["boards"]["mainboard"]
    bolt = next(c for c in mainboard if c["name"] == "Lightning Bolt")
    assert bolt["mana_cost"] == "{R}"
    assert bolt["oracle_text"] == "Deal 3 damage."
    assert bolt["prices"] == {"usd": "0.50"}
    # 4 × $0.50 (Lightning Bolt) + 4 × $5.00 (Goblin Guide) = $22.00
    assert result["price_total_usd"] == "22.00"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/moxfield/test_client.py::test_get_deck_with_enrichment -v
```

Expected: FAIL — enrichment not yet implemented.

- [ ] **Step 3: Implement `_enrich_deck`**

```python
# Replace _enrich_deck stub in scryfallmcp/moxfield/client.py
# Add import at top:
from scryfallmcp.scryfall.client import ScryfallClient

# Replace _enrich_deck:
    async def _enrich_deck(self, deck: dict) -> dict:
        scryfall = ScryfallClient()

        # Collect all unique card names across all boards
        all_cards: list[dict] = []
        for board in deck["boards"].values():
            all_cards.extend(board)

        unique_names = list({c["name"] for c in all_cards})
        scryfall_cards = await scryfall.get_cards_bulk(unique_names)
        scryfall_by_name = {c["name"]: c for c in scryfall_cards if "name" in c}

        total_usd = 0.0

        for board in deck["boards"].values():
            for card in board:
                sc = scryfall_by_name.get(card["name"], {})
                card.update({k: v for k, v in sc.items() if k != "name"})
                price_str = sc.get("prices", {}).get("usd")
                if price_str:
                    try:
                        total_usd += float(price_str) * card["quantity"]
                    except (ValueError, TypeError):
                        pass

        deck["price_total_usd"] = f"{total_usd:.2f}"
        return deck
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scryfallmcp/moxfield/client.py tests/moxfield/test_client.py
git commit -m "feat: deck enrichment with scryfall data and price totals"
```

---

## Task 9: MCP Server — Register All 7 Tools

**Files:**
- Create: `scryfallmcp/server.py`

> No unit tests for the server layer — FastMCP tool registration is framework-level wiring. Integration-tested manually per the Verification section.

- [ ] **Step 1: Create `scryfallmcp/server.py`**

```python
# scryfallmcp/server.py
from mcp.server.fastmcp import FastMCP
from scryfallmcp.scryfall.client import ScryfallClient
from scryfallmcp.moxfield.client import MoxfieldClient
from scryfallmcp.moxfield.auth import CredentialManager

mcp = FastMCP("scryfallmcp")

_scryfall = ScryfallClient()
_cred_manager = CredentialManager()
_moxfield = MoxfieldClient(credential_manager=_cred_manager)


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


# ── Moxfield Tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_user_decks(username: str) -> list[dict]:
    """List all decks for a Moxfield user.

    username: the display name / URL slug (e.g. 'johndoe' from moxfield.com/users/johndoe)
    """
    return await _moxfield.get_user_decks(username)


@mcp.tool()
async def get_deck(deck_id: str, enrich_with_scryfall: bool = True) -> dict:
    """Fetch a Moxfield deck by its public ID.

    Returns full card list with quantities, board breakdown, and (optionally)
    Scryfall card data and price totals.
    """
    return await _moxfield.get_deck(deck_id, enrich_with_scryfall=enrich_with_scryfall)


@mcp.tool()
async def refresh_moxfield_credentials() -> dict:
    """Manually trigger Moxfield re-authentication via browser login.

    Use this if Moxfield calls are returning authentication errors.
    """
    try:
        creds = await _cred_manager.login()
        return {"status": "success", "expires_at": creds.expires_at.isoformat()}
    except Exception as e:
        return {"error": "moxfield_auth_failed", "reason": str(e)}


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
git commit -m "feat: mcp server with all 7 tools registered"
```

---

## Task 10: End-to-End Verification

> These steps require a real `.env` file and network access. They are manual integration tests.

- [ ] **Step 1: Set up `.env`**

```bash
cp .env.example .env
# Edit .env with your real Moxfield credentials
```

- [ ] **Step 2: Run all unit tests one final time**

```bash
pytest tests/ -v
```

Expected: All tests PASS, no failures.

- [ ] **Step 3: Test Scryfall tools via MCP dev mode**

```bash
mcp dev scryfallmcp/server.py
```

In the MCP inspector, call:
- `search_cards` with `query="t:dragon c:r"` → should return a list of red dragons with full card data
- `get_card_by_name` with `name="Lightning Bolt"` → should return Lightning Bolt's full card data
- `get_cards_bulk` with `names=["Sol Ring", "Cultivate", "Command Tower"]` → should return 3 cards
- `get_card_by_set` with `set_code="leb"`, `collector_number="1"` → should return Black Lotus

- [ ] **Step 4: Test Moxfield authentication**

```bash
# In MCP inspector:
```

Call `refresh_moxfield_credentials` → should open headless browser, log in, and return `{"status": "success", "expires_at": "..."}`. Verify `credentials.json` was created with permissions `600`.

- [ ] **Step 5: Test Moxfield deck tools**

In MCP inspector:
- `get_user_decks` with your Moxfield username → should list your decks
- `get_deck` with a real deck ID (from the previous call's results) and `enrich_with_scryfall=true` → should return full deck with `mana_cost`, `oracle_text`, and `price_total_usd` populated

- [ ] **Step 6: Final commit**

```bash
git add .env.example
git commit -m "chore: add .env.example for setup documentation"
```

---

## Notes for Implementer

1. **Moxfield API endpoints** (`/v2/users/<username>/decks`, `/v2/decks/all/<id>`) are inferred from browser traffic — verify these with DevTools before trusting them. If they return 404, inspect actual network requests on moxfield.com.

2. **Cookie names** for Moxfield session are likely `_moxfield_session`. The `cf_clearance` cookie (Cloudflare) may also be required. Confirm by inspecting cookies in DevTools after manual login.

3. **Token capture in Playwright** — the `page.on("request")` handler fires before the page is fully loaded. If the token isn't captured on the `/decks` page load, try navigating to another authenticated page or triggering a search.

4. **Double-faced cards** — `_card_to_dict` falls back to `card_faces[0].image_uris` for DFCs. This may need adjustment for split cards or adventures.
