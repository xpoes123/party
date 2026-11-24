# Event RSVP (Partiful-lite)

First uses: poker 12/4, murder mystery 12/5.

## Guest side (no login)
- `/e/<slug>/<token>`: personal link. "Hey Sam", event details, three buttons (Going / Maybe / Can't).
  One tap saves. Shows the first names of who's going.
- `/e/<slug>`: open link. Name + phone + answer. Phone is the identity: same phone = same invite row,
  so re-RSVPing updates instead of duplicating. After saving, the page moves to the guest's personal link.

## Host side (`/admin/events`, existing admin key)
- Create/edit an event: slug, title, when (free text), where, blurb.
- Add invitees by pasting `Name, phone` lines. Each gets a personal token.
- Table of invitees with status, personal link, remove.
- Blast feed for an iOS Shortcut: `GET /admin/e/<slug>/blast?to=all|pending|going&msg=...`
  (admin key header) returns `[{name, phone, text}]` with `{name}` and `{link}` filled in.
  The Shortcut loops and sends each text from David's number.

## Data (party.db)
- `events(slug PK, title, starts, place, blurb)`
- `invites(id, slug, name, phone, token UNIQUE, status '' | going | maybe | no, source invite|open, updated)`,
  `UNIQUE(slug, phone)`.
- Phones normalized to `+1XXXXXXXXXX` (10 digits gets +1; 11 starting with 1 gets +).

## Not now
Plus-ones, comments, Twilio, friend-CRM invite picker (comes from `friends` later).
