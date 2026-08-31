import asyncio
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

BASE_URL = "https://api.scryfall.com"
RATE_LIMIT_DELAY = 0.1  # 100ms between requests


def _is_rate_limited(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _join_faces(card: dict, field: str, sep: str) -> str | None:
    """Join a per-face field across card_faces, skipping empty values.

    Scryfall leaves several top-level fields null on multi-face cards (every
    transform / modal DFC / Adventure / split / Room) and puts the real values
    in card_faces[]. Reading the top level alone silently yields None.
    """
    values = [(f.get(field) or "").strip() for f in card.get("card_faces") or []]
    values = [v for v in values if v]
    return sep.join(values) if values else None


def _front_face(card: dict, field: str):
    """First face that carries `field` — Scryfall's own convention for combat
    stats (it copies the front face's power to the top level on Adventures).
    Kept scalar so numeric consumers don't have to parse a "3 // 5" string."""
    for face in card.get("card_faces") or []:
        val = face.get(field)
        if val is not None:
            return val
    return None


def _card_to_dict(
    card: dict,
    *,
    include_all_legalities: bool = False,
    include_all_prices: bool = False,
) -> dict:
    legalities = card.get("legalities", {})
    result: dict = {
        "name": card.get("name"),
        # Fall through to card_faces[] when Scryfall leaves the top level null.
        # oracle_text is null on EVERY multi-face layout; mana_cost only on
        # transform/modal_dfc (Adventures and splits already carry a joined one).
        "mana_cost": card.get("mana_cost") or _join_faces(card, "mana_cost", " // "),
        "cmc": card.get("cmc"),
        "type_line": card.get("type_line"),
        "oracle_text": card.get("oracle_text")
        or _join_faces(card, "oracle_text", "\n//\n"),
        "color_identity": card.get("color_identity", []),
        "keywords": card.get("keywords", []),
        "set": card.get("set"),
        "rarity": card.get("rarity"),
    }
    # Only emitted for multi-face cards: it tells a consumer which layout
    # produced a "A // B" type_line without shipping the card_faces array.
    # Omitted on normal cards — a flat "layout" on all 100 cards of a deck cost
    # ~1.7KB and tripped the payload-size guard in tests/test_payload_size.py.
    if card.get("card_faces"):
        result["layout"] = card.get("layout")
    # Omit null combat stats — not applicable to non-creatures/planeswalkers
    for field in ("power", "toughness", "loyalty"):
        val = card.get(field)
        if val is None:
            val = _front_face(card, field)
        if val is not None:
            result[field] = val
    # Legalities: single boolean by default; full object on request
    if include_all_legalities:
        result["legalities"] = legalities
    else:
        result["commander_legal"] = legalities.get("commander") == "legal"
    # Prices: usd string by default; full object on request
    if include_all_prices:
        result["prices"] = card.get("prices", {})
    else:
        result["price_usd"] = (card.get("prices") or {}).get("usd")
    return result


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
    async def _post(self, path: str, payload: dict) -> dict:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        r = await self._http.post(path, json=payload)
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def search_cards(
        self,
        query: str,
        page: int = 1,
        *,
        include_all_legalities: bool = False,
        include_all_prices: bool = False,
    ) -> list[dict] | dict:
        try:
            data = await self._get("/cards/search", q=query, page=page)
            return [
                _card_to_dict(c, include_all_legalities=include_all_legalities, include_all_prices=include_all_prices)
                for c in data.get("data", [])
            ]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card not found", "query": query}
            raise

    async def get_card_by_name(
        self,
        name: str,
        fuzzy: bool = True,
        *,
        include_all_legalities: bool = False,
        include_all_prices: bool = False,
    ) -> dict:
        param_key = "fuzzy" if fuzzy else "exact"
        try:
            data = await self._get("/cards/named", **{param_key: name})
            return _card_to_dict(data, include_all_legalities=include_all_legalities, include_all_prices=include_all_prices)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card not found", "query": name}
            raise

    async def get_card_by_set(
        self,
        set_code: str,
        collector_number: str,
        *,
        include_all_legalities: bool = False,
        include_all_prices: bool = False,
    ) -> dict:
        try:
            data = await self._get(f"/cards/{set_code}/{collector_number}")
            return _card_to_dict(data, include_all_legalities=include_all_legalities, include_all_prices=include_all_prices)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "card not found", "query": f"{set_code}/{collector_number}"}
            raise

    async def get_cards_bulk(
        self,
        names: list[str],
        *,
        include_all_legalities: bool = False,
        include_all_prices: bool = False,
    ) -> list[dict]:
        CHUNK_SIZE = 75
        semaphore = asyncio.Semaphore(3)
        chunks = [names[i:i + CHUNK_SIZE] for i in range(0, len(names), CHUNK_SIZE)]

        async def fetch_chunk(chunk: list[str]) -> list[dict]:
            async with semaphore:
                payload = {"identifiers": [{"name": n} for n in chunk]}
                data = await self._post("/cards/collection", payload)
                return [
                    _card_to_dict(c, include_all_legalities=include_all_legalities, include_all_prices=include_all_prices)
                    for c in data.get("data", [])
                ]

        results = await asyncio.gather(*[fetch_chunk(c) for c in chunks])
        return [card for batch in results for card in batch]
