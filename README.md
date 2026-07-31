# party

Live social graph for a birthday party. Guests scan a QR, tap who they are, and
tap others to connect — each connection unlocks contact info and lights up an
edge on a shared live graph.

## Run (local dev)

```fish
set -x PARTY_ADMIN_KEY partytime
uvicorn app:app --host 0.0.0.0 --port 7799
```

- Guest app: `/`
- Wall (fullscreen graph for a monitor/TV): `/wall`
- Admin (add guests, toggle who's present): `/admin?key=partytime`

Contacts are hidden until two people connect. `present=0` guests disappear from
the app and graph. Data lives in `party.db` (gitignored). Real-time via 2.5s
polling — no websockets.

## Test

```fish
python test_app.py
```

## Deploy (VPS, later)

Add a Caddy block for `party.djiang.xyz` → `reverse_proxy 127.0.0.1:7799`, run
under systemd with `PARTY_ADMIN_KEY` set to something private, git pull to
deploy. Point the door QR at `https://party.djiang.xyz`.
