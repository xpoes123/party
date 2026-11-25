"""Event RSVPs (Partiful-lite). Phone number is the guest identity; no login.
See docs/superpowers/specs/2026-11-24-event-rsvp-design.md."""
import base64
import os
import re
import secrets
import time
from contextlib import closing
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

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


def _going(conn, slug: str, status: str = "going") -> list[str]:
    rows = conn.execute("SELECT name FROM invites WHERE slug=? AND status=? ORDER BY updated", (slug, status))
    return [r["name"].split()[0] for r in rows]


def _remember(conn, phone: str, name: str, tag: str):
    """People met through events (plus-ones, friends of friends) land in the contacts list."""
    conn.execute("INSERT OR IGNORE INTO contacts (phone, name) VALUES (?, ?)", (phone, name))
    tags = [t for t in conn.execute("SELECT tags FROM contacts WHERE phone=?", (phone,)).fetchone()["tags"].split(",") if t]
    if tag and tag not in tags:
        conn.execute("UPDATE contacts SET tags=? WHERE phone=?", (",".join(tags + [tag]), phone))


def _claim_phone(conn, slug: str, body: dict) -> tuple[str, str]:
    name = (body.get("name") or "").strip()[:60]
    phone = norm_phone(body.get("phone", ""))
    if not name or not phone:
        raise HTTPException(400, "need a name and a valid phone number")
    # A phone already on the list must use its personal link: otherwise anyone who knows a
    # guest's number could change their RSVP and read their link (and the address).
    if conn.execute("SELECT 1 FROM invites WHERE slug=? AND phone=?", (slug, phone)).fetchone():
        raise HTTPException(409, "That number is already on the list. Use the link that was texted to it.")
    return name, phone


def _uploads() -> str:
    path = os.path.join(os.path.dirname(party.DB), "uploads")
    os.makedirs(path, exist_ok=True)
    return path


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
        ev = dict(_event(conn, slug))
        row = conn.execute("SELECT * FROM invites WHERE slug=? AND token=?", (slug, t)).fetchone() if t else None
        me = None
        if row:
            guests = [r["name"] for r in conn.execute("SELECT name FROM invites WHERE via=? ORDER BY id", (row["id"],))]
            me = {"name": row["name"], "status": row["status"], "needs_info": row["phone"].startswith("?"),
                  "plus_left": max(row["plus"] - len(guests), 0), "guests": guests}
        if not me or me["needs_info"]:  # the open link is shareable; the address is for invited people only
            ev["address"] = ""
        return {"event": ev, "me": me, "going": _going(conn, slug),
                "maybe": _going(conn, slug, "maybe"), "invited": _going(conn, slug, "")}


@router.get("/api/e/{slug}/cal.ics")
def ics(slug: str, t: str = ""):
    with closing(party.db()) as conn:
        ev = _event(conn, slug)
        if not conn.execute("SELECT 1 FROM invites WHERE slug=? AND token=?", (slug, t)).fetchone():
            raise HTTPException(404, "unknown invite link")
    if not ev["at"]:
        raise HTTPException(404, "no time set yet")
    begin = datetime.strptime(ev["at"], "%Y-%m-%dT%H:%M")
    start, end = (d.strftime("%Y%m%dT%H%M%S") for d in (begin, begin + timedelta(hours=3)))  # ponytail: fixed 3h block
    base = (PUBLIC_URL or "").rstrip("/")
    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//party//rsvp//EN", "BEGIN:VEVENT",
        f"UID:{slug}@party.djiang.xyz", f"DTSTAMP:{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        f"DTSTART;TZID=America/New_York:{start}", f"DTEND;TZID=America/New_York:{end}",
        f"SUMMARY:{ev['title']}", f"LOCATION:{ev['address']}", f"URL:{base}/e/{slug}/{t}",
        "END:VEVENT", "END:VCALENDAR", ""])
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{slug}.ics"'})


