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
                PRIMARY KEY (a, b)
            );
            """
        )


init()


def pair(a, b):
    """Normalize an edge to (min, max) so it's undirected + unique."""
    a, b = int(a), int(b)
    if a == b:
        raise HTTPException(400, "can't connect to yourself")
    return (a, b) if a < b else (b, a)


def require_admin(request: Request):
    if request.query_params.get("key") != ADMIN_KEY:
        raise HTTPException(403, "bad admin key")


# ---- pages ----
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/wall")
def wall():
    return FileResponse(os.path.join(STATIC, "wall.html"))


@app.get("/admin")
def admin(request: Request):
    require_admin(request)
    return FileResponse(os.path.join(STATIC, "admin.html"))


# ---- state ----
@app.get("/state")
def state(me: int | None = None):
    """Present guests + edges. Contacts only revealed for `me`'s connections."""
    with closing(db()) as conn:
        guests = conn.execute(
            "SELECT id, name, contacts FROM guests WHERE present=1 ORDER BY name"
        ).fetchall()
        present_ids = {g["id"] for g in guests}
        edges = [
            {"a": r["a"], "b": r["b"]}
            for r in conn.execute("SELECT a, b FROM edges").fetchall()
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
    with closing(db()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO edges (a, b) VALUES (?, ?)", (a, b))
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


app.mount("/static", StaticFiles(directory=STATIC), name="static")
