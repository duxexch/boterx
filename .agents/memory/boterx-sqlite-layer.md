---
name: Boterx SQLite persistence layer
description: How database.py replaces in-memory user_states and CSV I/O in the Boterx bot
---

## Rule
`database.py` at the workspace root provides the full SQLite persistence layer. `migrate.py` is a one-time idempotent importer.

**Why:** The bot was losing all FSM states (user_states = {}) on every restart. CSV I/O had no ACID guarantees and no transactions.

## Key classes/functions
- `BotDatabase` — thread-safe SQLite wrapper, WAL mode, per-table threading.Lock, per-thread connections via threading.local
- `PersistentStateDict` — drop-in replacement for `self.user_states = {}`, backs every read/write to SQLite user_states table
- `csv_read(filename)` — reads from SQLite table; falls back to CSV file if table doesn't exist yet (backward compat)
- `csv_write(filename, rows, mode)` — writes to SQLite; mode='w' replaces, mode='a' appends
- `get_db()` — singleton, thread-safe

## How to apply
In comprehensive_bot.py:
1. `from database import get_db, PersistentStateDict` — already added
2. `self._db = get_db(); self.user_states = PersistentStateDict(self._db)` — already in __init__
3. `safe_csv_write` / `safe_csv_read` / `read_csv_helper` — already delegate to database module

Run `python3 migrate.py` once on the VPS to import existing CSV data into SQLite.
DB path defaults to boterx.db alongside the script; override with BOTERX_DB env var.

## API endpoints still needed
The 5 new game templates (mines, plinko, wheel, lottery, snatch) have complete frontends but no backend routes yet. See Task #1.
