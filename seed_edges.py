"""Preseed connections by name, based on who already knows who.

Fill in GROUPS (everyone in a group is connected to everyone else in it) and/or
PAIRS (one-off links). Names are case-insensitive and must exist in party.db.
Run: python seed_edges.py    (idempotent — safe to re-run)
"""
import sqlite3
from itertools import combinations

DB = "party.db"

# each group = a friend cluster where everyone knows everyone (a clique)
GROUPS = [
    # ["david", "coby", "max", "rohan"],
]

# one-off connections that aren't part of a group
PAIRS = [
    # ["stephanie", "avni"],
]


def main():
    conn = sqlite3.connect(DB)
    ids = {r[1].lower(): r[0] for r in conn.execute("SELECT id, name FROM guests")}

    wanted = set()
    for group in GROUPS:
        for a, b in combinations(group, 2):
            wanted.add((a, b))
    wanted.update(tuple(p) for p in PAIRS)

    added = skipped = 0
    for a, b in wanted:
        ia, ib = ids.get(a.lower()), ids.get(b.lower())
        if ia is None or ib is None:
            print(f"  skip (unknown name): {a} — {b}")
            skipped += 1
            continue
        lo, hi = sorted((ia, ib))
        cur = conn.execute("INSERT OR IGNORE INTO edges (a, b) VALUES (?, ?)", (lo, hi))
        added += cur.rowcount
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    print(f"added {added} new edge(s), {skipped} skipped. total edges now: {total}")


if __name__ == "__main__":
    main()
