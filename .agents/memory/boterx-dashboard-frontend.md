---
name: Boterx dashboard frontend reliability
description: Vendor assets are self-hosted; layout is CSS-first; how to verify admin pages via server-side curl login
---

- All dashboard vendor libs (Tailwind runtime, Alpine, Chart.js, Font Awesome + webfonts) are self-hosted under `dashboard/static/vendor/`. **Why:** CDN failures (jsdelivr/cdnjs) previously broke the entire panel — Alpine not loading meant empty labels, no data, sidebar overlapping content. Never reintroduce CDN `<script>` tags in base.html.
- Sidebar/layout is CSS-first: `.vex-sidebar` off-canvas by default on mobile (`.mobile-open` slides in), visible + `.main-wrap` margin on desktop (`.lg-collapsed`/`.full` to collapse). Alpine only toggles classes; the layout must stay correct with JS disabled.
- Light mode uses `body.light-mode` CSS-var remaps in style.css; Tailwind opacity-variant classes (`bg-slate-800/80` etc.) need explicit light-mode overrides or text becomes invisible.
- To verify admin pages end-to-end on the prod server: curl POST to `/vex/admin/admin` with `admin_id` (first of ADMIN_USER_IDS from systemd unit or /opt/bot/.env) + `password` (DASHBOARD_PASSWORD), cookie jar, then fetch pages/APIs. Login returns 303 on success.
- Dashboard has no local Flask/jinja2 in the Replit workspace — validate templates by deploying and curling, or `python3 -m py_compile` for backend only.
