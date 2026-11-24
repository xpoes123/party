"""Self-check for event RSVPs. Run: python test_rsvp.py"""
import os, tempfile

os.environ["PARTY_ADMIN_KEY"] = "testkey"
_tmp = tempfile.mkdtemp()
import app
app.DB = os.path.join(_tmp, "t.db")
app.init()

from fastapi.testclient import TestClient
from rsvp import norm_phone
c = TestClient(app.app)
AK = {"X-Admin-Key": "testkey"}


def test():
    assert norm_phone("(917) 555-0101") == "+19175550101"
    assert norm_phone("1-917-555-0101") == "+19175550101"
    assert norm_phone("+44 20 7946 0958") == "+442079460958"
    assert norm_phone("555") is None

    # admin only
    assert c.post("/admin/event", json={"slug": "poker", "title": "Poker"}).status_code == 403
    r = c.post("/admin/event", json={"slug": "poker", "title": "Poker night", "starts": "Thu 12/4 8pm",
                                    "place": "Our place", "blurb": "Bring $20"}, headers=AK)
    assert r.status_code == 200, r.text
    assert c.post("/admin/event", json={"slug": "Bad Slug!", "title": "x"}, headers=AK).status_code == 400

    # paste invitees; duplicates by phone collapse, junk lines are reported
    r = c.post("/admin/e/poker/invite", json={"lines": "Leo Park, 917-555-0101\nSam, (917) 555-0102\nLeo again, 9175550101\nnophone"},
               headers=AK).json()
    assert r["added"] == 2 and r["skipped"] == ["nophone"], r
    rows = c.get("/admin/e/poker", headers=AK).json()["invites"]
    leo = next(x for x in rows if x["phone"] == "+19175550101")
    assert leo["name"] == "Leo Park" and leo["status"] == ""

    # personal link: one tap
    pub = c.get(f"/api/e/poker?t={leo['token']}").json()
    assert pub["me"]["name"] == "Leo Park" and pub["event"]["title"] == "Poker night"
    assert "phone" not in pub["me"]  # never echo phones to guests
    assert c.post("/api/e/poker/rsvp", json={"t": leo["token"], "status": "going"}).status_code == 200
    assert c.post("/api/e/poker/rsvp", json={"t": leo["token"], "status": "party"}).status_code == 400
    assert c.post("/api/e/poker/rsvp", json={"t": "nope", "status": "going"}).status_code == 404
    assert c.get("/api/e/poker").json()["going"] == ["Leo"]

    # open link: new phone creates a row; existing phone updates it (no dupes)
    r = c.post("/api/e/poker/rsvp", json={"name": "Nina A", "phone": "917 555 0199", "status": "maybe"}).json()
    assert r["token"]
    r2 = c.post("/api/e/poker/rsvp", json={"name": "Sam O", "phone": "9175550102", "status": "no"}).json()
    rows = {x["phone"]: x for x in c.get("/admin/e/poker", headers=AK).json()["invites"]}
    assert len(rows) == 3 and rows["+19175550102"]["status"] == "no" and rows["+19175550102"]["name"] == "Sam"
    assert r2["token"] == rows["+19175550102"]["token"]
    assert rows["+19175550199"]["source"] == "open"
    assert c.post("/api/e/poker/rsvp", json={"name": "", "phone": "9175550111", "status": "going"}).status_code == 400
    assert c.post("/api/e/poker/rsvp", json={"name": "X", "phone": "12", "status": "going"}).status_code == 400

    # blast feed: templated per person, filtered by status
    b = c.get("/admin/e/poker/blast", params={"to": "pending", "msg": "Hey {name}! RSVP: {link}"}, headers=AK).json()
    assert b == [], b  # Leo going, Nina maybe, Sam no -> nobody pending
    b = c.get("/admin/e/poker/blast", params={"to": "all", "msg": "Hey {name}: {link}"}, headers=AK).json()
    assert len(b) == 3
    leo_b = next(x for x in b if x["phone"] == "+19175550101")
    assert leo_b["text"] == f"Hey Leo: http://testserver/e/poker/{leo['token']}", leo_b
    b = c.get("/admin/e/poker/blast", params={"to": "going", "msg": "see you {name}"}, headers=AK).json()
    assert [x["name"] for x in b] == ["Leo Park"]
    assert c.get("/admin/e/poker/blast", params={"to": "all", "msg": "x"}).status_code == 403

    # remove an invite
    assert c.delete(f"/admin/invite/{leo['id']}", headers=AK).status_code == 200
    assert c.get("/api/e/poker").json()["going"] == []

    # unknown event
    assert c.get("/api/e/nope").status_code == 404
    assert c.get("/e/poker").status_code == 200
    assert c.get("/").status_code == 200 and c.get("/music").status_code == 200
    assert [e["slug"] for e in c.get("/api/events").json()] == ["poker"]
    print("ok")


if __name__ == "__main__":
    test()
