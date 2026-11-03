# party

## UI / design system (shared, do not fork)
- All styling comes from the shared sheet in `xpoes123/toolkit` -> `web/ui/` (local clone `~/code/toolkit`, VPS `/opt/toolkit`). Link it first in `<head>`: same-origin `/ui/ui.css` where the app serves it (finance, david-share), else `https://share.djiang.xyz/ui/ui.css`. Never vendor or copy it, and never hardcode palette hex.
- Use semantic tokens (`var(--bg|--surface|--surface-2|--line|--line-2|--text|--text-2|--muted|--accent|--ok|--bad|--warn|--info)`), scales (`--space-*`, `--radius*`, `--text-*`) and `ui-*` components (`ui-btn`, `ui-card`, `ui-stat`, `ui-pill`, `ui-flex`, `ui-stack`, ...). Theme = `data-theme` attribute; default is `davidj`.
- **Need a color, component, variant or asset that doesn't exist? Add it to toolkit `web/ui/`, not locally.** Edit tokens/themes/`components.css`, run `web/ui/check.sh <dir>`, commit + push toolkit, then `ssh root@87.99.136.82 'git -C /opt/toolkit pull'` (live within 5 min cache). Local one-off CSS is for layout of that page only.
- Public/branded products (scibowl-org, davidJ, poverty-football, redherring, tv, games) keep their own look and opt out.
