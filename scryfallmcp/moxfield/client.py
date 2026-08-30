import re

import httpx
from scryfallmcp.moxfield.auth import CredentialManager, Credentials
from scryfallmcp.scryfall.client import ScryfallClient

MOXFIELD_API = "https://api2.moxfield.com"

# Extract the public deck id from a full Moxfield URL, e.g.
# https://moxfield.com/decks/abc123 -> abc123
_DECK_ID_RE = re.compile(r"moxfield\.com/decks/([A-Za-z0-9_-]+)")
# Moxfield public ids / usernames are limited to these characters. Validating
# before interpolating into a URL path guards against path/query injection.
_VALID_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Bounds to keep a single call from requesting oversized pages / queries.
_MAX_QUERY_LEN = 300
_MAX_PAGE_SIZE = 50


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
    ):
        self._cred_manager = credential_manager or CredentialManager()
        self._scryfall = scryfall_client or ScryfallClient()
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()
        await self._scryfall.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    def _headers(self, creds: Credentials | None = None) -> dict:
        """Browser-mimicking headers required to reach Moxfield's public API.

        Authentication is optional: the Authorization/Cookie pair is only
        attached when valid credentials are available (needed for private
        decks). Public read endpoints work with the browser headers alone.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
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
        r.raise_for_status()
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
        self, query: str, fmt: str | None = None, page: int = 1, page_size: int = 20
    ) -> dict:
        """Search public Moxfield decks by keyword. Works unauthenticated."""
        params = {
            "q": (query or "")[:_MAX_QUERY_LEN],
            "pageNumber": _clamp_page(page),
            "pageSize": _clamp_page_size(page_size, 20),
        }
        if fmt:
            params["fmt"] = fmt
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
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
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
        scryfall_by_name = {c["name"]: c for c in scryfall_cards if "name" in c}

        total_usd = 0.0
        has_price = False

        for board in deck["boards"].values():
            for card in board:
                sc = scryfall_by_name.get(card["name"], {})
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