@router.get("/uploads/{name}")
def upload(name: str):
    path = os.path.join(_uploads(), os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path)


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
            row = conn.execute("SELECT * FROM invites WHERE slug=? AND token=?", (slug, body["t"])).fetchone()
            if not row:
                raise HTTPException(404, "unknown invite link")
            if row["phone"].startswith("?"):  # name-only invite: the guest fills in their own number once
                name, phone = _claim_phone(conn, slug, body)
                conn.execute("UPDATE invites SET name=?, phone=? WHERE id=?", (name, phone, row["id"]))
                _remember(conn, phone, name, row["source"].removeprefix("ask:"))
            conn.execute("UPDATE invites SET status=?, updated=? WHERE id=?", (status, now, row["id"]))
            return {"ok": True, "token": body["t"]}
        name, phone = _claim_phone(conn, slug, body)
        token = secrets.token_urlsafe(8)
        conn.execute("INSERT INTO invites (slug, name, phone, token, status, source, updated) VALUES (?, ?, ?, ?, ?, 'open', ?)",
                     (slug, name, phone, token, status, now))
        return {"ok": True, "token": token}


@router.post("/api/e/{slug}/plusone")
async def plusone(slug: str, request: Request):
    """An invited guest adds their +1 (name + number). The +1 gets their own link, marked going."""
    body = await request.json()
    with closing(party.db()) as conn, conn:
        me = conn.execute("SELECT * FROM invites WHERE slug=? AND token=?", (slug, body.get("t", ""))).fetchone()
        if not me:
            raise HTTPException(404, "unknown invite link")
        used = conn.execute("SELECT COUNT(*) FROM invites WHERE via=?", (me["id"],)).fetchone()[0]
        if used >= me["plus"]:
            raise HTTPException(403, "No +1 spots left on this invite")
        name, phone = _claim_phone(conn, slug, body)
        token = secrets.token_urlsafe(8)
        conn.execute("INSERT INTO invites (slug, name, phone, token, status, source, via, updated) VALUES (?, ?, ?, ?, 'going', 'plus1', ?, ?)",
                     (slug, name, phone, token, me["id"], int(time.time())))
        _remember(conn, phone, name, "plus-one")
        return {"ok": True, "token": token}


# ---- host ----
@router.get("/admin/events")
def admin_page():
    return FileResponse(os.path.join(party.STATIC, "events-admin.html"), headers={"Cache-Control": "no-store"})


@router.get("/admin/people")
def people_page():
    return FileResponse(os.path.join(party.STATIC, "people.html"), headers={"Cache-Control": "no-store"})


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
    at = b.get("at", "")
    if at and not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d", at):
        raise HTTPException(400, "at must be YYYY-MM-DDTHH:MM")
    with closing(party.db()) as conn, conn:
        conn.execute("""INSERT INTO events (slug, title, starts, place, blurb, at, address, host) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (slug) DO UPDATE SET title=excluded.title, starts=excluded.starts, place=excluded.place,
                        blurb=excluded.blurb, at=excluded.at, address=excluded.address, host=excluded.host""",
                     (slug, b["title"].strip(), b.get("starts", ""), b.get("place", ""), b.get("blurb", ""),
                      at, b.get("address", ""), b.get("host", "")))
    return {"ok": True}


@router.post("/admin/e/{slug}/cover")
async def admin_cover(slug: str, request: Request):
    """Body {data: 'data:image/jpeg;base64,...'} from the admin page's file picker."""
    party.require_admin(request)
    m = re.fullmatch(r"data:image/(jpeg|png|webp|gif);base64,(.+)", (await request.json()).get("data", ""), re.S)
    if not m:
        raise HTTPException(400, "send a jpeg/png/webp/gif data URL")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 8_000_000:
        raise HTTPException(400, "image over 8MB")
    name = f"{slug}-{secrets.token_hex(4)}.{m.group(1).replace('jpeg', 'jpg')}"
    with open(os.path.join(_uploads(), name), "wb") as f:
        f.write(raw)
    with closing(party.db()) as conn, conn:
        _event(conn, slug)
        conn.execute("UPDATE events SET cover=? WHERE slug=?", (f"/uploads/{name}", slug))
    return {"cover": f"/uploads/{name}"}


