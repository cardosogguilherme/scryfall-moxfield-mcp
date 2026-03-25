#!/usr/bin/env python3
"""
Manually save Moxfield credentials extracted from your browser.

EASIEST METHOD — run this snippet in your browser console on moxfield.com:

    (function(){
      const orig = window.fetch;
      window.fetch = function(...a) {
        const h = (a[1]||{}).headers||{};
        const auth = h['Authorization'] || h['authorization'];
        if (auth && a[0].includes('api2.moxfield.com')) {
          console.log('TOKEN:', auth);
          console.log('COOKIES:', document.cookie);
          window.fetch = orig;
        }
        return orig.apply(this, a);
      };
      console.log('Interceptor ready — navigate to your decks page now');
    })()

After running it, navigate to moxfield.com/decks and the TOKEN will appear in the console.
Then paste both values here when prompted.

ALTERNATIVE — get values manually from DevTools:
  Token:   Network tab → any api2.moxfield.com request → Request Headers → Authorization
  Cookies: Application tab → Storage → Cookies → https://www.moxfield.com
           (copy Name=Value for each cookie, separated by "; ")
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

CREDENTIALS_PATH = Path(__file__).parent / "credentials.json"
DEFAULT_TTL_HOURS = int(os.getenv("CREDENTIALS_TTL_HOURS", "24"))


def parse_cookie_string(cookie_str: str) -> dict:
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def main():
    print("=== Moxfield Credential Saver ===\n")
    print("EASIEST: paste this in your browser console on moxfield.com, then go to /decks:\n")
    print("  (function(){const o=window.fetch;window.fetch=function(...a){const h=(a[1]||{}).headers||{};")
    print("  const t=h['Authorization']||h['authorization'];if(t&&a[0].includes('api2.moxfield.com'))")
    print("  {console.log('TOKEN:',t);console.log('COOKIES:',document.cookie);window.fetch=o;}")
    print("  return o.apply(this,a);};console.log('Ready — go to /decks now');})();\n")
    print("-" * 60)

    print("\nPaste your token (starts with 'Bearer '):")
    token = input("> ").strip()

    if not token.startswith("Bearer "):
        print("ERROR: Token must start with 'Bearer '. Got:", token[:30])
        sys.exit(1)

    print("\nPaste your cookies (or press Enter to skip — token-only may work):")
    print("Format: name1=value1; name2=value2")
    cookie_str = input("> ").strip()

    cookies = parse_cookie_string(cookie_str) if cookie_str else {}

    expires_at = datetime.now(timezone.utc) + timedelta(hours=DEFAULT_TTL_HOURS)

    data = {
        "token": token,
        "cookies": cookies,
        "expires_at": expires_at.isoformat(),
    }

    CREDENTIALS_PATH.write_text(json.dumps(data, indent=2))
    os.chmod(CREDENTIALS_PATH, 0o600)

    print(f"\n✓ Saved to {CREDENTIALS_PATH}")
    print(f"✓ Token: {token[:40]}...")
    print(f"✓ Cookies: {len(cookies)} saved" if cookies else "✓ Cookies: none (token-only)")
    print(f"✓ Expires: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
