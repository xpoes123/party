# Party Social Graph — Design

**Date:** 2026-07-31 · **Party:** tomorrow (2026-08-01)

## Concept

A live web app for a birthday party (~20 guests at a time). A QR code on the
door and walls links to the app. A guest scans it, taps their own name to become
"themselves," then taps anyone else present to connect. Each connection appears
instantly as an edge on a shared live graph and unlocks the two people's contact
info to each other. The host (David) controls who is "present," so the active
graph only shows people actually at the party.

## Stack

- **FastAPI + SQLite**, single-file backend.
- **One HTML page** (embedded CSS + JS), screens switched client-side.
- **cytoscape.js** vendored as a local static file (no CDN — works on flaky
  party wifi).
- **Real-time via polling** `GET /state` every 2s. No websockets, no accounts.
- Hosted on the Hetzner VPS behind Caddy at `party.djiang.xyz`, systemd unit,
  git pull-to-deploy (same pattern as david-share).

## Data model (SQLite)

- **guests**: `id INTEGER PK, name TEXT, present INTEGER (0/1),
  contacts TEXT (JSON list of {label, value})`
  - `contacts` is a flexible list so guests can add/remove Instagram / Discord /
    phone / anything. David pre-fills some.
- **edges**: `a INTEGER, b INTEGER` — undirected, stored normalized as
  `a < b`, `UNIQUE(a, b)`.

## Identity

Trust-based, no auth. On "pick who you are," the chosen guest id is saved in
`localStorage`. All actions (connect, edit profile) act as that id. ~20 people,
David trusts them not to impersonate.

## Screens (single HTML, JS-switched)

1. **Pick who you are** — list of present guests; tap your name → saved to
   localStorage. Shown when no identity set.
2. **Connect** — list/grid of every *other* present guest. Tap someone → edge
   created instantly (no accept). Connected people show a ✓; their contact info
   becomes visible inline.
3. **My profile** — edit own `contacts` (add/remove rows). Also lists your
   current edges with a remove button.
4. **Graph** — live cytoscape graph, nodes = present guests, edges =
   connections. Viewable on phones. Polls /state.
5. **Wall mode** (`GET /wall`) — same graph, fullscreen, no controls, for
   David's desktop monitor. Polls /state.

## Admin (`GET /admin?key=...`)

Protected by a URL key (env var `PARTY_ADMIN_KEY`). Lets David:
- Add a guest (name + optional pre-filled contacts).
- Toggle any guest's `present` flag.

No delete-guest for v1 (toggle present off is enough). YAGNI.

## Privacy model

Contact info is **hidden until connected** — this is what makes connecting
meaningful. Names and the graph structure are visible to anyone with the link;
contact details are only returned to a viewer for guests they share an edge with.
`GET /state` therefore takes the viewer's id and only includes contacts for the
viewer's connections.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/` | The app (single HTML page) |
| GET  | `/state?me={id}` | JSON: present guests, edges, + contacts for `me`'s connections |
| POST | `/connect` `{a, b}` | Create edge (idempotent) |
| POST | `/disconnect` `{a, b}` | Remove edge |
| POST | `/profile/{id}` `{contacts}` | Replace a guest's contacts |
| GET  | `/wall` | Fullscreen graph page |
| GET  | `/admin?key=` | Admin page |
| POST | `/admin/guest?key=` `{name, contacts}` | Add guest |
| POST | `/admin/present/{id}?key=` `{present}` | Toggle presence |

## Files

- `app.py` — FastAPI app + all routes + SQLite init.
- `static/index.html` — the app (embedded CSS/JS).
- `static/wall.html` — wall-mode page served by `GET /wall`.
- `static/cytoscape.min.js` — vendored.
- `party.db` — SQLite (gitignored).
- deploy notes in README.

## Out of scope (v1 / YAGNI)

- No PINs / real auth.
- No websockets.
- No guest deletion, no edit-others'-contacts (except David via re-add).
- No party passphrase gate on the URL.
- No connection history/analytics.

## Testing

One `test_app.py` with a self-check: create guests, connect, assert edge
normalized + unique + idempotent, assert `/state` hides non-connected contacts
and reveals connected ones, assert disconnect removes the edge.
