"""Party social graph — FastAPI + SQLite, single file.

Guests scan a QR, pick who they are, tap others to connect. Connecting swaps
contact info (hidden until connected) and draws an edge on a live graph.
Host controls who's `present` via /admin. See docs/superpowers/specs.
"""
import json
import os
import sqlite3
from contextlib import closing

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DB = os.path.join(os.path.dirname(__file__), "party.db")
STATIC = os.path.join(os.path.dirname(__file__), "static")
ADMIN_KEY = os.environ.get("PARTY_ADMIN_KEY", "letmein")

app = FastAPI()


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init():
    with closing(db()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                present INTEGER NOT NULL DEFAULT 1,
                contacts TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS edges (
                a INTEGER NOT NULL,
                b INTEGER NOT NULL,
                weight INTEGER NOT NULL DEFAULT 50,
                PRIMARY KEY (a, b)
            );
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                opt_a TEXT NOT NULL,
                opt_b TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS votes (
                poll_id INTEGER NOT NULL,
                guest_id INTEGER NOT NULL,
                choice TEXT NOT NULL,
                PRIMARY KEY (poll_id, guest_id)
            );
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                by_name TEXT NOT NULL DEFAULT '',
                played INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        # migrate older DBs that predate the weight column
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(edges)")]
        if "weight" not in cols:
            conn.execute("ALTER TABLE edges ADD COLUMN weight INTEGER NOT NULL DEFAULT 50")


init()


def pair(a, b):
    """Normalize an edge to (min, max) so it's undirected + unique."""
    a, b = int(a), int(b)
    if a == b:
        raise HTTPException(400, "can't connect to yourself")
    return (a, b) if a < b else (b, a)


def require_admin(request: Request):
    if request.headers.get("x-admin-key") != ADMIN_KEY:
        raise HTTPException(403, "bad admin key")


# ---- pages ----
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/wall")
def wall():
    return FileResponse(os.path.join(STATIC, "wall.html"))


@app.get("/admin")
def admin():
    # page itself is harmless HTML; the admin API endpoints are what's gated
    # (via X-Admin-Key header). no-referrer so the ?key= bootstrap can't leak.
    return FileResponse(
        os.path.join(STATIC, "admin.html"),
        headers={"Referrer-Policy": "no-referrer"},
    )


# ---- state ----
@app.get("/roster")
def roster():
    """Everyone (present or not), for the identity picker. No contacts."""
    with closing(db()) as conn:
        rows = conn.execute("SELECT id, name, present FROM guests ORDER BY name").fetchall()
    return [{"id": r["id"], "name": r["name"], "present": bool(r["present"])} for r in rows]


@app.post("/checkin/{gid}")
def checkin(gid: int):
    """Guest self-check-in — marks themselves present. Trust-based, no auth."""
    with closing(db()) as conn, conn:
        cur = conn.execute("UPDATE guests SET present=1 WHERE id=?", (gid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "no such guest")
    return {"ok": True}


@app.get("/state")
def state(me: int | None = None):
    """Present guests + edges. Contacts only revealed for `me`'s connections."""
    with closing(db()) as conn:
        guests = conn.execute(
            "SELECT id, name, contacts FROM guests WHERE present=1 ORDER BY name"
        ).fetchall()
        present_ids = {g["id"] for g in guests}
        edges = [
            {"a": r["a"], "b": r["b"], "weight": r["weight"]}
            for r in conn.execute("SELECT a, b, weight FROM edges").fetchall()
            if r["a"] in present_ids and r["b"] in present_ids
        ]
    # who is `me` connected to?
    connected = set()
    if me is not None:
        for e in edges:
            if e["a"] == me:
                connected.add(e["b"])
            elif e["b"] == me:
                connected.add(e["a"])
    out = []
    for g in guests:
        reveal = me is not None and (g["id"] == me or g["id"] in connected)
        out.append(
            {
                "id": g["id"],
                "name": g["name"],
                "connected": g["id"] in connected,
                "contacts": json.loads(g["contacts"]) if reveal else None,
            }
        )
    return {"guests": out, "edges": edges}


# ---- actions ----
@app.post("/connect")
async def connect(request: Request):
    body = await request.json()
    a, b = pair(body["a"], body["b"])
    w = max(0, min(100, int(body.get("weight", 50))))
    with closing(db()) as conn, conn:
        # OR IGNORE: a live connect never clobbers a preseeded weight
        conn.execute("INSERT OR IGNORE INTO edges (a, b, weight) VALUES (?, ?, ?)", (a, b, w))
    return {"ok": True}


@app.post("/disconnect")
async def disconnect(request: Request):
    body = await request.json()
    a, b = pair(body["a"], body["b"])
    with closing(db()) as conn, conn:
        conn.execute("DELETE FROM edges WHERE a=? AND b=?", (a, b))
    return {"ok": True}


@app.post("/profile/{gid}")
async def profile(gid: int, request: Request):
    body = await request.json()
    contacts = body.get("contacts", [])
    # keep only well-formed, non-empty rows
    clean = [
        {"label": str(c.get("label", "")).strip(), "value": str(c.get("value", "")).strip()}
        for c in contacts
        if str(c.get("value", "")).strip()
    ]
    with closing(db()) as conn, conn:
        cur = conn.execute(
            "UPDATE guests SET contacts=? WHERE id=?", (json.dumps(clean), gid)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "no such guest")
    return {"ok": True, "contacts": clean}


# ---- admin ----
@app.get("/admin/guests")
def admin_guests(request: Request):
    require_admin(request)
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id, name, present, contacts FROM guests ORDER BY name"
        ).fetchall()
    return [
        {"id": r["id"], "name": r["name"], "present": bool(r["present"]),
         "contacts": json.loads(r["contacts"])}
        for r in rows
    ]


@app.post("/admin/guest")
async def admin_add_guest(request: Request):
    require_admin(request)
    body = await request.json()
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name required")
    contacts = body.get("contacts", [])
    with closing(db()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO guests (name, contacts) VALUES (?, ?)",
            (name, json.dumps(contacts)),
        )
    return {"ok": True, "id": cur.lastrowid}


@app.post("/admin/present/{gid}")
async def admin_present(gid: int, request: Request):
    require_admin(request)
    body = await request.json()
    present = 1 if body.get("present") else 0
    with closing(db()) as conn, conn:
        cur = conn.execute("UPDATE guests SET present=? WHERE id=?", (present, gid))
        if cur.rowcount == 0:
            raise HTTPException(404, "no such guest")
    return {"ok": True}


@app.get("/admin/edges")
def admin_edges(request: Request):
    require_admin(request)
    with closing(db()) as conn:
        rows = conn.execute("SELECT a, b, weight FROM edges").fetchall()
    return [{"a": r["a"], "b": r["b"], "weight": r["weight"]} for r in rows]


@app.post("/admin/edges/set")
async def admin_set_edges(request: Request):
    """Replace all of one person's connections. body: {person, links:[{other, weight}]}.
    weight 0 (or missing) removes that edge; >0 upserts it."""
    require_admin(request)
    body = await request.json()
    person = int(body["person"])
    with closing(db()) as conn, conn:
        for link in body.get("links", []):
            a, b = pair(person, link["other"])
            w = max(0, min(100, int(link.get("weight", 0))))
            if w > 0:
                conn.execute(
                    "INSERT INTO edges (a, b, weight) VALUES (?, ?, ?) "
                    "ON CONFLICT(a, b) DO UPDATE SET weight=excluded.weight",
                    (a, b, w),
                )
            else:
                conn.execute("DELETE FROM edges WHERE a=? AND b=?", (a, b))
    return {"ok": True}


# ---- polls ----
def _poll_row(conn, p, me):
    counts = {"a": 0, "b": 0}
    for r in conn.execute("SELECT choice, COUNT(*) c FROM votes WHERE poll_id=? GROUP BY choice", (p["id"],)):
        counts[r["choice"]] = r["c"]
    mine = None
    if me is not None:
        r = conn.execute("SELECT choice FROM votes WHERE poll_id=? AND guest_id=?", (p["id"], me)).fetchone()
        mine = r["choice"] if r else None
    return {"id": p["id"], "question": p["question"], "opt_a": p["opt_a"], "opt_b": p["opt_b"],
            "a": counts["a"], "b": counts["b"], "mine": mine}


@app.get("/polls")
def polls(me: int | None = None):
    with closing(db()) as conn:
        ps = conn.execute("SELECT * FROM polls WHERE active=1 ORDER BY id").fetchall()
        return [_poll_row(conn, p, me) for p in ps]


@app.post("/polls/vote")
async def vote(request: Request):
    body = await request.json()
    choice = body.get("choice")
    if choice not in ("a", "b"):
        raise HTTPException(400, "choice must be a or b")
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO votes (poll_id, guest_id, choice) VALUES (?, ?, ?) "
            "ON CONFLICT(poll_id, guest_id) DO UPDATE SET choice=excluded.choice",
            (int(body["poll_id"]), int(body["me"]), choice),
        )
    return {"ok": True}


