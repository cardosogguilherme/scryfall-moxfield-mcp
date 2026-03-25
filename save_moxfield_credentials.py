#!/usr/bin/env python3
"""
Manually save Moxfield credentials extracted from your browser.

How to get your token and cookies:
1. Open https://www.moxfield.com in your browser and log in
2. Open DevTools (F12) → Network tab
3. Filter by "api2.moxfield.com"
4. Click any request (e.g. to /v2/users/...)
5. In the Headers section, copy:
   - Authorization header value  (starts with "Bearer eyJ...")
   - Cookie header value         (long string like "_moxfield_session=...; cf_clearance=...")
6. Run this script and paste when prompted
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

CREDENTIALS_PATH = Path("credentials.json")
DEFAULT_TTL_HOURS = int(os.getenv("CREDENTIALS_TTL_HOURS", "24"))


def parse_cookie_string(cookie_str: str) -> dict:
    """Parse 'key=value; key2=value2' into a dict."""
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def main():
    print("=== Moxfield Credential Saver ===\n")
    print("Paste your Authorization header value (starts with 'Bearer '):")
    token = input("> ").strip()

    if not token.startswith("Bearer "):
        print("ERROR: Token must start with 'Bearer '. Got:", token[:30])
        sys.exit(1)

    print("\nPaste your Cookie header value:")
    cookie_str = input("> ").strip()

    cookies = parse_cookie_string(cookie_str)
    if not cookies:
        print("ERROR: Could not parse any cookies from input.")
        sys.exit(1)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=DEFAULT_TTL_HOURS)

    data = {
        "token": token,
        "cookies": cookies,
        "expires_at": expires_at.isoformat(),
    }

    CREDENTIALS_PATH.write_text(json.dumps(data, indent=2))
    os.chmod(CREDENTIALS_PATH, 0o600)

    print(f"\n✓ Saved {len(cookies)} cookie(s) to {CREDENTIALS_PATH}")
    print(f"✓ Token: {token[:40]}...")
    print(f"✓ Expires at: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"\nThe MCP server will use these credentials for the next {DEFAULT_TTL_HOURS} hours.")


if __name__ == "__main__":
    main()
