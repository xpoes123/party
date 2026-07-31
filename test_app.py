"""Self-check for the party graph. Run: python test_app.py"""
import os, tempfile

# use a throwaway db before importing the app
os.environ["PARTY_ADMIN_KEY"] = "testkey"
_tmp = tempfile.mkdtemp()
import app
app.DB = os.path.join(_tmp, "t.db")
app.init()

from fastapi.testclient import TestClient
c = TestClient(app.app)


AK = {"X-Admin-Key": "testkey"}


def add(name, contacts=None):
    r = c.post("/admin/guest", json={"name": name, "contacts": contacts or []}, headers=AK)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test():
    alice = add("Alice", [{"label": "insta", "value": "@alice"}])
    bob = add("Bob", [{"label": "phone", "value": "555-1234"}])
    carol = add("Carol")

    # both orderings normalize to the same edge; idempotent
    assert c.post("/connect", json={"a": bob, "b": alice}).status_code == 200
    assert c.post("/connect", json={"a": alice, "b": bob}).status_code == 200
    assert len(c.get("/state").json()["edges"]) == 1

    # privacy: alice sees bob's contacts (connected) but not carol's (not connected)
    guests = {g["name"]: g for g in c.get(f"/state?me={alice}").json()["guests"]}
    assert guests["Bob"]["connected"] and guests["Bob"]["contacts"] == [{"label": "phone", "value": "555-1234"}]
    assert not guests["Carol"]["connected"] and guests["Carol"]["contacts"] is None

    # anonymous viewer sees no contacts at all
    anon = {g["name"]: g for g in c.get("/state").json()["guests"]}
    assert anon["Alice"]["contacts"] is None

    # can't connect to self
    assert c.post("/connect", json={"a": alice, "b": alice}).status_code == 400

    # profile update replaces contacts, drops empty rows
    c.post(f"/profile/{carol}", json={"contacts": [
        {"label": "discord", "value": "carol#1"}, {"label": "x", "value": "  "}]})
    c.post("/connect", json={"a": alice, "b": carol})
    g = {x["name"]: x for x in c.get(f"/state?me={alice}").json()["guests"]}
    assert g["Carol"]["contacts"] == [{"label": "discord", "value": "carol#1"}]

    # disconnect removes the edge
    c.post("/disconnect", json={"a": alice, "b": bob})
    assert len(c.get("/state").json()["edges"]) == 1  # alice-carol remains

    # presence: hide bob -> drops from state and his edges vanish
    c.post(f"/admin/present/{bob}", json={"present": False}, headers=AK)
    s = c.get("/state").json()
    assert all(x["name"] != "Bob" for x in s["guests"])

    # admin key enforced
    assert c.get("/admin/guests").status_code == 403

    print("all checks passed ✓")


if __name__ == "__main__":
    test()
