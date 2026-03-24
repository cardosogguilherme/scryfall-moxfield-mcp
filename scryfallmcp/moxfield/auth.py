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
