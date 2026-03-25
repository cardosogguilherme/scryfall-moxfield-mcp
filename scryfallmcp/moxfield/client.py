import httpx
from scryfallmcp.moxfield.auth import CredentialManager, Credentials

MOXFIELD_API = "https://api2.moxfield.com"


class MoxfieldClient:
    def __init__(self, credential_manager: CredentialManager | None = None):
        self._cred_manager = credential_manager or CredentialManager()
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

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
