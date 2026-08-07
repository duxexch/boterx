#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate.py — One-time migration from CSV files to SQLite.

Usage:
    python migrate.py           # skip tables that already have data
    python migrate.py --force   # re-import everything (clears existing data)
"""
import os
import sys
import csv
import logging
from collections import OrderedDict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger('boterx.migrate')

# Change to script directory so relative CSV paths work
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from database import get_db, _table_name, _read_csv_file

# All CSV files to migrate
CSV_FILES = [
    'users.csv',
    'transactions.csv',
    'companies.csv',
    'payment_methods.csv',
    'complaints.csv',
    'system_settings.csv',
    'button_labels.csv',
    'admin_actions_log.csv',
    'svrp_credits.csv',
    'svrp_wallets.csv',
    'user_company_accounts.csv',
    'bonus_requests.csv',
    'recovery_requests.csv',
    'app_links.csv',
    'referrals.csv',
    'user_activity.csv',
    'referral_log.csv',
    'wheel_rounds.csv',
    'wheel_spins.csv',
    'wheel_gifts.csv',
    'lottery_rounds.csv',
    'lottery_tickets.csv',
    'lottery_winners.csv',
    'bot_channels.csv',
    'exchange_addresses.csv',
    'trade_orders.csv',
    'referral_links.csv',
    'company_payment_links.csv',
    'payment_method_steps.csv',
    'sticker_library.csv',
    'text_replacements.csv',
    'source_channels.csv',
    'daily_reports.csv',
    'ai_processed_posts.csv',
    'marketing_plans.csv',
    'bot_tokens.csv',
]


def migrate(force: bool = False):
    db = get_db()
    db.ensure_initialized()

    total_tables = 0
    total_rows = 0
    skipped = 0

    for csv_file in CSV_FILES:
        csv_path = os.path.join(SCRIPT_DIR, csv_file)
        table = _table_name(csv_file)

        if not os.path.exists(csv_path):
            logger.debug("Skipping %s — file not found", csv_file)
            continue

        # Check if table already has data
        existing_rows = db.get_row_count(table)
        if existing_rows > 0 and not force:
            logger.info("  SKIP  %-40s (table '%s' already has %d rows)", csv_file, table, existing_rows)
            skipped += 1
            continue

        # Read CSV
        rows = _read_csv_file(csv_path)
        if not rows:
            logger.info("  EMPTY %-40s (no rows in CSV)", csv_file)
            total_tables += 1
            continue

        fieldnames = list(rows[0].keys())

        # Force mode: clear existing data
        if force and existing_rows > 0:
            db._ensure_table(table, fieldnames)
            db._conn().execute(f'DELETE FROM "{table}"')
            db._conn().commit()

        # Import
        count = db.import_csv_file(csv_file, csv_path)
        total_tables += 1
        total_rows += count
        logger.info("  OK    %-40s → %d rows → table '%s'", csv_file, count, table)

    print()
    if skipped:
        print(f"Skipped {skipped} tables (already have data). Use --force to re-import.")
    print(f"Migration complete: {total_tables} tables, {total_rows} total rows")


if __name__ == '__main__':
    force = '--force' in sys.argv
    if force:
        print("Running in FORCE mode — existing data will be replaced.")
    migrate(force=force)
