#!/usr/bin/env python3
"""DM someone from David's own Discord account (user token, not a bot: against Discord's ToS, so keep
the volume to a handful of party invites). Token lives in ~/.config/party/discord-token (chmod 600).

    python3 discord_dm.py <discord user id> "message"
"""
import json
import os
import sys
import urllib.request

TOKEN_FILE = os.path.expanduser("~/.config/party/discord-token")
API = "https://discord.com/api/v9"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0 Safari/537.36"


def _call(method: str, path: str, body: dict) -> dict:
    with open(TOKEN_FILE) as f:
        token = f.read().strip()
    req = urllib.request.Request(API + path, json.dumps(body).encode(), method=method,
                                 headers={"Authorization": token, "Content-Type": "application/json", "User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=15))


def dm(user_id: str, text: str) -> str:
    """Send a DM; returns the message id."""
    channel = _call("POST", "/users/@me/channels", {"recipients": [user_id]})["id"]
    return _call("POST", f"/channels/{channel}/messages", {"content": text})["id"]


if __name__ == "__main__":
    print("sent", dm(sys.argv[1], sys.argv[2]))
