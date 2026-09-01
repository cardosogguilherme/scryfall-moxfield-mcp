import re

from scryfallmcp.moxfield.auth import CredentialManager, Credentials
from scryfallmcp.scryfall.client import ScryfallClient, _front_name


class _MoxfieldHTTPError(Exception):
    """A non-2xx from Moxfield, carrying the signal needed to tell apart a
    Cloudflare bot-management block from a Moxfield application error.

    A bare "HTTP 403" is unactionable: it cannot distinguish an edge challenge
    (`cf-mitigated`, a Ray ID, an HTML interstitial) from Moxfield itself
    refusing the request. Only response-side data is captured — request headers
    can carry the Bearer token and cookies and must never be echoed.
    """

    def __init__(self, status_code: int, response=None):
        self.status_code = status_code
        self.cf_ray = self.cf_mitigated = self.server = self.body = None
        if response is not None:
            headers = getattr(response, "headers", {}) or {}
            self.cf_ray = headers.get("cf-ray")
            self.cf_mitigated = headers.get("cf-mitigated")
            self.server = headers.get("server")
            self.body = (getattr(response, "text", "") or "")[:_ERROR_BODY_CHARS].strip()
        super().__init__(self._message())

    def _message(self) -> str:
        signal = {
            "cf-mitigated": self.cf_mitigated,
            "cf-ray": self.cf_ray,
            "server": self.server,
        }
        detail = ", ".join(f"{k}={v}" for k, v in signal.items() if v)
        msg = f"HTTP {self.status_code}"
        if detail:
            msg += f" ({detail})"
        if self.body:
            msg += f": {self.body!r}"
        return msg

MOXFIELD_API = "https://api2.moxfield.com"

# How much of an error body to keep. Enough to recognise a Cloudflare
# interstitial or a JSON error, short enough not to dump an HTML page.
_ERROR_BODY_CHARS = 200

# Extract the public deck id from a full Moxfield URL, e.g.
# https://moxfield.com/decks/abc123 -> abc123
_DECK_ID_RE = re.compile(r"moxfield\.com/decks/([A-Za-z0-9_-]+)")
# Moxfield public ids / usernames are limited to these characters. Validating
# before interpolating into a URL path guards against path/query injection.
_VALID_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Bounds to keep a single call from requesting oversized pages / queries.
_MAX_QUERY_LEN = 300
_MAX_PAGE_SIZE = 50

# Moxfield's format vocabulary is larger than we can verify by probing (the API
# rate-limits with HTTP 429 well before the list is exhausted), so `fmt` is
# bounded by shape rather than by an allowlist that would reject valid formats.
_MAX_FMT_LEN = 40
_VALID_FMT_RE = re.compile(r"^[A-Za-z]+$")

# These two vocabularies ARE small and closed, and were verified against the
# live endpoint: each value below produces a distinct ordering, while an
# unrecognised value makes Moxfield return an empty error response. Dropping an
# unknown value is therefore better than forwarding it.
_SORT_TYPES = frozenset({"updated", "created", "views", "likes", "name", "comments"})
_SORT_DIRECTIONS = frozenset({"ascending", "descending"})


def _clamp_page(page: int) -> int:
    try:
        return max(1, int(page))
    except (ValueError, TypeError):
        return 1


def _clamp_page_size(page_size: int, default: int) -> int:
    try:
        return max(1, min(_MAX_PAGE_SIZE, int(page_size)))
    except (ValueError, TypeError):
        return default


