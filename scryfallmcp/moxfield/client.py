import httpx
from scryfallmcp.moxfield.auth import CredentialManager, Credentials
from scryfallmcp.scryfall.client import ScryfallClient

MOXFIELD_API = "https://api2.moxfield.com"


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
        # Collect all unique card names across all boards
        all_cards: list[dict] = []
        for board in deck["boards"].values():
            all_cards.extend(board)

        unique_names = list({c["name"] for c in all_cards if c.get("name")})
        scryfall_cards = await self._scryfall.get_cards_bulk(unique_names)
        scryfall_by_name = {c["name"]: c for c in scryfall_cards if "name" in c}

        total_usd = 0.0
        has_price = False

        for board in deck["boards"].values():
            for card in board:
                sc = scryfall_by_name.get(card["name"], {})
                card.update({k: v for k, v in sc.items() if k != "name"})
                price_str = sc.get("prices", {}).get("usd")
                if price_str:
                    try:
                        total_usd += float(price_str) * card["quantity"]
                        has_price = True
                    except (ValueError, TypeError):
                        pass

        deck["price_total_usd"] = f"{total_usd:.2f}" if has_price else None
        return deck
