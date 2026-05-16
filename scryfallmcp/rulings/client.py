import os
import re
import httpx
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scryfallmcp.scryfall.client import ScryfallClient

DEFAULT_RULES_URL = os.getenv(
    "COMPREHENSIVE_RULES_URL",
    "https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.txt",
)

# Rule number pattern: e.g. "702.19a", "601", "100.1"
_RULE_RE = re.compile(r"^(\d{3}(?:\.\d+[a-z]?)?)\.?\s", re.MULTILINE)


def _parse_rules(text: str) -> dict[str, str]:
    """Parse the plain-text comprehensive rules into {rule_number: full_line} dict."""
    rules: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        m = _RULE_RE.match(line)
        if m:
            rules[m.group(1)] = line
    return rules


class RulingsClient:
    def __init__(self, scryfall_client: "ScryfallClient"):
        self._scryfall = scryfall_client
        self._http = httpx.AsyncClient(timeout=60.0)
        self._rules: dict[str, str] | None = None  # lazy-loaded

    async def _ensure_rules(self) -> dict[str, str]:
        if self._rules is None:
            url = DEFAULT_RULES_URL
            r = await self._http.get(url)
            r.raise_for_status()
            self._rules = _parse_rules(r.text)
        return self._rules

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def search_comprehensive_rules(
        self, query: str, section: str | None = None
    ) -> list[dict]:
        """Search rules text for a query string, optionally filtered to a section."""
        rules = await self._ensure_rules()
        query_lower = query.lower()
        results = []
        for rule_num, text in rules.items():
            if section and not rule_num.startswith(section):
                continue
            if query_lower in text.lower():
                results.append({"rule": rule_num, "text": text})
        return results

    async def get_rule(self, rule_number: str) -> dict:
        """Return a specific rule by number, plus its parent rule for context."""
        rules = await self._ensure_rules()
        rule_number = rule_number.rstrip(".")
        rule_text = rules.get(rule_number)
        if not rule_text:
            return {"error": "rule_not_found", "rule": rule_number}

        # Build parent: strip last character for sub-rules (e.g., "702.19a" → "702.19")
        parent_num = None
        parent_text = None
        if re.search(r"[a-z]$", rule_number):
            parent_num = rule_number[:-1]
        elif "." in rule_number:
            parent_num = rule_number.rsplit(".", 1)[0]

        if parent_num:
            parent_text = rules.get(parent_num)

        return {
            "rule": rule_number,
            "text": rule_text,
            "parent": {"rule": parent_num, "text": parent_text} if parent_text else None,
        }

    async def get_keyword_definition(self, keyword: str) -> dict:
        """Return the comprehensive rules definition for a keyword ability."""
        rules = await self._ensure_rules()
        keyword_lower = keyword.lower()
        # Section 702 = keyword abilities; 701 = keyword actions
        matches = []
        for section in ("702", "701", "703"):
            for rule_num, text in rules.items():
                if not rule_num.startswith(section):
                    continue
                if keyword_lower in text.lower():
                    matches.append({"rule": rule_num, "text": text})

        if not matches:
            # Broader search if not found in keyword sections
            matches = [
                {"rule": rn, "text": rt}
                for rn, rt in rules.items()
                if keyword_lower in rt.lower()
            ][:10]

        return {
            "keyword": keyword,
            "definitions": matches,
        }

    async def get_card_rulings(self, card_name: str, limit: int = 5) -> list[dict] | dict:
        """Return official rulings for a card from Scryfall."""
        # First get the card to find its ID
        card = await self._scryfall.get_card_by_name(card_name, fuzzy=True)
        if "error" in card:
            return card

        # Scryfall cards have a rulings_uri — we need to fetch it directly
        # We'll use the card's oracle_id to construct the rulings URL
        card_id_data = await self._scryfall._get(
            f"/cards/named", fuzzy=card_name
        )
        rulings_uri = card_id_data.get("rulings_uri")
        if not rulings_uri:
            return {"card": card_name, "rulings": []}

        # rulings_uri is a full URL; strip the base to get the path
        path = rulings_uri.replace("https://api.scryfall.com", "")
        data = await self._scryfall._get(path)
        raw_rulings = data.get("data", [])
        if limit:
            raw_rulings = raw_rulings[-limit:]  # most recent first
        rulings = [{"date": r.get("published_at"), "text": r.get("comment")} for r in raw_rulings]
        return {"card": card_name, "rulings": rulings}

    async def explain_interaction(
        self, card_a: str, card_b: str, scenario: str | None = None
    ) -> dict:
        """Assemble oracle text, rulings, and relevant rules for two cards."""
        card_a_data = await self._scryfall.get_card_by_name(card_a, fuzzy=True)
        card_b_data = await self._scryfall.get_card_by_name(card_b, fuzzy=True)
        rulings_a = await self.get_card_rulings(card_a)
        rulings_b = await self.get_card_rulings(card_b)

        # Find potentially relevant CR sections based on keywords in oracle text
        rules_context = []
        for card_data in (card_a_data, card_b_data):
            if isinstance(card_data, dict) and "oracle_text" in card_data:
                oracle = card_data["oracle_text"] or ""
                # Search for keywords appearing in oracle text
                for kw in ("triggered", "activated", "replacement", "state-based", "stack"):
                    if kw in oracle.lower():
                        hits = await self.search_comprehensive_rules(kw, section="6")
                        rules_context.extend(hits[:3])

        return {
            "card_a": {
                "name": card_a,
                "oracle_text": card_a_data.get("oracle_text") if isinstance(card_a_data, dict) else None,
                "rulings": rulings_a.get("rulings", []) if isinstance(rulings_a, dict) else [],
            },
            "card_b": {
                "name": card_b,
                "oracle_text": card_b_data.get("oracle_text") if isinstance(card_b_data, dict) else None,
                "rulings": rulings_b.get("rulings", []) if isinstance(rulings_b, dict) else [],
            },
            "scenario": scenario,
            "relevant_rules": rules_context,
            "note": "This is a context bundle. Use the oracle text, rulings, and rules above to reason about the interaction.",
        }

    def cache_status(self) -> dict:
        return {
            "loaded": self._rules is not None,
            "rule_count": len(self._rules) if self._rules else 0,
        }

    async def refresh_rules(self) -> dict:
        """Clear the cached comprehensive rules, forcing a re-fetch on next use."""
        self._rules = None
        return {"status": "rules_cache_cleared"}
