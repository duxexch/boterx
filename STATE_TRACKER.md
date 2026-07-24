# State Tracker — LangSense / DUX Bot

> Quick reference for current development state and next actions.

---

## Current Status: ANALYZED — Ready for Development

### Completed
- [x] Full project deep analysis (all 6606 lines of comprehensive_bot.py read)
- [x] PROJECT_BRAIN.md created (project identity, file inventory, architecture, known issues, team perspective)
- [x] ARCHITECTURE.md created (system diagrams, data flows, state machine, admin router map, data relationships, migration path)
- [x] DEV_GUIDE.md created (coding conventions, patterns, testing checklist, modification rules)
- [x] CHANGELOG.md created (historical timeline + template)
- [x] Codely CLI skill `langsense-dev` created
- [x] Project memories saved (3 entries: project overview, critical bugs, dev rules)

### Available for Next Actions

#### Quick wins (bug fixes):
1. Remove `print("🔍 DEBUG BOT_TOKEN:...")` from comprehensive_bot.py line ~18
2. Remove duplicate `💾 نسخة احتياطية فورية` from `admin_keyboard()`
3. Fix `handle_language_change()` to include `currency` column in fieldnames
4. Fix `ban_user_admin()` / `unban_user_admin()` to include `currency` column
5. Deduplicate `get_all_payment_methods()` (two definitions with different logic)

#### Medium tasks:
6. Add file locking for CSV writes (threading.Lock per file)
7. Refactor `handle_admin_actions()` from if/elif chain to dispatch table
8. Extract CSV operations into a data layer module
9. Add `requirements.txt` with actual dependencies
10. Move inline translations to translation files (or consolidate)

#### Large tasks:
11. Complete Aiogram v3 version with all features from comprehensive_bot.py
12. Migrate CSV → SQLite/PostgreSQL
13. Add automated tests (pytest)
14. Add CI/CD pipeline
15. Archive/remove legacy bot files

### File Locations
| Document | Path |
|----------|------|
| Project Brain | `C:\Users\gnz\Downloads\bot2\bot\PROJECT_BRAIN.md` |
| Architecture | `C:\Users\gnz\Downloads\bot2\bot\ARCHITECTURE.md` |
| Dev Guide | `C:\Users\gnz\Downloads\bot2\bot\DEV_GUIDE.md` |
| Changelog | `C:\Users\gnz\Downloads\bot2\bot\CHANGELOG.md` |
| State Tracker | `C:\Users\gnz\Downloads\bot2\bot\STATE_TRACKER.md` |
| Skill | `~/.codely/Default/.codely-cli/skills/langsense-dev/SKILL.md` |
