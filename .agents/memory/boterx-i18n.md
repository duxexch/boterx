---
name: Boterx AR/EN i18n
description: How the site-wide Arabic/English translation layer works and its constraints
---
- Runtime: `dashboard/static/js/i18n.js` (window.I18N, localStorage `vex_lang`, ar=rtl default, floating toggle via mountToggle, MutationObserver auto-translates dynamically inserted DOM when EN active).
- Shared dictionary: `dashboard/static/js/i18n-auto.js` — ~290 keys (x000…), auto-generated once by a script that injected `data-i18n`/`data-i18n-ph` into leaf tags and swapped exact JS string literals for `I18N.t('key')` across all player templates. game-base.js has its own `gb_*` keys in `window.I18N_EXTRA`.
- **Why:** subagent delegation blocked on this account, so translation was semi-automated; the generator only converts EXACT single-quoted literals — concatenated/ternary Arabic fragments in page JS remain untranslated (follow-up exists).
- **How to apply:** to add strings, add keys to i18n-auto.js (or page-level I18N_EXTRA before i18n.js runs) and tag markup with data-i18n; never nest double quotes inside inline onclick handlers (use I18N.t('key') with single quotes).
- Matching endpoints in app.py require `g.webapp_auth_strong`; CSV writes serialized by `_MATCH_CSV_LOCK`; cancel voids the pending agent txn first and rejects if already settled.