@app.get("/admin/polls")
def admin_polls(request: Request):
    require_admin(request)
    with closing(db()) as conn:
        ps = conn.execute("SELECT * FROM polls ORDER BY id").fetchall()
        return [{**_poll_row(conn, p, None), "active": bool(p["active"])} for p in ps]


@app.post("/admin/poll")
async def admin_add_poll(request: Request):
    require_admin(request)
    body = await request.json()
    q, a, b = body.get("question", "").strip(), body.get("opt_a", "").strip(), body.get("opt_b", "").strip()
    if not (q and a and b):
        raise HTTPException(400, "question and both options required")
    with closing(db()) as conn, conn:
        cur = conn.execute("INSERT INTO polls (question, opt_a, opt_b) VALUES (?, ?, ?)", (q, a, b))
    return {"ok": True, "id": cur.lastrowid}


@app.post("/admin/poll/{pid}")
async def admin_edit_poll(pid: int, request: Request):
    require_admin(request)
    body = await request.json()
    with closing(db()) as conn, conn:
        if body.get("delete"):
            conn.execute("DELETE FROM votes WHERE poll_id=?", (pid,))
            conn.execute("DELETE FROM polls WHERE id=?", (pid,))
        else:
            conn.execute("UPDATE polls SET active=? WHERE id=?", (1 if body.get("active") else 0, pid))
    return {"ok": True}


