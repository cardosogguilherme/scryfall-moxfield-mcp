import httpx

BASE_URL = "https://backend.commanderspellbook.com"


def _parse_variant(v: dict) -> dict:
    """Normalize a raw Commander Spellbook variant into a clean output object."""
    pieces = [u["card"]["name"] for u in v.get("uses", []) if u.get("card")]
    produces = [p["feature"]["name"] for p in v.get("produces", []) if p.get("feature")]
    prerequisites = " ".join(filter(None, [v.get("easyPrerequisites"), v.get("notablePrerequisites")])).strip()
    return {
        "id": v.get("id"),
        "pieces": pieces,
        "color_identity": v.get("identity", ""),
        "produces": produces,
        "steps": v.get("description", ""),
        "prerequisites": prerequisites or None,
        "legalities": v.get("legalities", {}),
        "prices": v.get("prices", {}),
    }


class CommanderSpellbookClient:
    def __init__(self):
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

    async def _get(self, path: str, **params) -> dict:
        r = await self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def _get_csrf_token(self) -> str:
        """Fetch a CSRF token for POST requests by hitting the find-my-combos endpoint."""
        r = await self._http.get("/find-my-combos/")
        data = r.json()
        token = data.get("csrfToken") or ""
        # Also persist any cookies the server set
        return token

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def find_combos_with_card(self, card_name: str) -> list[dict] | dict:
        """Return all combos that include a specific card."""
        try:
            results = []
            params: dict = {"uses": card_name, "limit": 100}
            while True:
                data = await self._get("/variants/", **params)
                results.extend(_parse_variant(v) for v in data.get("results", []))
                if not data.get("next"):
                    break
                # Extract offset from next URL for pagination
                next_url = data["next"]
                if "offset=" in next_url:
                    offset = int(next_url.split("offset=")[1].split("&")[0])
                    params["offset"] = offset
                else:
                    break
            return results
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "not_found", "query": card_name}
            raise

    async def find_combos_in_colors(
        self,
        color_identity: str,
        max_pieces: int | None = None,
        results_include: str | None = None,
        max_price_usd: float | None = None,
    ) -> list[dict] | dict:
        """Return combos legal in the given color identity, with optional filters."""
        try:
            params: dict = {"colorIdentity": color_identity.upper(), "limit": 100}
            if results_include:
                params["produces"] = results_include

            results = []
            while True:
                data = await self._get("/variants/", **params)
                for v in data.get("results", []):
                    parsed = _parse_variant(v)
                    if max_pieces and len(parsed["pieces"]) > max_pieces:
                        continue
                    if max_price_usd is not None:
                        try:
                            price = float(v.get("prices", {}).get("tcgplayer") or 0)
                            if price > max_price_usd:
                                continue
                        except (ValueError, TypeError):
                            pass
                    results.append(parsed)
                if not data.get("next"):
                    break
                next_url = data["next"]
                if "offset=" in next_url:
                    params["offset"] = int(next_url.split("offset=")[1].split("&")[0])
                else:
                    break
            return results
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                return {"error": "invalid_color_identity", "query": color_identity}
            raise

    async def find_combos_in_decklist(self, card_names: list[str]) -> list[dict]:
        """Return all combos where every piece is present in the provided card list."""
        token = await self._get_csrf_token()
        headers = {"X-CSRFTOKEN": token, "Referer": BASE_URL}
        r = await self._http.post(
            "/find-my-combos/",
            json={"cards": card_names},
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        included = data.get("results", {}).get("included", [])
        return [_parse_variant(v) for v in included]

    async def find_near_misses(
        self,
        card_names: list[str],
        missing_max: int = 1,
        color_identity: str | None = None,
    ) -> list[dict]:
        """Return combos where the deck is short by at most `missing_max` pieces."""
        token = await self._get_csrf_token()
        headers = {"X-CSRFTOKEN": token, "Referer": BASE_URL}
        body: dict = {"cards": card_names}
        if color_identity:
            body["identity"] = color_identity.upper()
        r = await self._http.post(
            "/find-my-combos/",
            json=body,
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", {})

        # almostIncluded = missing exactly 1 piece
        # almostIncludedByAddingColors = missing 1 piece but also requires new colors
        near = results.get("almostIncluded", [])
        if missing_max >= 2:
            # Commander Spellbook only surfaces 1-card misses; note this in output
            pass

        parsed = [_parse_variant(v) for v in near]
        # Annotate each near-miss with how many pieces are missing
        for item in parsed:
            deck_set = {n.lower() for n in card_names}
            missing = [p for p in item["pieces"] if p.lower() not in deck_set]
            item["missing_pieces"] = missing
        return parsed

    async def get_combo_details(self, combo_id: str) -> dict:
        """Return full details for a specific combo by ID."""
        try:
            data = await self._get(f"/variants/{combo_id}/")
            return _parse_variant(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "combo_not_found", "combo_id": combo_id}
            raise
