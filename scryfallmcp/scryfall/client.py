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