# ---- songs ----
@app.get("/songs")
def songs():
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM songs WHERE played=0 ORDER BY id").fetchall()
    return [{"id": r["id"], "title": r["title"], "by": r["by_name"]} for r in rows]


@app.post("/songs")
async def add_song(request: Request):
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(400, "title required")
    with closing(db()) as conn, conn:
        cur = conn.execute("INSERT INTO songs (title, by_name) VALUES (?, ?)",
                           (title[:120], body.get("by", "").strip()[:40]))
    return {"ok": True, "id": cur.lastrowid}


@app.post("/admin/song/{sid}")
async def admin_song(sid: int, request: Request):
    require_admin(request)
    body = await request.json()
    with closing(db()) as conn, conn:
        if body.get("delete"):
            conn.execute("DELETE FROM songs WHERE id=?", (sid,))
        else:
            conn.execute("UPDATE songs SET played=? WHERE id=?", (1 if body.get("played") else 0, sid))
    return {"ok": True}


# ---- pages: wall deck, scenes, welcome ----
@app.get("/welcome")
def welcome():
    return FileResponse(os.path.join(STATIC, "welcome.html"))


@app.get("/scene/{name}")
def scene(name: str):
    path = os.path.join(STATIC, "scenes", os.path.basename(name) + ".html")
    if not os.path.exists(path):
        raise HTTPException(404, "no such scene")
    return FileResponse(path)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
