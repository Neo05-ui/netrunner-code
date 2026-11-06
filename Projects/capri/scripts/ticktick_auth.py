#!/usr/bin/env python3
"""Connect Capri to TickTick. Run this once, on your own machine.

Nothing here is shared with anyone. Your client secret is read from .env,
the browser round-trip happens against ticktick.com directly, and the
resulting token is written to data/ticktick_token.json, which is gitignored.

Before running:
  1. Go to  https://developer.ticktick.com/manage  and register an app
  2. Set its redirect URI to exactly:  http://127.0.0.1:8900/callback
  3. Copy .env.example to .env and put your Client ID and Secret in it

Then:  ./.venv/bin/python scripts/ticktick_auth.py
"""
from __future__ import annotations

import base64
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REDIRECT = "http://127.0.0.1:8900/callback"
AUTH_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"
SCOPE = "tasks:read"          # read-only, deliberately. No write scope asked for.

_code: str | None = None
_state_ok = False


def load_env() -> tuple[str, str]:
    env = ROOT / ".env"
    if not env.exists():
        sys.exit("No .env file. Copy .env.example to .env and fill it in.")
    vals = {}
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"').strip("'")
    cid = vals.get("TICKTICK_CLIENT_ID", "")
    sec = vals.get("TICKTICK_CLIENT_SECRET", "")
    if not cid or not sec:
        sys.exit("TICKTICK_CLIENT_ID / TICKTICK_CLIENT_SECRET missing from .env")
    return cid, sec


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):                                   # noqa: N802
        global _code, _state_ok
        q = urllib.parse.urlparse(self.path)
        if q.path != "/callback":
            self.send_response(404); self.end_headers(); return
        params = urllib.parse.parse_qs(q.query)
        _code = (params.get("code") or [None])[0]
        _state_ok = (params.get("state") or [None])[0] == self.server.state
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<body style='background:#08060F;color:#F2ECFF;"
            b"font-family:monospace;padding:3rem'>"
            b"<h2 style='color:#FF0033'>Capri is connected.</h2>"
            b"<p>You can close this tab.</p></body>")

    def log_message(self, *a):                          # silence the server
        pass


def main() -> int:
    cid, sec = load_env()
    state = secrets.token_urlsafe(16)

    server = http.server.HTTPServer(("127.0.0.1", 8900), Handler)
    server.state = state
    threading.Thread(target=server.handle_request, daemon=True).start()

    url = f"{AUTH_URL}?" + urllib.parse.urlencode({
        "client_id": cid, "scope": SCOPE, "state": state,
        "redirect_uri": REDIRECT, "response_type": "code"})
    print("Opening your browser to approve read-only access...")
    print(f"  if it doesn't open: {url}\n")
    webbrowser.open(url)

    for _ in range(120):
        if _code:
            break
        threading.Event().wait(1)
    if not _code:
        return print("Timed out waiting for approval.") or 1
    if not _state_ok:
        return print("State mismatch — aborting rather than trusting it.") or 1

    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    body = urllib.parse.urlencode({
        "code": _code, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT, "scope": SCOPE}).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.loads(r.read())

    if "access_token" not in tok:
        return print(f"No token in response: {tok}") or 1

    out = ROOT / "data" / "ticktick_token.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tok, indent=2))
    os.chmod(out, 0o600)                     # not world-readable
    print(f"Saved to {out} (mode 600, gitignored).")
    print("Capri can now read your tasks. She cannot change them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
