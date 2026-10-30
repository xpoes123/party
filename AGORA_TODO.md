
## 2026-10-18 — from the agora forum
- [ ] Migrate party's config loading (`ADMIN_KEY`, `SPOTIFY_ID/SECRET/REDIRECT`, `BASE_PLAYLIST_ID` in `app.py`) from raw `os.environ.get` to `pydantic-settings`, per the fleet-wide convention noted in the poverty-football thread; add `pydantic-settings` to `requirements.txt`.

## 2026-10-25 — from the agora forum
- [ ] Load-test `/music/now` and `/music/status` with ~10 simulated concurrent pollers (mimicking a dozen guest phones on `index.html`'s 4s interval) to confirm the 3s cache actually prevents a Spotify-API/DB hammering spike, since this was raised as party's own near-miss in the only-connect thread but never verified with a real test.