@router.post("/admin/e/{slug}/invite")
async def admin_invite(slug: str, request: Request):
    """Paste `Name, phone` lines. `Name, @discord` = Discord-only guest. `Name, ?tag` = guest fills in their own
    number on first RSVP and is saved to contacts with that tag. Same phone twice = one invite."""
    party.require_admin(request)
    lines = (await request.json()).get("lines", "")
    added, skipped = 0, []
    with closing(party.db()) as conn, conn:
        _event(conn, slug)
        for line in filter(None, (l.strip() for l in lines.splitlines())):
            name, _, raw = line.rpartition(",")
            raw = raw.strip()
            # ponytail: Discord guests reuse the phone column as their unique key; you DM them the link yourself
            phone = raw.lower() if re.fullmatch(r"@[\w.]{2,32}", raw) else norm_phone(raw)
            source = "invite"
            if raw.startswith("?"):  # unique placeholder until the guest claims it
                phone, source = "?" + secrets.token_hex(4), "ask:" + re.sub(r"[^a-z0-9-]", "", raw[1:].lower())
            if not name.strip() or not phone:
                skipped.append(line)
                continue
            cur = conn.execute("INSERT OR IGNORE INTO invites (slug, name, phone, token, source, updated) VALUES (?, ?, ?, ?, ?, ?)",
                               (slug, name.strip()[:60], phone, secrets.token_urlsafe(8), source, int(time.time())))
            added += cur.rowcount
    return {"added": added, "skipped": skipped}


@router.post("/admin/contacts/sync")
async def admin_contacts_sync(request: Request):
    """[[name, raw phone], ...] from sync_contacts.sh. Refreshes names; keeps tags and hidden."""
    party.require_admin(request)
    rows = {}
    for name, raw in await request.json():
        if (phone := norm_phone(raw)) and (name or "").strip():
            rows.setdefault(phone, name.strip()[:60])
    with closing(party.db()) as conn, conn:
        conn.executemany("INSERT INTO contacts (phone, name) VALUES (?, ?) ON CONFLICT (phone) DO UPDATE SET name=excluded.name",
                         rows.items())
    return {"synced": len(rows)}


@router.get("/admin/contacts")
def admin_contacts(request: Request):
    party.require_admin(request)
    with closing(party.db()) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM contacts ORDER BY name COLLATE NOCASE")]


@router.post("/admin/contact")
async def admin_contact(request: Request):
    """{phone, tags?: 'poker,trivia', hidden?: bool}"""
    party.require_admin(request)
    b = await request.json()
    with closing(party.db()) as conn, conn:
        if "tags" in b:
            tags = ",".join(dict.fromkeys(t.strip().lower() for t in b["tags"].split(",") if t.strip()))
            conn.execute("UPDATE contacts SET tags=? WHERE phone=?", (tags, b["phone"]))
        if "hidden" in b:
            conn.execute("UPDATE contacts SET hidden=? WHERE phone=?", (int(bool(b["hidden"])), b["phone"]))
    return {"ok": True}


@router.get("/admin/e/{slug}")
def admin_event_detail(slug: str, request: Request):
    party.require_admin(request)
    with closing(party.db()) as conn:
        ev = _event(conn, slug)
        rows = conn.execute("SELECT * FROM invites WHERE slug=? ORDER BY name COLLATE NOCASE", (slug,))
        return {"event": dict(ev), "invites": [dict(r) for r in rows]}


@router.post("/admin/invite/{iid}")
async def admin_invite_plus(iid: int, request: Request):
    party.require_admin(request)
    plus = int((await request.json()).get("plus", 0))
    with closing(party.db()) as conn, conn:
        conn.execute("UPDATE invites SET plus=? WHERE id=?", (min(max(plus, 0), 5), iid))
    return {"ok": True}


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
        rows = conn.execute(f"SELECT name, phone, token FROM invites WHERE slug=? AND phone NOT LIKE '@%' AND phone NOT LIKE '?%' {where[to]} ORDER BY name", (slug,))
        return [{"name": r["name"], "phone": r["phone"],
                 "text": msg.replace("{name}", r["name"].split()[0]).replace("{link}", f"{base}/e/{slug}/{r['token']}")}
                for r in rows]
