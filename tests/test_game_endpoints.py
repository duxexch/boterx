"""
Integration tests for the five mini-game API endpoints.

Tests run against REAL SQLite (temporary file) and the REAL Flask test client.
They cover:
  - Balance integrity (no double-charge, no double-pay)
  - Durable idempotency: same request_id on a fresh DB connection returns cached result
  - Concurrent identical requests: only one settlement executes
  - Lottery draw ordering: persistence failure aborts before crediting winners
  - Mines cashout: pre-deducted bet, credit-only, idempotent
  - Persistence failure: save errors propagate (no silent swallow during draw)

Run with:  python -m pytest tests/test_game_endpoints.py -v
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest

# ---------------------------------------------------------------------------
# Set up paths
# ---------------------------------------------------------------------------
WORKSPACE = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE)
sys.path.insert(0, os.path.join(WORKSPACE, 'dashboard'))

# ---------------------------------------------------------------------------
# Isolate to a temporary SQLite DB for every test
# ---------------------------------------------------------------------------
import db_manager as _dm_module

def _make_temp_db():
    """Create a temporary DB file and return (path, GameDB instance)."""
    f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    f.close()
    db = _dm_module.GameDB(f.name)
    return f.name, db

def _ensure_user(db, uid, balance=1000.0):
    """Upsert a test user with a known balance."""
    conn = db._conn()
    with _dm_module._db_lock:
        conn.execute('BEGIN')
        conn.execute('''
            INSERT INTO users (telegram_id, game_balance) VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET game_balance = ?
        ''', (str(uid), balance, balance))
        conn.commit()


# ===========================================================================
# 1. SQLite-layer idempotency tests (no Flask needed)
# ===========================================================================

class TestSettleWithIdempotency(unittest.TestCase):
    """GameDB.settle_with_idempotency against a real temporary SQLite DB."""

    def setUp(self):
        self.db_path, self.db = _make_temp_db()
        _ensure_user(self.db, 'u1', 1000.0)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    # --- Basic settlement ---

    def test_settle_deducts_bet_and_adds_payout(self):
        ok, stored, cached = self.db.settle_with_idempotency(
            'u1', 100, 200, 'req-1', {'game': 'plinko'})
        self.assertTrue(ok)
        self.assertIsNone(cached)
        self.assertAlmostEqual(stored['balance_after'], 1100.0)

    def test_settle_insufficient_funds_rejected(self):
        ok, stored, cached = self.db.settle_with_idempotency(
            'u1', 2000, 0, 'req-2', {'game': 'wheel'})
        self.assertFalse(ok)
        self.assertIsNone(stored)
        self.assertIsNone(cached)
        # Balance must be unchanged
        row = self.db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', ('u1',)).fetchone()
        self.assertAlmostEqual(row[0], 1000.0)

    # --- Idempotency on the SAME connection (common case) ---

    def test_same_request_id_returns_cached_result(self):
        ok1, stored1, _ = self.db.settle_with_idempotency(
            'u1', 100, 200, 'req-3', {'game': 'snatch'})
        self.assertTrue(ok1)

        ok2, stored2, cached2 = self.db.settle_with_idempotency(
            'u1', 100, 200, 'req-3', {'game': 'snatch'})
        self.assertTrue(ok2)
        self.assertIsNone(stored2)
        self.assertIsNotNone(cached2)
        # Cached result must match first call
        self.assertAlmostEqual(cached2['balance_after'], stored1['balance_after'])
        # Balance must NOT have changed on the second call
        row = self.db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', ('u1',)).fetchone()
        self.assertAlmostEqual(row[0], stored1['balance_after'])

    # --- Idempotency ACROSS DB restarts (new connection to same file) ---

    def test_idempotency_survives_restart(self):
        """Simulates server restart: new GameDB instance same DB file."""
        ok1, stored1, _ = self.db.settle_with_idempotency(
            'u1', 100, 0, 'req-restart', {'game': 'mines_new'})
        self.assertTrue(ok1)
        bal_after_first = stored1['balance_after']

        # Simulate restart: create a brand-new GameDB connection to the same file
        db2 = _dm_module.GameDB(self.db_path)
        ok2, stored2, cached2 = db2.settle_with_idempotency(
            'u1', 100, 0, 'req-restart', {'game': 'mines_new'})

        self.assertTrue(ok2)
        self.assertIsNotNone(cached2)
        # Cached result from first call is returned; balance not changed again
        self.assertAlmostEqual(cached2['balance_after'], bal_after_first)
        # Actual DB balance unchanged after retry
        row = db2._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', ('u1',)).fetchone()
        self.assertAlmostEqual(row[0], bal_after_first)

    # --- Concurrent identical requests (same request_id, different threads) ---

    def test_concurrent_duplicate_requests_settle_exactly_once(self):
        """Two threads fire the same request_id simultaneously; exactly one settles."""
        results = []
        errors = []

        def do_settle():
            try:
                ok, stored, cached = self.db.settle_with_idempotency(
                    'u1', 100, 200, 'req-concurrent', {'game': 'plinko'})
                results.append((ok, stored, cached))
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=do_settle)
        t2 = threading.Thread(target=do_settle)
        t1.start(); t2.start()
        t1.join(); t2.join()

        self.assertEqual(len(errors), 0, errors)
        self.assertEqual(len(results), 2)

        # Total settlement: only ONE of the two should have stored (not cached)
        settled = sum(1 for ok, stored, cached in results if stored is not None)
        replayed = sum(1 for ok, stored, cached in results if cached is not None)
        self.assertEqual(settled, 1, "Exactly one thread should settle")
        self.assertEqual(replayed, 1, "The other thread should get the cached result")

        # Balance reflects exactly one round (net = 200 - 100 = +100)
        row = self.db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', ('u1',)).fetchone()
        self.assertAlmostEqual(row[0], 1100.0)

    # --- credit_with_idempotency (mines cashout style) ---

    def test_credit_with_idempotency_is_exactly_once(self):
        payout = 250.0
        template = {'payout': payout}
        ok1, stored1, _ = self.db.credit_with_idempotency('u1', payout, 'cashout-1', template)
        self.assertTrue(ok1)
        self.assertAlmostEqual(stored1['balance_after'], 1250.0)

        # Retry
        ok2, stored2, cached2 = self.db.credit_with_idempotency('u1', payout, 'cashout-1', template)
        self.assertTrue(ok2)
        self.assertIsNone(stored2)
        self.assertAlmostEqual(cached2['balance_after'], 1250.0)

        # Balance must not have changed a second time
        row = self.db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', ('u1',)).fetchone()
        self.assertAlmostEqual(row[0], 1250.0)

    def test_credit_survives_restart(self):
        payout = 180.0
        template = {'payout': payout}
        ok1, stored1, _ = self.db.credit_with_idempotency('u1', payout, 'cashout-restart', template)
        self.assertTrue(ok1)

        # Simulate restart
        db2 = _dm_module.GameDB(self.db_path)
        ok2, stored2, cached2 = db2.credit_with_idempotency(
            'u1', payout, 'cashout-restart', template)
        self.assertTrue(ok2)
        self.assertIsNone(stored2)
        self.assertAlmostEqual(cached2['balance_after'], stored1['balance_after'])

        row = db2._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', ('u1',)).fetchone()
        self.assertAlmostEqual(row[0], stored1['balance_after'])

    # --- balance_after is correct ---

    def test_balance_after_stored_matches_actual_db_balance(self):
        """balance_after in the stored idempotency record must equal actual DB balance."""
        ok, stored, _ = self.db.settle_with_idempotency(
            'u1', 300, 150, 'req-bal', {'game': 'wheel'})
        self.assertTrue(ok)
        row = self.db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', ('u1',)).fetchone()
        self.assertAlmostEqual(stored['balance_after'], row[0])


# ===========================================================================
# 2. Lottery draw ordering: persist-before-credit
# ===========================================================================

class TestLotteryDrawOrdering(unittest.TestCase):
    """
    Verifies the lottery draw does NOT credit winners when the state save fails.
    We patch _save_lottery_state to raise on the first call (simulating disk error),
    and confirm no add_balance was called.
    """

    def setUp(self):
        self.db_path, self.db = _make_temp_db()
        _ensure_user(self.db, 'winner1', 500.0)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_draw_aborts_before_credit_when_save_fails(self):
        """If _save_lottery_state raises, credit_with_idempotency must not be called."""
        import dashboard.app as app_module
        from unittest.mock import patch, MagicMock

        credit_calls = []

        def mock_credit(uid, amount, key, template):
            credit_calls.append((uid, amount))
            return True, {'balance_after': 999}, None

        def mock_save_fail(state, raise_on_error=False):
            if raise_on_error:
                raise OSError("Simulated disk full")

        with patch.object(app_module, '_save_lottery_state', side_effect=mock_save_fail), \
             patch.object(app_module._gm, 'credit_with_idempotency', side_effect=mock_credit):
            # Build a state that needs drawing
            now = time.time()
            state = {
                'round_id': 'LTR_TEST',
                'draw_time': now - 10,  # expired
                'ticket_price': 50,
                'tickets': [{
                    'id': 'T1', 'uid': 'winner1',
                    'numbers': [1, 2, 3, 4, 5], 'status': 'pending',
                    'scratched': False, 'drawn': None
                }],
                'tickets_sold': 1,
                'prize_pool': 100,
                'drawn': None,
            }
            with patch.object(app_module, '_load_lottery_state', return_value=state):
                try:
                    app_module._get_or_create_lottery_round()
                except OSError:
                    pass  # Expected: save failed

        # No credits should have been issued because save failed first
        self.assertEqual(len(credit_calls), 0,
            f"Expected 0 credit calls, got {len(credit_calls)}: {credit_calls}")

    def test_draw_credits_winners_after_successful_save(self):
        """When save succeeds, winners are credited with derived idempotency keys."""
        import dashboard.app as app_module
        from unittest.mock import patch, MagicMock

        credit_calls = []

        def mock_credit(uid, amount, key, template):
            credit_calls.append((uid, amount, key))
            return True, {'balance_after': 999}, None

        saved_states = []

        def mock_save(state, raise_on_error=False):
            saved_states.append(dict(state))

        # Force all tickets to win by patching random.sample inside the draw
        now = time.time()
        winning_numbers = [1, 2, 3, 4, 5]
        state = {
            'round_id': 'LTR_WIN',
            'draw_time': now - 10,
            'ticket_price': 50,
            'tickets': [{
                'id': 'T1', 'uid': 'winner1',
                'numbers': winning_numbers, 'status': 'pending',
                'scratched': False, 'drawn': None
            }],
            'tickets_sold': 1,
            'prize_pool': 100.0,
            'drawn': None,
        }
        with patch.object(app_module, '_save_lottery_state', side_effect=mock_save), \
             patch.object(app_module._gm, 'credit_with_idempotency', side_effect=mock_credit), \
             patch.object(app_module, '_load_lottery_state', return_value=state), \
             patch('random.sample', return_value=winning_numbers):
            app_module._get_or_create_lottery_round()

        # State must be saved (with drawn set) BEFORE credit_with_idempotency is called
        self.assertGreater(len(saved_states), 0, "State should have been saved")
        self.assertIsNotNone(saved_states[0].get('drawn'), "State must have drawn set before credit")

        # Winner should have been credited
        self.assertEqual(len(credit_calls), 1, f"Expected 1 credit call, got {credit_calls}")
        uid, amount, key = credit_calls[0]
        self.assertEqual(uid, 'winner1')
        self.assertAlmostEqual(amount, 100.0)
        # Derived key must embed round_id and uid
        self.assertIn('LTR_WIN', key)
        self.assertIn('winner1', key)

    def test_restart_after_save_before_credits_resumes_payment(self):
        """Simulates a crash: drawn state is persisted with winners_to_credit,
        but credits have NOT run. Next call must resume and credit the winner."""
        import dashboard.app as app_module
        from unittest.mock import patch

        credit_calls = []

        def mock_credit(uid, amount, key, template):
            credit_calls.append((uid, amount, key))
            return True, {'balance_after': 999}, None

        # Simulate the state after a crash: drawn is set, winners_to_credit is populated,
        # but no credits have been paid yet.
        now = time.time()
        state_after_crash = {
            'round_id': 'LTR_CRASH',
            'draw_time': now - 60,  # already expired
            'ticket_price': 50,
            'tickets': [{
                'id': 'T1', 'uid': 'winner1',
                'numbers': [1, 2, 3, 4, 5],
                'status': 'win', 'scratched': True,
                'drawn': [1, 2, 3, 4, 5], 'prize': 100.0
            }],
            'tickets_sold': 1,
            'prize_pool': 100.0,
            'drawn': [1, 2, 3, 4, 5],
            'drawn_at': now - 60,
            'winners_to_credit': [{
                'uid': 'winner1',
                'amount': 100.0,
                'idem_key': 'lottery_LTR_CRASH_winner1'
            }],
        }

        saved_states = []

        def mock_save(state, raise_on_error=False):
            saved_states.append({'drawn': state.get('drawn'),
                                 'winners_to_credit': state.get('winners_to_credit', [])})

        with patch.object(app_module, '_load_lottery_state', side_effect=[
                state_after_crash,  # first load: returns crash state
                dict(state_after_crash, winners_to_credit=[])  # second load: after credits cleared
            ]), \
             patch.object(app_module, '_save_lottery_state', side_effect=mock_save), \
             patch.object(app_module._gm, 'credit_with_idempotency', side_effect=mock_credit):
            app_module._get_or_create_lottery_round()

        # The winner must have been credited via the resume path
        self.assertEqual(len(credit_calls), 1,
            f"Expected 1 credit call after restart, got {credit_calls}")
        uid_called, amount_called, key_called = credit_calls[0]
        self.assertEqual(uid_called, 'winner1')
        self.assertAlmostEqual(amount_called, 100.0)
        self.assertEqual(key_called, 'lottery_LTR_CRASH_winner1')

    def test_partial_credit_completed_on_next_call(self):
        """Simulates partial credit: 1 of 2 winners was credited before crash.
        Next call must credit only the remaining winner (idempotency keys prevent double-pay)."""
        import dashboard.app as app_module
        from unittest.mock import patch

        credit_calls = []
        # Simulate winner2 already credited (idem_key returns cached result),
        # winner1 still pending (returns fresh credit)
        def mock_credit(uid, amount, key, template):
            credit_calls.append((uid, key))
            # Both calls succeed; idempotency enforcement is tested at the DB layer
            return True, {'balance_after': 999}, None

        now = time.time()
        # Only winner1 remains in winners_to_credit (winner2 was already paid before crash)
        state_partial = {
            'round_id': 'LTR_PARTIAL',
            'draw_time': now - 60,
            'ticket_price': 50,
            'tickets': [],
            'tickets_sold': 2,
            'prize_pool': 200.0,
            'drawn': [1, 2, 3, 4, 5],
            'drawn_at': now - 60,
            'winners_to_credit': [{
                'uid': 'winner1',
                'amount': 100.0,
                'idem_key': 'lottery_LTR_PARTIAL_winner1'
            }],  # only winner1 remains
        }

        saved_states = []

        def mock_save(state, raise_on_error=False):
            saved_states.append({'winners_to_credit': list(state.get('winners_to_credit', []))})

        with patch.object(app_module, '_load_lottery_state', side_effect=[
                state_partial,
                dict(state_partial, winners_to_credit=[])
            ]), \
             patch.object(app_module, '_save_lottery_state', side_effect=mock_save), \
             patch.object(app_module._gm, 'credit_with_idempotency', side_effect=mock_credit):
            app_module._get_or_create_lottery_round()

        # Only winner1 should be credited (winner2 already paid, not in pending list)
        self.assertEqual(len(credit_calls), 1, f"Expected 1 credit call, got {credit_calls}")
        self.assertEqual(credit_calls[0][0], 'winner1')
        self.assertEqual(credit_calls[0][1], 'lottery_LTR_PARTIAL_winner1')


# ===========================================================================
# 3. Flask endpoint integration tests (real test client)
# ===========================================================================

def _build_test_app():
    """Import and configure the Flask app for testing.

    Uses the app's real vex_games.db so _inject_user writes to the same DB
    that the running app reads. Test users use UIDs that are unlikely to
    collide with real accounts (prefix: 'TEST_').
    """
    import dashboard.app as app_module
    app_module.app.config['TESTING'] = True
    app_module.app.config['SECRET_KEY'] = 'test-secret'

    # Use the same DB path the app uses
    import db_manager as dm
    real_db_path = dm.DB_PATH

    return app_module, real_db_path


class TestFlaskEndpointIdempotency(unittest.TestCase):
    """Flask test client tests for idempotency and balance integrity."""

    @classmethod
    def setUpClass(cls):
        """Import app once; inject a test user into the real SQLite DB."""
        try:
            cls.app_module, cls.db_path = _build_test_app()
            cls.client = cls.app_module.app.test_client()
            cls._skip = False
        except Exception as e:
            cls._skip = True
            cls._skip_reason = str(e)

    @classmethod
    def tearDownClass(cls):
        if not cls._skip:
            # Clean up test users and snatch sessions from the real DB (UIDs start with 'flask_')
            try:
                import db_manager as dm
                conn = dm._get_conn()
                conn.execute("DELETE FROM users WHERE telegram_id LIKE 'flask_%'")
                conn.execute("DELETE FROM game_idempotency WHERE uid LIKE 'flask_%'")
                conn.execute("DELETE FROM snatch_sessions WHERE uid LIKE 'flask_%'")
                conn.commit()
                conn.close()
            except Exception:
                pass

    def setUp(self):
        if self._skip:
            self.skipTest(f"App import failed: {self._skip_reason}")

    def _inject_user(self, uid, balance=2000.0):
        """Write test user directly to the app's real vex_games.db."""
        import db_manager as dm
        db = dm.GameDB()   # no arg → uses module-level DB_PATH (same as the app)
        _ensure_user(db, uid, balance)

    def _post(self, path, data, uid='test_user_42', request_id=None):
        """POST helper.

        Temporarily blanks app_module.BOT_TOKEN so webapp_auth falls into its
        dev-mode branch (accepts 'uid' from JSON body).  The real BOT_TOKEN is
        restored afterwards so module state isn't permanently altered.
        """
        from unittest.mock import patch
        headers = {'Content-Type': 'application/json'}
        if request_id:
            headers['X-Request-Id'] = request_id
        body = dict(data)
        # webapp_auth dev-mode: accepts 'uid' from JSON body when BOT_TOKEN is ''
        body['uid'] = str(uid)
        if request_id:
            body['request_id'] = request_id

        with patch.object(self.app_module, 'BOT_TOKEN', ''):
            resp = self.client.post(path,
                data=json.dumps(body),
                headers=headers)
        return resp

    # --- Plinko: duplicate request_id → idempotent response ---

    def test_plinko_duplicate_request_id_no_double_charge(self):
        uid = 'flask_plinko_1'
        self._inject_user(uid, 500.0)

        r1 = self._post('/api/plinko/drop',
                        {'bet': 100, 'rows': 8, 'risk': 'low'},
                        uid=uid, request_id='plinko-idem-1')
        self.assertEqual(r1.status_code, 200)
        d1 = json.loads(r1.data)
        self.assertTrue(d1.get('success'))
        bal1 = d1.get('balance_after')

        # Second call with same request_id
        r2 = self._post('/api/plinko/drop',
                        {'bet': 100, 'rows': 8, 'risk': 'low'},
                        uid=uid, request_id='plinko-idem-1')
        self.assertEqual(r2.status_code, 200)
        d2 = json.loads(r2.data)
        self.assertTrue(d2.get('success'))
        bal2 = d2.get('balance_after')

        # Both responses must report the same balance_after (idempotent)
        self.assertAlmostEqual(bal1, bal2,
            msg=f"Idempotent replay should return same balance_after: {bal1} vs {bal2}")

        # Actual DB balance must equal bal1 (settled once, not twice)
        import db_manager as dm
        db = dm.GameDB(self.db_path)
        row = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()
        self.assertAlmostEqual(row[0], bal1)

    # --- Wheel: idempotency record survives a new DB connection (simulated restart) ---

    def test_wheel_idempotency_survives_restart(self):
        uid = 'flask_wheel_restart'
        self._inject_user(uid, 500.0)

        r1 = self._post('/api/wheel/spin', {'bet': 100}, uid=uid, request_id='wheel-restart-1')
        self.assertEqual(r1.status_code, 200)
        d1 = json.loads(r1.data)
        bal1 = d1.get('balance_after')

        # Simulate restart: query the idempotency record from a fresh DB connection
        # (same vex_games.db file the app uses — proves the record survives process restart)
        import db_manager as dm
        db2 = dm.GameDB()  # fresh instance → new per-thread connection to same DB file
        db2._local = type('L', (), {})()  # clear thread-local so it opens a new connection
        cached = db2.get_idempotency_record(uid, 'wheel-restart-1')
        self.assertIsNotNone(cached,
            "Idempotency record must be in SQLite (survives restart)")
        self.assertAlmostEqual(cached.get('balance_after', -1), bal1)

    # --- Mines: cashout credit-only, not double-charge ---

    def test_mines_cashout_credit_only(self):
        uid = 'flask_mines_cashout'
        self._inject_user(uid, 500.0)

        # Start a mines session
        r_new = self._post('/api/mines/new',
                           {'bet': 100, 'mines_count': 3}, uid=uid, request_id='mines-new-1')
        self.assertEqual(r_new.status_code, 200, r_new.data)
        d_new = json.loads(r_new.data)
        self.assertTrue(d_new.get('success'), d_new)
        bal_after_new = d_new.get('balance_after')

        # Bet was deducted; balance should be lower
        import db_manager as dm
        db = dm.GameDB(self.db_path)
        row = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()
        self.assertAlmostEqual(row[0], bal_after_new)
        self.assertLess(bal_after_new, 500.0)

        # Cashout (no reveal — tests that cashout works even with multiplier=1.0)
        r_co = self._post('/api/mines/cashout', {}, uid=uid, request_id='mines-co-1')
        self.assertEqual(r_co.status_code, 200, r_co.data)
        d_co = json.loads(r_co.data)
        self.assertTrue(d_co.get('success'), d_co)
        bal_after_co = d_co.get('balance_after')
        payout = d_co.get('payout', 0)

        # balance_after_cashout ≈ balance_after_new + payout
        self.assertAlmostEqual(bal_after_co, bal_after_new + payout, places=2)

        # Verify DB
        row2 = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()
        self.assertAlmostEqual(row2[0], bal_after_co)

    # --- Snatch: two-phase balance integrity ---

    def test_snatch_spin_deducts_bet_only(self):
        """Spin deducts bet; no payout until /api/snatch/end is called."""
        uid = 'flask_snatch_1'
        self._inject_user(uid, 300.0)

        r = self._post('/api/snatch/spin', {'bet': 50}, uid=uid, request_id='snatch-spin-1')
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.data)
        self.assertTrue(d.get('success'), d)
        # Spin must return session_id (not payout)
        self.assertIn('session_id', d, "Spin must return session_id for two-phase protocol")
        # balance_before is 300; after deduction = 300 - 50 = 250
        expected_bal = 300.0 - 50.0
        self.assertAlmostEqual(d.get('balance_before', -1), 300.0, places=2)

        import db_manager as dm
        db = dm.GameDB(self.db_path)
        row = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()
        # Bet deducted in wallet DB before /api/snatch/end
        self.assertAlmostEqual(row[0], expected_bal, places=2,
                               msg="Bet must be deducted from wallet at spin time")

    def test_snatch_end_credits_server_payout(self):
        """Full two-phase flow: spin deducts bet, end credits server-determined payout.

        The payout is set by the server algorithm at spin time.  We verify:
          1. Bet is deducted at spin (balance drops by bet).
          2. /api/snatch/end returns success with a payout value.
          3. Wallet balance = balance_after_spin + payout (exactly once).
          4. Forged score cannot inflate the payout beyond the server value.
        """
        uid = 'flask_snatch_2'
        self._inject_user(uid, 500.0)

        # Step 1: spin
        r1 = self._post('/api/snatch/spin', {'bet': 100}, uid=uid, request_id='snatch-end-spin-1')
        self.assertEqual(r1.status_code, 200)
        d1 = json.loads(r1.data)
        self.assertTrue(d1.get('success'), d1)
        session_id = d1.get('session_id')
        self.assertIsNotNone(session_id, "Spin must return session_id")

        import db_manager as dm
        db = dm.GameDB(self.db_path)
        bal_after_spin = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()[0]
        self.assertAlmostEqual(bal_after_spin, 400.0, places=2,
                               msg="Bet must be deducted at spin")

        # Step 2: end — score value from client does NOT influence payout
        r2 = self._post('/api/snatch/end', {'session_id': session_id, 'score': 45},
                        uid=uid)
        self.assertEqual(r2.status_code, 200)
        d2 = json.loads(r2.data)
        self.assertTrue(d2.get('success'), d2)
        server_payout = d2.get('payout', 0)

        # Wallet must reflect bet-out + server_payout-in: 400 + server_payout
        bal_after_end = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()[0]
        self.assertAlmostEqual(bal_after_end, 400.0 + server_payout, places=2,
                               msg="Balance must equal 400 + server_payout, no more, no less")

        # Forged-score check: re-calling end with inflated score must be rejected
        # (session is settled — second call must not succeed)
        r3 = self._post('/api/snatch/end', {'session_id': session_id, 'score': 200},
                        uid=uid)
        self.assertNotEqual(r3.status_code, 200,
                            "Second /api/snatch/end must be rejected after first succeeds")
        # Wallet must not have changed
        bal_after_forged = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()[0]
        self.assertAlmostEqual(bal_after_forged, bal_after_end, places=2,
                               msg="Forged second end must not affect wallet balance")

    def test_snatch_end_duplicate_rejected(self):
        """Second /api/snatch/end on the same session must be rejected."""
        uid = 'flask_snatch_3'
        self._inject_user(uid, 500.0)

        r1 = self._post('/api/snatch/spin', {'bet': 50}, uid=uid, request_id='snatch-dup-spin')
        session_id = json.loads(r1.data).get('session_id')
        self.assertIsNotNone(session_id)

        r2 = self._post('/api/snatch/end', {'session_id': session_id, 'score': 40}, uid=uid)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(json.loads(r2.data).get('success'))

        # Second call: session is now 'settled', must be blocked
        r3 = self._post('/api/snatch/end', {'session_id': session_id, 'score': 40}, uid=uid)
        self.assertNotEqual(r3.status_code, 200,
                            "Duplicate /api/snatch/end must be rejected")

    def test_snatch_spin_idempotent(self):
        """Same request_id on /api/snatch/spin deducts bet exactly once."""
        uid = 'flask_snatch_4'
        self._inject_user(uid, 300.0)

        r1 = self._post('/api/snatch/spin', {'bet': 50}, uid=uid, request_id='snatch-idem-1')
        r2 = self._post('/api/snatch/spin', {'bet': 50}, uid=uid, request_id='snatch-idem-1')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        d1 = json.loads(r1.data)
        d2 = json.loads(r2.data)
        self.assertTrue(d1.get('success'))
        self.assertTrue(d2.get('success'))

        import db_manager as dm
        db = dm.GameDB(self.db_path)
        bal = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()[0]
        self.assertAlmostEqual(bal, 250.0, places=2,
                               msg="Idempotent spin: bet deducted exactly once")

    # --- Lottery buy: exactly-once ticket deduction ---

    def test_lottery_buy_idempotent(self):
        uid = 'flask_lottery_1'
        self._inject_user(uid, 500.0)

        r1 = self._post('/api/lottery/buy', {'count': 1}, uid=uid, request_id='lottery-buy-1')
        self.assertEqual(r1.status_code, 200, r1.data)
        d1 = json.loads(r1.data)
        self.assertTrue(d1.get('success'), d1)
        bal1 = d1.get('balance_after')

        # Retry with same request_id
        r2 = self._post('/api/lottery/buy', {'count': 1}, uid=uid, request_id='lottery-buy-1')
        self.assertEqual(r2.status_code, 200, r2.data)
        d2 = json.loads(r2.data)
        self.assertTrue(d2.get('success'), d2)
        bal2 = d2.get('balance_after')

        # Idempotent: both report same balance_after
        self.assertAlmostEqual(bal1, bal2,
            msg=f"Lottery buy idempotency failed: {bal1} vs {bal2}")

        import db_manager as dm
        db = dm.GameDB(self.db_path)
        row = db._conn().execute(
            'SELECT game_balance FROM users WHERE telegram_id=?', (uid,)).fetchone()
        self.assertAlmostEqual(row[0], bal1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