class MoxfieldClient:
    def __init__(
        self,
        credential_manager: CredentialManager | None = None,
        scryfall_client: "ScryfallClient | None" = None,
        http_client=None,
    ):
        self._cred_manager = credential_manager or CredentialManager()
        self._scryfall = scryfall_client or ScryfallClient()
        if http_client is not None:
            self._http = http_client
        else:
            from curl_cffi.requests import AsyncSession
            # "chrome" tracks the newest profile the installed curl_cffi ships,
            # so the fingerprint stops ageing against Cloudflare on every bump.
            self._http = AsyncSession(impersonate="chrome")

    async def close(self) -> None:
        # httpx spells it aclose(), curl_cffi's AsyncSession spells it close().
        # Both are coroutines; the injected test double may be either.
        closer = getattr(self._http, "aclose", None) or self._http.close
        await closer()
        await self._scryfall.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    def _headers(self, creds: Credentials | None = None) -> dict:
        """Site headers for Moxfield's public API.

        Deliberately no User-Agent: curl_cffi's impersonation supplies one that
        matches the TLS/HTTP2 fingerprint it presents. Hand-writing a UA here
        pins it to whatever Chrome version we last typed and contradicts that
        fingerprint, which is exactly what Cloudflare scores on.

        Authentication is optional: the Authorization/Cookie pair is only
        attached when valid credentials are available (needed for private
        decks). Public read endpoints work with these headers alone.
        """
        headers = {
            "Accept": "application/json",
            "Origin": "https://www.moxfield.com",
            "Referer": "https://www.moxfield.com/",
        }
        if creds is not None:
            headers["Authorization"] = creds.token
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in creds.cookies.items())
        return headers

    async def _get(self, path: str, **params) -> dict:
        # Use credentials if we have valid ones; otherwise fall through to an
        # unauthenticated request (public data works without a token).
        try:
            creds = await self._cred_manager.get_valid_credentials()
        except RuntimeError:
            creds = None

        r = await self._http.get(
            f"{MOXFIELD_API}{path}", headers=self._headers(creds), params=params
        )
        if r.status_code == 401 and creds is not None:
            # Credentials were present but rejected — force a re-auth once and retry.
            try:
                creds = await self._cred_manager.login()
                r = await self._http.get(
                    f"{MOXFIELD_API}{path}", headers=self._headers(creds), params=params
                )
            except RuntimeError:
                pass
        if not (200 <= r.status_code < 300):
            raise _MoxfieldHTTPError(r.status_code, r)
        return r.json()

    def _extract_deck_id(self, deck_url_or_id: str) -> str:
        m = _DECK_ID_RE.search(deck_url_or_id or "")
        return m.group(1) if m else (deck_url_or_id or "")

    def _summarize_deck(self, d: dict) -> dict:
        """Map a deck-search / deck-list item into our unified summary shape."""
        return {
            "id": d.get("publicId"),
            "name": d.get("name"),
            "format": d.get("format"),
            "author": (d.get("createdByUser") or {}).get("userName"),
            "url": d.get("publicUrl"),
            "color_identity": d.get("colorIdentity"),
            "likes": d.get("likeCount"),
            "views": d.get("viewCount"),
            "updated_at": d.get("lastUpdatedAtUtc"),
        }

    async def search_decks(
        self,
        query: str,
        fmt: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_type: str | None = None,
        sort_direction: str | None = None,
    ) -> dict:
        """Search public Moxfield decks by name. Works unauthenticated.

        The search term goes out as `deckName`. It is NOT `q` — that param is
        silently ignored by /v2/decks/search, which then returns the unfiltered
        recent-decks feed and looks like a working search returning wrong decks.

        Note `total_results` is capped at 10000 by Moxfield for broad searches;
        narrow ones return a real count.
        """
        params = {
            "deckName": (query or "")[:_MAX_QUERY_LEN],
            "pageNumber": _clamp_page(page),
            "pageSize": _clamp_page_size(page_size, 20),
        }
        if fmt and len(fmt) <= _MAX_FMT_LEN and _VALID_FMT_RE.match(fmt):
            params["fmt"] = fmt
        if sort_type in _SORT_TYPES:
            params["sortType"] = sort_type
        if sort_direction in _SORT_DIRECTIONS:
            params["sortDirection"] = sort_direction
        data = await self._get("/v2/decks/search", **params)
        return {
            "total_results": data.get("totalResults"),
            "page": data.get("pageNumber"),
            "total_pages": data.get("totalPages"),
            "decks": [self._summarize_deck(d) for d in data.get("data", [])],
        }

    async def find_deck(self, name_query: str, username: str) -> list[dict]:
        decks = await self.get_user_decks(username)
        query_lower = (name_query or "").lower()
        return [d for d in decks if query_lower in (d.get("name") or "").lower()]

    async def get_user_decks(
        self, username: str, page: int = 1, page_size: int = 50
    ) -> list[dict]:
        """List a user's public decks via the search endpoint (works unauthenticated)."""
        username = (username or "")[:_MAX_QUERY_LEN]
        if not _VALID_ID_RE.match(username):
            return []
        data = await self._get(
            "/v2/decks/search",
            authorUserNames=username,
            pageNumber=_clamp_page(page),
            pageSize=_clamp_page_size(page_size, 50),
        )
        return [self._summarize_deck(d) for d in data.get("data", [])]

    def _parse_deck(self, raw: dict) -> dict:
        """Convert raw Moxfield deck response into our unified deck object."""
        def parse_board(board_data: dict) -> list[dict]:
            return [
                {
                    "name": entry.get("card", {}).get("name"),
                    "quantity": entry.get("quantity", 0),
                }
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

    async def get_deck(self, deck_id: str, enrich_with_scryfall: "str | bool" = "lean") -> dict:
        deck_id = self._extract_deck_id(deck_id)
        if not _VALID_ID_RE.match(deck_id):
            return {"error": "invalid deck id", "deck_id": deck_id}

        try:
            raw = await self._get(f"/v2/decks/all/{deck_id}")
        except _MoxfieldHTTPError as e:
            if e.status_code == 404:
                return {"error": "deck not found", "deck_id": deck_id}
            raise

        deck = self._parse_deck(raw)

        if enrich_with_scryfall:
            full = enrich_with_scryfall == "full"
            deck = await self._enrich_deck(deck, full=full)

        return deck

    async def _enrich_deck(self, deck: dict, *, full: bool = False) -> dict:
        all_cards: list[dict] = []
        for board in deck["boards"].values():
            all_cards.extend(board)

        unique_names = list({c["name"] for c in all_cards if c.get("name")})
        scryfall_cards = await self._scryfall.get_cards_bulk(
            unique_names,
            include_all_legalities=full,
            include_all_prices=full,
        )
        # Index under both the full name and the front face: Moxfield names
        # DFCs "A // B" while a caller (or another source) may use "A" alone,
        # and Scryfall always answers with the full joined name.
        scryfall_by_name: dict[str, dict] = {}
        for c in scryfall_cards:
            name = c.get("name")
            if not name or "error" in c:
                continue
            scryfall_by_name.setdefault(name, c)
            scryfall_by_name.setdefault(_front_name(name), c)

        total_usd = 0.0
        has_price = False

        for board in deck["boards"].values():
            for card in board:
                sc = scryfall_by_name.get(card["name"]) or scryfall_by_name.get(
                    _front_name(card["name"])
                ) or {}
                card.update({k: v for k, v in sc.items() if k != "name"})
                price_str = sc.get("price_usd") if not full else (sc.get("prices") or {}).get("usd")
                if price_str:
                    try:
                        total_usd += float(price_str) * card["quantity"]
                        has_price = True
                    except (ValueError, TypeError):
                        pass

        deck["price_total_usd"] = f"{total_usd:.2f}" if has_price else None
        return deck
