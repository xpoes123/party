"""Event RSVPs (Partiful-lite). Phone number is the guest identity; no login.
See docs/superpowers/specs/2026-11-24-event-rsvp-design.md."""
import os
import re
import secrets
import time
from contextlib import closing

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

import app as party

router = APIRouter()
STATUSES = {"going", "maybe", "no"}
PUBLIC_URL = os.environ.get("PARTY_PUBLIC_URL", "")  # behind Caddy, request.base_url is 127.0.0.1


def norm_phone(raw: str) -> str | None:
    d = re.sub(r"\D", "", raw or "")
    if (raw or "").strip().startswith("+") and 8 <= len(d) <= 15:
        return "+" + d
    if len(d) == 10:
        return "+1" + d
    if len(d) == 11 and d[0] == "1":
        return "+" + d
    return None


def _event(conn, slug: str):
    ev = conn.execute("SELECT * FROM events WHERE slug=?", (slug,)).fetchone()
    if not ev:
        raise HTTPException(404, "no such event")
    return ev


def _going(conn, slug: str) -> list[str]:
    rows = conn.execute("SELECT name FROM invites WHERE slug=? AND status='going' ORDER BY updated", (slug,))
    return [r["name"].split()[0] for r in rows]


@router.get("/")
def home():
    return FileResponse(os.path.join(party.STATIC, "home.html"))


@router.get("/api/events")
def events():
    with closing(party.db()) as conn:
        return [dict(r) for r in conn.execute("SELECT slug, title, starts, place FROM events ORDER BY rowid")]


@router.get("/e/{slug}")
@router.get("/e/{slug}/{token}")
def page(slug: str, token: str = ""):
    return FileResponse(os.path.join(party.STATIC, "rsvp.html"), headers={"Cache-Control": "no-store"})


@router.get("/api/e/{slug}")
def public(slug: str, t: str = ""):
    with closing(party.db()) as conn:
        ev = _event(conn, slug)
        me = conn.execute("SELECT name, status FROM invites WHERE slug=? AND token=?", (slug, t)).fetchone() if t else None
        return {"event": dict(ev), "me": dict(me) if me else None, "going": _going(conn, slug)}


@router.post("/api/e/{slug}/rsvp")
async def rsvp(slug: str, request: Request):
    body = await request.json()
    status = body.get("status")
    if status not in STATUSES:
        raise HTTPException(400, "status must be going, maybe or no")
    now = int(time.time())
    with closing(party.db()) as conn, conn:
        _event(conn, slug)
        if body.get("t"):
            cur = conn.execute("UPDATE invites SET status=?, updated=? WHERE slug=? AND token=?",
                               (status, now, slug, body["t"]))
            if not cur.rowcount:
                raise HTTPException(404, "unknown invite link")
            return {"ok": True, "token": body["t"]}
        name = (body.get("name") or "").strip()[:60]
        phone = norm_phone(body.get("phone", ""))
        if not name or not phone:
            raise HTTPException(400, "need a name and a valid phone number")
        # existing phone keeps the host's name for it and its token
        conn.execute("""INSERT INTO invites (slug, name, phone, token, status, source, updated)
                        VALUES (?, ?, ?, ?, ?, 'open', ?)
                        ON CONFLICT (slug, phone) DO UPDATE SET status=excluded.status, updated=excluded.updated""",
                     (slug, name, phone, secrets.token_urlsafe(8), status, now))
        token = conn.execute("SELECT token FROM invites WHERE slug=? AND phone=?", (slug, phone)).fetchone()["token"]
        return {"ok": True, "token": token}


# ---- host ----
@router.get("/admin/events")
def admin_page():
    return FileResponse(os.path.join(party.STATIC, "events-admin.html"), headers={"Cache-Control": "no-store"})


@router.get("/admin/events/list")
def admin_list(request: Request):
    party.require_admin(request)
    with closing(party.db()) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM events ORDER BY rowid DESC")]


@router.post("/admin/event")
async def admin_event(request: Request):
    party.require_admin(request)
    b = await request.json()
    slug = (b.get("slug") or "").strip()
    if not re.fullmatch(r"[a-z0-9-]{1,40}", slug) or not (b.get("title") or "").strip():
        raise HTTPException(400, "slug must be lowercase letters, digits, dashes; title required")
    with closing(party.db()) as conn, conn:
        conn.execute("""INSERT INTO events (slug, title, starts, place, blurb) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT (slug) DO UPDATE SET title=excluded.title, starts=excluded.starts,
                        place=excluded.place, blurb=excluded.blurb""",
                     (slug, b["title"].strip(), b.get("starts", ""), b.get("place", ""), b.get("blurb", "")))
    return {"ok": True}


@router.post("/admin/e/{slug}/invite")
async def admin_invite(slug: str, request: Request):
    """Paste `Name, phone` lines. Same phone twice = one invite."""
    party.require_admin(request)
    lines = (await request.json()).get("lines", "")
    added, skipped = 0, []
    with closing(party.db()) as conn, conn:
        _event(conn, slug)
        for line in filter(None, (l.strip() for l in lines.splitlines())):
            name, _, raw = line.rpartition(",")
            phone = norm_phone(raw)
            if not name.strip() or not phone:
                skipped.append(line)
                continue
            cur = conn.execute("INSERT OR IGNORE INTO invites (slug, name, phone, token, updated) VALUES (?, ?, ?, ?, ?)",
                               (slug, name.strip()[:60], phone, secrets.token_urlsafe(8), int(time.time())))
            added += cur.rowcount
    return {"added": added, "skipped": skipped}


@router.get("/admin/e/{slug}")
def admin_event_detail(slug: str, request: Request):
    party.require_admin(request)
    with closing(party.db()) as conn:
        ev = _event(conn, slug)
        rows = conn.execute("SELECT * FROM invites WHERE slug=? ORDER BY name COLLATE NOCASE", (slug,))
        return {"event": dict(ev), "invites": [dict(r) for r in rows]}


@router.delete("/admin/invite/{iid}")
def admin_uninvite(iid: int, request: Request):
    party.require_admin(request)
    with closing(party.db()) as conn, conn:
        conn.execute("DELETE FROM invites WHERE id=?", (iid,))
    return {"ok": True}


@router.get("/admin/e/{slug}/blast")
def blast(slug: str, request: Request, msg: str, to: str = "pending"):
    """Feed for the iOS Shortcut: one personal text per invitee. `{name}` = first name, `{link}` = their link."""
    party.require_admin(request)
    where = {"all": "", "pending": "AND status=''", "going": "AND status='going'",
             "maybe": "AND status='maybe'", "yes-maybe": "AND status IN ('going','maybe')"}
    if to not in where:
        raise HTTPException(400, f"to must be one of {', '.join(where)}")
    base = (PUBLIC_URL or str(request.base_url)).rstrip("/")
    with closing(party.db()) as conn:
        _event(conn, slug)
        rows = conn.execute(f"SELECT name, phone, token FROM invites WHERE slug=? {where[to]} ORDER BY name", (slug,))
        return [{"name": r["name"], "phone": r["phone"],
                 "text": msg.replace("{name}", r["name"].split()[0]).replace("{link}", f"{base}/e/{slug}/{r['token']}")}
                for r in rows]
