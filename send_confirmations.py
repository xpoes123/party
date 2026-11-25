#!/usr/bin/env python3
"""Send queued RSVP confirmation texts from the MacBook's Messages. Runs every minute from the
party-confirm.timer user unit on the desktop; a no-op while the Mac is asleep (texts wait in the queue)."""
import json
import shlex
import subprocess
import urllib.request

MAC = "david@100.111.209.2"
BASE = "https://party.djiang.xyz"
SEND = 'on run argv\ntell application "Messages" to send (item 2 of argv) to participant (item 1 of argv)\nend run'


def main():
    key = subprocess.run(["ssh", "root@87.99.136.82", "grep ^PARTY_ADMIN_KEY /opt/party/.env | cut -d= -f2-"],
                         capture_output=True, text=True, check=True).stdout.strip()
    h = {"X-Admin-Key": key}
    for m in json.load(urllib.request.urlopen(urllib.request.Request(f"{BASE}/admin/outbox", headers=h))):
        cmd = "osascript - " + shlex.join([m["phone"], m["text"]])
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", MAC, cmd], input=SEND, text=True, capture_output=True)
        if r.returncode:
            print(f"failed {m['phone']}: {r.stderr.strip()}")
            return  # Mac asleep or Messages error; retry next run
        urllib.request.urlopen(urllib.request.Request(f"{BASE}/admin/outbox/{m['id']}/sent", method="POST", headers=h))
        print(f"sent {m['phone']}: {m['text']}")


if __name__ == "__main__":
    main()
