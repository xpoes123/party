#!/usr/bin/env bash
# Push phone contacts (name + number only) from the MacBook's Contacts to the party app's
# /admin/people dashboard. Run from the desktop while the Mac is awake. Tags/hidden survive re-syncs.
set -euo pipefail
MAC=david@100.111.209.2
KEY=$(ssh root@87.99.136.82 "grep ^PARTY_ADMIN_KEY /opt/party/.env | cut -d= -f2-")
ssh -o BatchMode=yes "$MAC" 'for db in ~/Library/Application\ Support/AddressBook/Sources/*/AddressBook-v22.abcddb; do
  sqlite3 -readonly -separator "	" "$db" "SELECT trim(coalesce(r.ZFIRSTNAME,\"\")||\" \"||coalesce(r.ZLASTNAME,\"\")), p.ZFULLNUMBER
    FROM ZABCDRECORD r JOIN ZABCDPHONENUMBER p ON p.ZOWNER=r.Z_PK WHERE coalesce(r.ZFIRSTNAME, r.ZLASTNAME) IS NOT NULL"; done' |
  python3 -c 'import sys, json; print(json.dumps([l.rstrip("\n").split("\t", 1) for l in sys.stdin if "\t" in l]))' |
  curl -sf -H "X-Admin-Key: $KEY" -H 'Content-Type: application/json' --data-binary @- https://party.djiang.xyz/admin/contacts/sync
echo
