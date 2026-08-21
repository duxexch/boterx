#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ticket System — نظام التذاكر (بديل نظام الشكاوى القديم)
SQLite-backed with smart routing, SLA tracking, and conversation threads.

Features:
- Smart routing: match complaints → involved agent, general → round-robin
- Multi-state workflow: pending → assigned → in_progress → awaiting_user → resolved → closed
- SLA tracking with auto-escalation
- Two-way conversation threads (customer + agent/admin)
- Priority levels with response time requirements
"""

import os
import secrets
import sqlite3
import threading
import logging
from datetime import datetime, timedelta

from db_manager import DB_PATH

logger = logging.getLogger(__name__)

_lock = threading.Lock()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# SLA thresholds (hours)
SLA = {
    'urgent': 1,
    'high':   4,
    'normal': 24,
    'low':    72,
}

TICKET_STATUSES = ['pending', 'assigned', 'in_progress', 'awaiting_user',
                   'resolved', 'closed', 'escalated']

TICKET_CATEGORIES = ['matching', 'deposit', 'withdraw', 'compensation',
                     'account', 'technical', 'general']


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    c.row_factory = sqlite3.Row
    return c


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def init_ticket_tables():
    conn = _conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS tickets (
                id                TEXT PRIMARY KEY,
                user_id           TEXT NOT NULL DEFAULT '',
                customer_id       TEXT NOT NULL DEFAULT '',
                subject           TEXT NOT NULL DEFAULT '',
                message           TEXT NOT NULL DEFAULT '',
                category          TEXT NOT NULL DEFAULT 'general',
                priority          TEXT NOT NULL DEFAULT 'normal',
                status            TEXT NOT NULL DEFAULT 'pending',
                assigned_agent_id TEXT NOT NULL DEFAULT '',
                match_id          TEXT NOT NULL DEFAULT '',
                created_at        TEXT NOT NULL DEFAULT '',
                updated_at        TEXT NOT NULL DEFAULT '',
                first_response_at TEXT NOT NULL DEFAULT '',
                resolved_at       TEXT NOT NULL DEFAULT '',
                closed_at         TEXT NOT NULL DEFAULT '',
                sla_deadline      TEXT NOT NULL DEFAULT '',
                resolved_by       TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_ticket_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS idx_ticket_user ON tickets(user_id);
            CREATE INDEX IF NOT EXISTS idx_ticket_agent ON tickets(assigned_agent_id);

            CREATE TABLE IF NOT EXISTS ticket_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id   TEXT NOT NULL,
                sender_type TEXT NOT NULL,
                sender_id   TEXT NOT NULL,
                message     TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_tmsg_ticket ON ticket_messages(ticket_id);

            CREATE TABLE IF NOT EXISTS ticket_assignments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id   TEXT NOT NULL,
                agent_id    TEXT NOT NULL,
                assigned_at TEXT NOT NULL DEFAULT '',
                resolved_at TEXT NOT NULL DEFAULT ''
            );
        ''')

        # Migrate old complaints.csv if exists
        _migrate_complaints_csv(conn)

        conn.commit()
    finally:
        conn.close()


def _migrate_complaints_csv(conn):
    """One-time migration of old complaints.csv into tickets."""
    import csv
    path = os.path.join(BASE_DIR, 'complaints.csv')
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                tid = row.get('id', '')
                if not tid or tid.startswith('TKT'):
                    continue  # Skip already-migrated
                new_id = f"TKT{secrets.token_hex(4).upper()}"
                user_id = row.get('customer_id', '')
                message = row.get('message', '')
                status = row.get('status', 'pending')
                date = row.get('date', '')
                admin_response = row.get('admin_response', '')

                sla_deadline = ''
                if date:
                    try:
                        dt = datetime.strptime(date, '%Y-%m-%d %H:%M')
                        sla_deadline = (dt + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass

                conn.execute('''INSERT OR IGNORE INTO tickets
                    (id, user_id, customer_id, subject, message, category, priority,
                     status, created_at, updated_at, sla_deadline)
                    VALUES (?,?,?, 'شكوى (مُرحَّلة)', ?, 'general', 'normal', ?, ?, ?, ?)''',
                    (new_id, '', user_id, message,
                     'resolved' if status == 'resolved' else 'closed' if status == 'resolved' else 'pending',
                     date, date or _now(), sla_deadline))

                # Migrate admin response as ticket message
                if admin_response:
                    conn.execute('''INSERT INTO ticket_messages
                        (ticket_id, sender_type, sender_id, message, created_at)
                        VALUES (?,?, 'admin', ?, ?)''',
                        (new_id, '', admin_response, date or _now()))

        logger.info("Migrated complaints.csv to tickets table")
    except Exception as e:
        logger.error(f"Error migrating complaints: {e}")


init_ticket_tables()


# ── Ticket CRUD ────────────────────────────────────────────────────────────────

def create_ticket(user_id, customer_id, message, category='general',
                  priority='normal', match_id=''):
    """Create a new ticket with smart routing."""
    ticket_id = f"TKT{secrets.token_hex(4).upper()}"
    message = str(message).strip()[:2000]

    # Calculate SLA deadline
    sla_hours = SLA.get(priority, 24)
    sla_deadline = (datetime.now() + timedelta(hours=sla_hours)).strftime('%Y-%m-%d %H:%M:%S')

    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')

        # Create ticket
        conn.execute('''INSERT INTO tickets
            (id, user_id, customer_id, subject, message, category, priority,
             status, created_at, updated_at, sla_deadline, match_id)
            VALUES (?,?,'شكوى جديدة',?,?,?,?, 'pending',?,?,?)''',
            (ticket_id, str(user_id), customer_id, message, category, priority,
             _now(), _now(), sla_deadline, str(match_id)))

        # Add user's message as first ticket message
        conn.execute('''INSERT INTO ticket_messages
            (ticket_id, sender_type, sender_id, message, created_at)
            VALUES (?, 'user', ?, ?, ?)''',
            (ticket_id, str(user_id), message, _now()))

        # Smart routing
        assigned_agent = _auto_route(conn, ticket_id, category, match_id)

        conn.commit()
        return {'id': ticket_id, 'assigned_agent': assigned_agent}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating ticket: {e}")
        return {'error': str(e)}
    finally:
        conn.close()


def _auto_route(conn, ticket_id, category, match_id):
    """Smart routing: find the best agent for this ticket."""
    # If it's about a specific match, route to the involved agent
    if match_id:
        match = conn.execute(
            "SELECT agent_id FROM matches WHERE id=?", (match_id,)).fetchone()
        if match and match['agent_id']:
            agent_id = match['agent_id']
            # Check if agent is online and has capacity
            agent = conn.execute(
                "SELECT id, is_online FROM agent_bots WHERE id=? AND is_active=1",
                (agent_id,)).fetchone()
            if agent:
                _assign_ticket(conn, ticket_id, agent_id)
                return agent_id

    # For non-match tickets or no agent found: round-robin among online agents
    agents = conn.execute('''
        SELECT a.id, COUNT(t.id) AS open_count
        FROM agent_bots a
        LEFT JOIN tickets t ON t.assigned_agent_id = a.id
            AND t.status IN ('pending','assigned','in_progress')
        WHERE a.is_active=1 AND a.is_online=1
        GROUP BY a.id
        ORDER BY open_count ASC
        LIMIT 1
    ''').fetchone()

    if agents:
        _assign_ticket(conn, ticket_id, agents['id'])
        return agents['id']

    # No online agents — leave unassigned for admin
    return ''


def _assign_ticket(conn, ticket_id, agent_id):
    """Assign ticket to agent (inside transaction)."""
    conn.execute('''
        UPDATE tickets SET status='assigned', assigned_agent_id=?,
        updated_at=? WHERE id=? AND status='pending'
    ''', (agent_id, _now(), ticket_id))
    conn.execute('''INSERT INTO ticket_assignments
        (ticket_id, agent_id, assigned_at) VALUES (?,?,?)''',
        (ticket_id, agent_id, _now()))


def get_ticket(ticket_id):
    conn = _conn()
    try:
        t = conn.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        return dict(t) if t else None
    finally:
        conn.close()


def list_tickets(status='', priority='', agent_id='', user_id='', limit=100):
    sql = 'SELECT t.*, b.bot_name AS agent_name FROM tickets t '
    sql += 'LEFT JOIN agent_bots b ON t.assigned_agent_id = b.id WHERE 1=1'
    args = []
    if status:
        statuses = [s.strip() for s in str(status).split(',') if s.strip()]
        if statuses:
            sql += f" AND t.status IN ({','.join(['?']*len(statuses))})"
            args.extend(statuses)
    if priority:
        sql += ' AND t.priority=?'
        args.append(priority)
    if agent_id:
        sql += ' AND t.assigned_agent_id=?'
        args.append(agent_id)
    if user_id:
        sql += ' AND t.user_id=?'
        args.append(str(user_id))
    sql += ' ORDER BY t.created_at DESC LIMIT ?'
    args.append(int(limit))
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def get_ticket_messages(ticket_id):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY id',
            (ticket_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_ticket_message(ticket_id, sender_type, sender_id, message):
    """Add message to ticket thread. sender_type: 'user'|'agent'|'admin'"""
    message = str(message).strip()[:5000]
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''INSERT INTO ticket_messages
            (ticket_id, sender_type, sender_id, message, created_at)
            VALUES (?,?,?,?,?)''', (ticket_id, sender_type, str(sender_id), message, _now()))
        conn.execute('UPDATE tickets SET updated_at=? WHERE id=?', (_now(), ticket_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()


def reply_to_ticket(ticket_id, sender_type, sender_id, message, new_status=None):
    """Reply to ticket + optionally change status."""
    message = str(message).strip()[:5000]
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''INSERT INTO ticket_messages
            (ticket_id, sender_type, sender_id, message, created_at)
            VALUES (?,?,?,?,?)''', (ticket_id, sender_type, str(sender_id), message, _now()))

        updates = ['updated_at=?']
        vals = [_now()]

        # Set first_response_at when agent/admin first replies
        t = conn.execute('SELECT first_response_at, status FROM tickets WHERE id=?',
                         (ticket_id,)).fetchone()
        if t and not t['first_response_at'] and sender_type in ('agent', 'admin'):
            updates.append('first_response_at=?')
            vals.append(_now())

        if new_status and new_status in TICKET_STATUSES:
            updates.append('status=?')
            vals.append(new_status)
            if new_status == 'resolved':
                updates.append('resolved_at=?')
                updates.append('resolved_by=?')
                vals.extend([_now(), str(sender_id)])
            elif new_status == 'closed':
                updates.append('closed_at=?')
                vals.append(_now())

        vals.append(ticket_id)
        conn.execute(f'UPDATE tickets SET {", ".join(updates)} WHERE id=?', vals)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Error replying to ticket: {e}")
        return False
    finally:
        conn.close()


def update_ticket_status(ticket_id, status, agent_id=''):
    """Change ticket status."""
    if status not in TICKET_STATUSES:
        return False
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        sets = ['status=?', 'updated_at=?']
        vals = [status, _now()]
        if status == 'resolved':
            sets.append('resolved_at=?')
            vals.append(_now())
        elif status == 'closed':
            sets.append('closed_at=?')
            vals.append(_now())
        if agent_id:
            sets.append('assigned_agent_id=?')
            vals.append(agent_id)
        vals.append(ticket_id)
        conn.execute(f'UPDATE tickets SET {", ".join(sets)} WHERE id=?', vals)

        # Track assignment
        if agent_id and status in ('assigned', 'in_progress'):
            existing = conn.execute(
                'SELECT 1 FROM ticket_assignments WHERE ticket_id=? AND agent_id=? AND resolved_at=?',
                (ticket_id, agent_id, '')).fetchone()
            if not existing:
                conn.execute('''INSERT INTO ticket_assignments
                    (ticket_id, agent_id, assigned_at) VALUES (?,?,?)''',
                    (ticket_id, agent_id, _now()))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()


def reassign_ticket(ticket_id, new_agent_id, reason=''):
    """Reassign ticket to a different agent."""
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''UPDATE tickets SET assigned_agent_id=?, status='assigned',
            updated_at=? WHERE id=?''', (new_agent_id, _now(), ticket_id))
        conn.execute('''INSERT INTO ticket_messages
            (ticket_id, sender_type, sender_id, message, created_at)
            VALUES (?, 'system', '', ?, ?)''',
            (ticket_id, f"تمت إعادة التوجيه إلى وكيل آخر. السبب: {reason}" if reason
             else "تمت إعادة التوجيه إلى وكيل آخر", _now()))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()


# ── SLA Monitoring ──────────────────────────────────────────────────────────

def check_sla_breached():
    """Find tickets that have breached their SLA. Returns list."""
    now = _now()
    conn = _conn()
    try:
        rows = conn.execute('''
            SELECT * FROM tickets
            WHERE status IN ('pending','assigned','in_progress')
            AND sla_deadline != '' AND sla_deadline < ?
            ORDER BY sla_deadline ASC
        ''', (now,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def escalate_overdue_tickets():
    """Auto-escalate tickets past SLA. Returns count escalated."""
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        cur = conn.execute('''
            UPDATE tickets SET status='escalated', updated_at=?
            WHERE status IN ('pending','assigned','in_progress')
            AND sla_deadline != '' AND sla_deadline < ?
        ''', (_now(), _now()))
        count = cur.rowcount
        conn.commit()
        return count
    except Exception as e:
        conn.rollback()
        logger.error(f"Error escalating tickets: {e}")
        return 0
    finally:
        conn.close()


# ── Stats ────────────────────────────────────────────────────────────────────

def get_ticket_stats():
    conn = _conn()
    try:
        total = conn.execute('SELECT COUNT(*) c FROM tickets').fetchone()['c']
        open_count = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE status IN ('pending','assigned','in_progress')"
        ).fetchone()['c']
        escalated = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE status='escalated'"
        ).fetchone()['c']
        resolved = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE status='resolved'"
        ).fetchone()['c']
        breached = conn.execute('''
            SELECT COUNT(*) c FROM tickets
            WHERE status IN ('pending','assigned','in_progress','escalated')
            AND sla_deadline != '' AND sla_deadline < ?
        ''', (_now(),)).fetchone()['c']
        return {
            'total': total, 'open': open_count, 'escalated': escalated,
            'resolved': resolved, 'breached': breached,
            'closed': total - open_count - escalated - resolved,
        }
    finally:
        conn.close()


def get_user_ticket_count(user_id, days=1):
    """Count tickets from user in last N days (for rate limiting)."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE user_id=? AND created_at >= ?",
            (str(user_id), cutoff)).fetchone()
        return r['c'] if r else 0
    finally:
        conn.close()


# ── Agent ticket queue ────────────────────────────────────────────────────────

def get_agent_tickets(agent_id):
    """Get tickets assigned to an agent."""
    return list_tickets(agent_id=agent_id,
                         status='assigned,in_progress,awaiting_user')
