# party

Live social graph for a birthday party. Guests scan a QR, tap who they are, and
tap others to connect — each connection unlocks contact info and lights up an
edge on a shared live graph.

## Run (local dev)

```fish
set -x PARTY_ADMIN_KEY partytime
uvicorn app:app --host 0.0.0.0 --port 7799
```

- Guest app (phones): `/` — pick your name, connect, vote in polls, request songs, edit contacts
- Wall (monitor A): `/wall` — auto-rotating scenes: graph → blob battle → live poll → song queue
- Welcome screen (monitor B): `/welcome` — big QR + live headcount + arrivals ticker.
  QR encodes this page's origin by default; override with `/welcome?url=https://party.djiang.xyz`
- Admin (control panel): `/admin?key=partytime` — guests/presence, connection weights, polls, song queue

Wall scenes live in `static/scenes/` and are served at `/scene/<name>`; the blob
battle (`/scene/blobs`) is a self-contained canvas game that names its two blobs
after random present guests.

Contacts are hidden until two people connect. `present=0` guests disappear from
the app and graph. Data lives in `party.db` (gitignored). Real-time via 2.5s
polling — no websockets.

## Test

```fish
python test_app.py
```

## Deploy (VPS — live)

Live at **https://party.djiang.xyz**. On the Hetzner VPS: `/opt/party`, systemd
unit `party.service` (uvicorn on `127.0.0.1:7786`), Caddy `reverse_proxy` block,
admin key in `/opt/party/.env`. Cloned via the `party-deploy` SSH deploy key
(`core.sshCommand` is set in the repo config).

Redeploy after pushing to `main`:

```bash
ssh root@87.99.136.82 "cd /opt/party && git pull && venv/bin/pip install -q -r requirements.txt && systemctl restart party"
```

`party.db` lives on the VPS and is not in git — guests/edges/polls/songs persist
across redeploys.
