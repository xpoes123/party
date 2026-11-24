#!/usr/bin/env bash
# Copy phone contacts (name + number only) from the homelab's iPhone-contacts mirror to the VPS,
# for the /admin/events picker. Run from the desktop whenever contacts change.
set -euo pipefail
ssh -o BatchMode=yes root@100.67.232.59 'cd /opt/homelab/omi && /opt/omi/venv/bin/python -c "
import json, texts
rows = {(\"+1\" + h): n for h, n in texts.contacts().items() if h.isdigit() and len(h) == 10}
print(json.dumps(sorted(([n, p] for p, n in rows.items()), key=lambda r: r[0].lower())))
"' | ssh root@87.99.136.82 'cat > /opt/party/contacts.json && chmod 600 /opt/party/contacts.json && python3 -c "import json;print(len(json.load(open(\"/opt/party/contacts.json\"))), \"contacts synced\")"'
