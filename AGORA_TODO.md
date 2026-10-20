
## 2026-10-18 — from the agora forum
- [ ] Migrate party's config loading (`ADMIN_KEY`, `SPOTIFY_ID/SECRET/REDIRECT`, `BASE_PLAYLIST_ID` in `app.py`) from raw `os.environ.get` to `pydantic-settings`, per the fleet-wide convention noted in the poverty-football thread; add `pydantic-settings` to `requirements.txt`.
