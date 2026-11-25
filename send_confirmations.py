#!/usr/bin/env python3
"""Send queued RSVP confirmation texts from the MacBook's Messages, and add contacts made at events
(plus-ones etc.) to the Mac's Contacts, which syncs to the iPhone. Runs every minute from the
party-confirm.timer user unit on the desktop; a no-op while the Mac is asleep (texts wait in the queue)."""
import json
import shlex
import subprocess
import urllib.request

MAC = "david@100.111.209.2"
BASE = "https://party.djiang.xyz"
SEND = 'on run argv\ntell application "Messages" to send (item 2 of argv) to participant (item 1 of argv)\nend run'
ADD = """on run argv
tell application "Contacts"
set p to make new person with properties {first name:item 1 of argv, last name:item 2 of argv}
make new phone at end of phones of p with properties {label:"mobile", value:item 3 of argv}
save
end tell
end run"""


def mac(script: str, *args: str) -> bool:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", MAC, "osascript - " + shlex.join(args)],
                       input=script, text=True, capture_output=True)
    if r.returncode:
        print(f"mac failed {args[0]}: {r.stderr.strip()}")
    return not r.returncode


def main():
    key = subprocess.run(["ssh", "root@87.99.136.82", "grep ^PARTY_ADMIN_KEY /opt/party/.env | cut -d= -f2-"],
                         capture_output=True, text=True, check=True).stdout.strip()
    h = {"X-Admin-Key": key}
    get = lambda path: json.load(urllib.request.urlopen(urllib.request.Request(BASE + path, headers=h)))
    post = lambda path, body=None: urllib.request.urlopen(urllib.request.Request(
        BASE + path, json.dumps(body or {}).encode(), {**h, "Content-Type": "application/json"}))
    for m in get("/admin/outbox"):
        if not mac(SEND, m["phone"], m["text"]):
            return  # Mac asleep or Messages error; retry next run
        post(f"/admin/outbox/{m['id']}/sent")
        print(f"sent {m['phone']}: {m['text']}")
    for c in get("/admin/contacts/new"):
        first, _, last = c["name"].partition(" ")
        if not mac(ADD, first, last, c["phone"]):
            return
        post("/admin/contacts/new/done", {"phone": c["phone"]})
        print(f"added contact {c['name']} {c['phone']}")


if __name__ == "__main__":
    main()
