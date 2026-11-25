#!/usr/bin/env python3
"""Send queued RSVP confirmation texts from the MacBook's Messages, and add contacts made at events
(plus-ones etc.) to the Mac's Contacts, which syncs to the iPhone. Runs every minute from the
party-confirm.timer user unit on the desktop; a no-op while the Mac is asleep (texts wait in the queue)."""
import json
import shlex
import subprocess
import time
import urllib.request

from discord_dm import dm

MAC = "david@100.111.209.2"
BASE = "https://party.djiang.xyz"
# Messages silently drops a send it can't route (non-iMessage number, no SMS forwarding), so every send is
# checked against chat.db. Green-bubble SMS needs Text Message Forwarding (iPhone -> this Mac) turned on.
SEND = {svc: 'on run argv\ntell application "Messages" to send (item 2 of argv) to participant (item 1 of argv)'
             f' of (1st account whose service type = {svc})\nend run' for svc in ("iMessage", "SMS")}
CHAT = "sqlite3 ~/Library/Messages/chat.db "
ADD = """on run argv
tell application "Contacts"
set p to make new person with properties {first name:item 1 of argv, last name:item 2 of argv}
make new phone at end of phones of p with properties {label:"mobile", value:item 3 of argv}
save
end tell
end run"""


def mac(script: str, *args: str) -> bool:
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", MAC, "osascript - " + shlex.join(args)],
                           input=script, text=True, capture_output=True, timeout=90)
    except subprocess.TimeoutExpired:  # e.g. macOS waiting on an "allow access" prompt
        print(f"mac timed out {args[0]}")
        return False
    if r.returncode:
        print(f"mac failed {args[0]}: {r.stderr.strip()}")
    return not r.returncode


def sql(q: str) -> str:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", MAC, CHAT + shlex.quote(q)],
                       capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def delivered(phone: str, text: str) -> bool:
    for svc in ("iMessage", "SMS"):
        before = sql("SELECT max(ROWID) FROM message") or "0"
        mac(SEND[svc], phone, text)
        time.sleep(8)
        if sql(f"SELECT count(*) FROM message m JOIN handle h ON h.ROWID=m.handle_id WHERE m.ROWID>{int(before)} "
               f"AND m.is_from_me=1 AND m.error=0 AND h.id LIKE '%{''.join(filter(str.isdigit, phone))[-10:]}'") not in ("", "0"):
            return True
    return False


def main():
    key = subprocess.run(["ssh", "root@87.99.136.82", "grep ^PARTY_ADMIN_KEY /opt/party/.env | cut -d= -f2-"],
                         capture_output=True, text=True, check=True).stdout.strip()
    h = {"X-Admin-Key": key}
    get = lambda path: json.load(urllib.request.urlopen(urllib.request.Request(BASE + path, headers=h)))
    post = lambda path, body=None: urllib.request.urlopen(urllib.request.Request(
        BASE + path, json.dumps(body or {}).encode(), {**h, "Content-Type": "application/json"}))
    for m in get("/admin/outbox"):
        if m["phone"].startswith("@"):  # Discord guest invited as `Name, @<user id>`
            dm(m["phone"][1:], m["text"])
            post(f"/admin/outbox/{m['id']}/sent")
            print(f"DMed {m['phone']}: {m['text']}")
        elif delivered(m["phone"], m["text"]):
            post(f"/admin/outbox/{m['id']}/sent")
            print(f"sent {m['phone']}: {m['text']}")
        else:  # ponytail: retried every minute until it goes through; fine at party scale
            print(f"NOT delivered {m['phone']} (no iMessage, and SMS forwarding unavailable?)")
    for c in get("/admin/contacts/new"):
        first, _, last = c["name"].partition(" ")
        if not mac(ADD, first, last, c["phone"]):
            return
        post("/admin/contacts/new/done", {"phone": c["phone"]})
        print(f"added contact {c['name']} {c['phone']}")


if __name__ == "__main__":
    main()
