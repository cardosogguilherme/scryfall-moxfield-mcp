import re
import httpx

BASE_URL = "https://json.edhrec.com/pages"


def _to_slug(name: str) -> str:
    """Convert a card/commander name to an EDHREC URL slug.

    Examples:
        "Krenko, Mob Boss"      → "krenko-mob-boss"
        "Atraxa, Praetors' Voice" → "atraxa-praetors-voice"
    """
    slug = name.lower()
    slug = slug.replace("'", "").replace(",", "")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


def _parse_cardview(cv: dict) -> dict:
    potential = cv.get("potential_decks") or 1
    inclusion = cv.get("inclusion") or cv.get("num_decks") or 0
    inclusion_pct = round(inclusion / potential * 100, 1) if potential else None
    return {
        "name": cv.get("name"),
        "inclusion_percent": inclusion_pct,
        "synergy_score": cv.get("synergy"),
        "num_decks": inclusion,
        "potential_decks": potential,
        "trend_zscore": cv.get("trend_zscore"),
    }


class EDHRecClient:
    def __init__(self):
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

    async def _get(self, path: str) -> dict:
        r = await self._http.get(path)
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _fetch_commander_page(self, commander_name: str, theme: str | None = None) -> dict:
        slug = _to_slug(commander_name)
        path = f"/commanders/{slug}.json" if not theme else f"/commanders/{slug}/{_to_slug(theme)}.json"
        try:
            return await self._get(path)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {}
            raise

    async def get_commander_recommendations(
        self,
        commander_name: str,
        theme: str | None = None,
        budget: str | None = None,
    ) -> list[dict] | dict:
        """Return cards grouped by category for a commander, optionally filtered by theme."""
        data = await self._fetch_commander_page(commander_name, theme)
        if not data:
            return {"error": "commander_not_found", "query": commander_name}

        cardlists = (
            data.get("container", {}).get("json_dict", {}).get("cardlists")
            or data.get("cardlists")
            or []
        )

        result = []
        for cl in cardlists:
            header = cl.get("header") or cl.get("tag") or ""
            cards = [_parse_cardview(cv) for cv in cl.get("cardviews", [])]

            if budget == "budget":
                cards = [c for c in cards if c.get("synergy_score") is not None]
            elif budget == "expensive":
                cards = [c for c in cards if c.get("synergy_score") is not None]

            result.append({"category": header, "cards": cards})

        return result

    async def get_commander_themes(self, commander_name: str) -> list[dict] | dict:
        """Return available themes/tags for a commander."""
        data = await self._fetch_commander_page(commander_name)
        if not data:
            return {"error": "commander_not_found", "query": commander_name}

        taglinks = (
            data.get("panels", {}).get("taglinks")
            or data.get("container", {}).get("json_dict", {}).get("panels", {}).get("taglinks")
            or []
        )

        return [
            {
                "theme": tl.get("value"),
                "slug": tl.get("slug"),
                "deck_count": tl.get("count"),
            }
            for tl in taglinks
        ]

    async def get_card_top_commanders(self, card_name: str) -> list[dict] | dict:
        """Return commanders that most frequently run this card."""
        slug = _to_slug(card_name)
        try:
            data = await self._get(f"/cards/{slug}.json")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card_not_found", "query": card_name}
            raise

        # The card page has a "commanders" section in its cardlists or a dedicated field
        card_data = (
            data.get("container", {}).get("json_dict", {})
            or data
        )
        commanders = card_data.get("commanders") or card_data.get("topcommanders") or []

        if isinstance(commanders, list):
            return [
                {
                    "name": c.get("name"),
                    "inclusion_percent": c.get("inclusion"),
                    "num_decks": c.get("num_decks"),
                }
                for c in commanders
            ]

        # Fall back to cardlists if dedicated commanders list not present
        cardlists = card_data.get("cardlists") or []
        for cl in cardlists:
            header = (cl.get("header") or "").lower()
            if "commander" in header:
                return [_parse_cardview(cv) for cv in cl.get("cardviews", [])]

        return []

    async def get_average_deck(
        self, commander_name: str, theme: str | None = None
    ) -> list[dict] | dict:
        """Return the statistical average 99-card decklist for a commander."""
        data = await self._fetch_commander_page(commander_name, theme)
        if not data:
            return {"error": "commander_not_found", "query": commander_name}

        cardlists = (
            data.get("container", {}).get("json_dict", {}).get("cardlists")
            or data.get("cardlists")
            or []
        )

        # "Top Cards" category represents the most-played cards (average deck baseline)
        for cl in cardlists:
            header = (cl.get("header") or cl.get("tag") or "").lower()
            if "top" in header:
                return [_parse_cardview(cv) for cv in cl.get("cardviews", [])]

        # Fallback: return all cards from all categories flattened
        all_cards = []
        for cl in cardlists:
            all_cards.extend(_parse_cardview(cv) for cv in cl.get("cardviews", []))
        return all_cards

    async def get_budget_alternatives(
        self, card_name: str, max_price_usd: float | None = None
    ) -> list[dict] | dict:
        """Return functionally similar, cheaper cards for a given card."""
        slug = _to_slug(card_name)
        try:
            data = await self._get(f"/cards/{slug}.json")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card_not_found", "query": card_name}
            raise

        card_data = (
            data.get("container", {}).get("json_dict", {})
            or data
        )

        # Look for similar/budget card sections in cardlists
        cardlists = card_data.get("cardlists") or []
        alternatives = []
        for cl in cardlists:
            header = (cl.get("header") or cl.get("tag") or "").lower()
            if any(kw in header for kw in ("similar", "budget", "upgrade")):
                alternatives.extend(_parse_cardview(cv) for cv in cl.get("cardviews", []))

        # If no dedicated section, fall back to all cards with high synergy
        if not alternatives:
            for cl in cardlists:
                for cv in cl.get("cardviews", []):
                    parsed = _parse_cardview(cv)
                    if (parsed.get("synergy_score") or 0) > 0.2:
                        alternatives.append(parsed)

        return alternatives
