---
name: Boterx dashboard frontend reliability
description: Vendor assets are self-hosted; layout is CSS-first; how to verify admin pages via server-side curl login
---

- All dashboard vendor libs (Tailwind runtime, Alpine, Chart.js, Font Awesome + webfonts) are self-hosted under `dashboard/static/vendor/`. **Why:** CDN failures (jsdelivr/cdnjs) previously broke the entire panel — Alpine not loading meant empty labels, no data, sidebar overlapping content. Never reintroduce CDN `<script>` tags in base.html.
- Sidebar/layout is CSS-first: `.vex-sidebar` off-canvas by default on mobile (`.mobile-open` slides in), visible + `.main-wrap` margin on desktop (`.lg-collapsed`/`.full` to collapse). Alpine only toggles classes; the layout must stay correct with JS disabled.
- Light mode uses `body.light-mode` CSS-var remaps in style.css; Tailwind opacity-variant classes (`bg-slate-800/80` etc.) need explicit light-mode overrides or text becomes invisible.
- CSP must include `'unsafe-eval'` in script-src: Alpine.js and the Tailwind runtime compile expressions with `new Function()`. Without it every page's JS silently dies (no data, broken sidebar, stuck popups) — this was the true root cause of the "panel shows no data / broken layout" report, not empty CSVs.
- FontAwesome webfonts must live at `dashboard/static/webfonts/` (the `all.min.css` references `../webfonts/`), not under `vendor/`. Missing → 404s and blank-square icons everywhere.
- Client stats pollers must stop on 401/403. There are THREE independent ones: base.html `fetchStats`, app.js `Notifier.check`, dashboard.html Alpine `loadStats`; plus game-base.js `loadBalance` and lottery.html state poll (403 for admins hitting user-only game APIs). Any left un-guarded spams the console forever.
- Session churn caveat when testing: without a stable `DASHBOARD_SECRET_KEY`, every dev-server restart invalidates session cookies mid-test → spurious 401s. Set a fixed key in the dev workflow before running the testing subagent.
- To verify admin pages end-to-end on the prod server: curl POST to `/vex/admin/admin` with `admin_id` (first of ADMIN_USER_IDS from systemd unit or /opt/bot/.env) + `password` (DASHBOARD_PASSWORD), cookie jar, then fetch pages/APIs. Login returns 303 on success.
- Dashboard has no local Flask/jinja2 in the Replit workspace — validate templates by deploying and curling, or `python3 -m py_compile` for backend only.

## Bot icons (شركات/وسائل الدفع)
- Telegram text must never carry raw icon URLs: use `display_icon()`; `get_company_icon()` now skips http/ paths too.
- `bot_icon` CSV column (companies + payment_methods) holds an absolute image URL shown only in the bot via `send_entity_card()` when setting `bot_icon_mode=photo`; size via `bot_icon_size` (applied at upload). Admin API: `/api/bot-icon-settings`.
- Bot caches (settings, companies, methods) now expire after 60s — panel changes reach the bot without restart.
- `append_csv` auto-migrates CSV headers when new columns appear; malformed (None-key) files are left untouched.

## Public games site (webapp)
- User-facing pages: `/home` (home.html), `/webapp/games` (games_hub.html), dedicated game routes `/webapp/{aviator,crash,dice,mines,plinko,wheel,lottery,snatch}`, `/webapp/{wallet,account,stats}`. Shared shell = `static/css/game-base.css` + `static/js/game-base.js`. base.html/style.css are ADMIN shell only.
- Live animated background: `body::before/::after` in game-base.css (z-index 0, pointer-events none) — `#app` is z-index 1 above it. home.html has its own `.bg-fx` orbs + JS spark particles. All motion honors prefers-reduced-motion.
- game_engine.get_games() has a 30s catalog cache; ALWAYS call `_gm.invalidate_games_cache()` after any games_catalog.csv mutation (add_game does it internally; admin toggle route calls it) or the list serves stale active-set.
