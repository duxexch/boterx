"""
Tests for the Snatch game session state machine.

Uses real db_manager.GameDB (the same module used in production) for session
operations, so the tests exercise the actual schema, CAS logic, and DB wiring.

Wallet operations use a lightweight in-memory stub so the tests have no
dependency on vex_games.db being pre-seeded.

Covered scenarios:
  - intent row recovery: promoted when deduction record found; deleted when not
  - TTL expiry → automatic refund (idempotent across multiple sweep runs)
  - Normal settlement: score brackets, score cap, expired/wrong-uid rejection
  - Concurrent sweep+end race: exactly-one winner via CAS
  - Duplicate /api/snatch/end blocked
  - Crash recovery: settling/refunding intermediate states completed by sweep

Run with:  python3 -m unittest tests/test_snatch_sessions.py -v
"""

import os
import sys
import tempfile
import threading
import time
import unittest

WORKSPACE = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE)
sys.path.insert(0, os.path.join(WORKSPACE, 'dashboard'))

import db_manager as dm


# ---------------------------------------------------------------------------
# Minimal wallet stub — replaces _gm in the snatch module
# ---------------------------------------------------------------------------

class _FakeWallet:
    """Thread-safe in-memory wallet stub."""

    def __init__(self, initial_balance=1000.0):
        self._lock = threading.Lock()
        self._balances: dict = {}
        self._idem: dict = {}
        self._default_balance = initial_balance

    def ensure_user(self, uid, balance=None):
        with self._lock:
            self._balances[str(uid)] = balance if balance is not None else self._default_balance

    def get_balance(self, uid):
        with self._lock:
            return self._balances.get(str(uid), self._default_balance)

    def get_idempotency_record(self, uid, request_id):
        with self._lock:
            return self._idem.get((str(uid), str(request_id)))

    def credit_with_idempotency(self, uid, amount, request_id, template):
        with self._lock:
            key = (str(uid), str(request_id))
            if key in self._idem:
                return True, None, self._idem[key]
            bal = self._balances.get(str(uid), 0.0) + float(amount)
            self._balances[str(uid)] = bal
            resp = dict(template)
            resp['balance_after'] = bal
            self._idem[key] = resp
            return True, resp, None

    def settle_with_idempotency(self, uid, bet, payout, request_id, template):
        with self._lock:
            key = (str(uid), str(request_id)) if request_id else None
            if key and key in self._idem:
                return True, None, self._idem[key]
            bal = self._balances.get(str(uid), 0.0)
            net = float(payout) - float(bet)
            if net < 0 and bal < abs(net):
                return False, None, None
            new_bal = bal + net
            self._balances[str(uid)] = new_bal
            resp = dict(template)
            resp['balance_after'] = new_bal
            if key:
                self._idem[key] = resp
            return True, resp, None


# ---------------------------------------------------------------------------
# Constants matching app.py
# ---------------------------------------------------------------------------

_SNATCH_SESSION_TTL      = 35
_SNATCH_INTENT_GRACE     = 120
_SNATCH_SETTLING_TIMEOUT = 300


def _payout_multiplier(score):
    if score >= 40: return 2.0
    if score >= 25: return 1.5
    if score >= 15: return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# State-machine helpers (mirror app.py logic using real GameDB methods)
# ---------------------------------------------------------------------------

def run_sweep(sdb: dm.GameDB, wallet: _FakeWallet, now=None):
    """One sweep pass using real GameDB session methods."""
    if now is None:
        now = time.time()

    # 1. Resolve old intent rows
    for sess in sdb.snatch_get_by_status('intent', created_before=now - _SNATCH_INTENT_GRACE):
        sid = sess['session_id']
        uid = sess['uid']
        spin_key = sess['spin_request_id']
        idem = wallet.get_idempotency_record(uid, spin_key) if spin_key else None
        if idem:
            sdb.snatch_cas_status(sid, 'intent', 'pending')
        else:
            sdb.snatch_delete_session(sid)

    # 2. Claim expired pending rows
    for sess in sdb.snatch_get_by_status('pending', created_before=now - _SNATCH_SESSION_TTL):
        sdb.snatch_cas_status(sess['session_id'], 'pending', 'refunding')

    # 3. Process refunding rows: credit THEN mark terminal
    for sess in sdb.snatch_get_by_status('refunding'):
        sid = sess['session_id']
        uid = sess['uid']
        bet = sess['bet_amount']
        if bet > 0:
            wallet.credit_with_idempotency(uid, bet, f"snatch_refund_{sid}",
                                           {'success': True, 'refunded': True})
        sdb.snatch_cas_status(sid, 'refunding', 'refunded',
                              settled_at=time.time())

    # 4. Recover stale settling rows — use server-stored payout, never re-derive from score
    for sess in sdb.snatch_get_by_status('settling',
                                         created_before=now - _SNATCH_SETTLING_TIMEOUT):
        sid = sess['session_id']
        uid = sess['uid']
        payout = sess['payout'] if sess['payout'] is not None else 0.0
        if payout > 0:
            wallet.credit_with_idempotency(uid, payout, f"snatch_payout_{sid}",
                                           {'success': True, 'payout': payout})
        sdb.snatch_cas_status(sid, 'settling', 'settled',
                              settled_at=time.time())


def do_end(sdb: dm.GameDB, wallet: _FakeWallet, session_id, uid, score, now=None):
    """Run the /api/snatch/end logic using real GameDB methods.

    The payout credited is taken from the server-stored sess['payout'] column,
    which was set at spin time by the server algorithm.  The client-supplied
    score is stored for analytics but does NOT influence the financial outcome.

    Returns (ok, payout_or_error_str).
    """
    if now is None:
        now = time.time()
    score = min(max(0, score), 200)

    sess = sdb.snatch_get_session(session_id)
    if not sess:
        return False, 'not_found'
    if str(sess['uid']) != str(uid):
        return False, 'mismatch'
    if sess['status'] != 'pending':
        return False, f'already_{sess["status"]}'
    if now - sess['created_at'] > _SNATCH_SESSION_TTL:
        return False, 'expired'

    # Server-authoritative payout — stored at spin time, never from client
    payout = sess['payout'] if sess['payout'] is not None else 0.0

    # CAS: pending → settling (stores client score for analytics only)
    updated = sdb.snatch_cas_status(session_id, 'pending', 'settling', score=score)
    if updated == 0:
        return False, 'race_lost'

    new_balance = wallet.get_balance(uid)
    if payout > 0:
        _, cr, cc = wallet.credit_with_idempotency(
            uid, payout, f"snatch_payout_{session_id}",
            {'success': True, 'payout': payout}
        )
        res = cc or cr or {}
        new_balance = res.get('balance_after', wallet.get_balance(uid))

    # Terminal update AFTER credit (payout already stored in row from spin)
    sdb.snatch_cas_status(session_id, 'settling', 'settled',
                          settled_at=time.time())
    return True, payout


# ---------------------------------------------------------------------------
# Test base: fresh GameDB per test pointing at a temp file
# ---------------------------------------------------------------------------

class SnatchTestCase(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        f.close()
        self.db_path = f.name
        self.sdb = dm.GameDB(self.db_path)   # _custom_init creates snatch_sessions
        self.wallet = _FakeWallet()
        self.wallet.ensure_user('u1', 1000.0)
        self.wallet.ensure_user('u2', 1000.0)

    def _create_pending(self, sid, uid, bet, server_payout, age_seconds=0):
        """Create a pending session with a pre-determined server payout."""
        self.sdb.snatch_create_session(
            sid, uid, bet, None,
            time.time() - age_seconds,
            server_payout=server_payout
        )
        self.sdb.snatch_cas_status(sid, 'intent', 'pending')

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass


# ===========================================================================
# Tests
# ===========================================================================

class TestIntentRecovery(SnatchTestCase):
    """Intent row recovery at sweep time."""

    def test_intent_with_deduction_record_is_refunded(self):
        """Crash after deduction before intent→pending: sweep promotes then refunds.

        INTENT_GRACE(120 s) > SESSION_TTL(35 s), so a row old enough for intent
        recovery is also past TTL — the same sweep run promotes to 'pending' and
        immediately claims it for refund. Final: 'refunded', bet restored.
        """
        self.wallet.ensure_user('u1', 490.0)
        # Simulate wallet deduction idempotency record already present
        self.wallet._idem[('u1', 'spin_key_1')] = {'balance_after': 490.0}

        self.sdb.snatch_create_session('S1', 'u1', 10.0, 'spin_key_1',
                                       time.time() - _SNATCH_INTENT_GRACE - 1)

        run_sweep(self.sdb, self.wallet)

        sess = self.sdb.snatch_get_session('S1')
        self.assertEqual(sess['status'], 'refunded',
                         "Row must be refunded after intent→pending→refunded in one sweep")
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 500.0,
                               msg="Bet must be refunded to the player")

    def test_intent_without_deduction_record_deleted(self):
        """Crash before deduction: no wallet record, intent row deleted, no refund."""
        bal_before = self.wallet.get_balance('u1')
        self.sdb.snatch_create_session('S2', 'u1', 10.0, 'spin_key_2',
                                       time.time() - _SNATCH_INTENT_GRACE - 1)

        run_sweep(self.sdb, self.wallet)

        self.assertIsNone(self.sdb.snatch_get_session('S2'),
                          "Ghost intent row must be deleted")
        self.assertAlmostEqual(self.wallet.get_balance('u1'), bal_before,
                               msg="Balance must not change for un-deducted intent")


class TestTTLRefund(SnatchTestCase):
    """Pending sessions past TTL are auto-refunded."""

    def test_expired_pending_session_is_refunded(self):
        """Player closes game: bet is refunded after TTL."""
        self.wallet.ensure_user('u1', 990.0)
        self._create_pending('S3', 'u1', 10.0, server_payout=20.0,
                             age_seconds=_SNATCH_SESSION_TTL + 5)

        run_sweep(self.sdb, self.wallet)

        self.assertEqual(self.sdb.snatch_get_session('S3')['status'], 'refunded')
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 1000.0)

    def test_refund_is_idempotent_across_multiple_sweeps(self):
        """Multiple sweep runs refund exactly once."""
        self.wallet.ensure_user('u1', 990.0)
        self._create_pending('S4', 'u1', 10.0, server_payout=20.0,
                             age_seconds=_SNATCH_SESSION_TTL + 5)

        run_sweep(self.sdb, self.wallet)
        run_sweep(self.sdb, self.wallet)
        run_sweep(self.sdb, self.wallet)

        self.assertAlmostEqual(self.wallet.get_balance('u1'), 1000.0,
                               msg="Balance must not exceed original after multiple sweeps")


class TestNormalSettlement(SnatchTestCase):
    """Normal /api/snatch/end settlement."""

    def test_server_win_payout_credited(self):
        """Server pre-computed 2× payout is credited regardless of client score."""
        self.wallet.ensure_user('u1', 990.0)
        self._create_pending('S5', 'u1', 10.0, server_payout=20.0)
        ok, payout = do_end(self.sdb, self.wallet, 'S5', 'u1', score=45)
        self.assertTrue(ok)
        self.assertAlmostEqual(payout, 20.0,
                               msg="Payout must equal the server-stored value, not score-derived")
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 1010.0)
        sess = self.sdb.snatch_get_session('S5')
        self.assertEqual(sess['status'], 'settled')

    def test_server_loss_no_extra_deduction(self):
        """Server pre-computed 0 payout: balance unchanged, session settled."""
        self.wallet.ensure_user('u1', 990.0)
        self._create_pending('S6', 'u1', 10.0, server_payout=0.0)
        ok, payout = do_end(self.sdb, self.wallet, 'S6', 'u1', score=5)
        self.assertTrue(ok)
        self.assertAlmostEqual(payout, 0.0)
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 990.0,
                               msg="Balance must not decrease further on 0-payout end")
        self.assertEqual(self.sdb.snatch_get_session('S6')['status'], 'settled')

    def test_forged_high_score_cannot_inflate_payout(self):
        """Security: client sending score=200 on a server-loss session earns nothing."""
        self.wallet.ensure_user('u1', 990.0)
        # Server determined this player loses
        self._create_pending('S7', 'u1', 10.0, server_payout=0.0)
        ok, payout = do_end(self.sdb, self.wallet, 'S7', 'u1', score=200)
        self.assertTrue(ok)
        self.assertAlmostEqual(payout, 0.0,
                               msg="Forged high score must NOT affect payout")
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 990.0,
                               msg="Balance must not increase due to forged score")

    def test_expired_session_rejected(self):
        self._create_pending('S8', 'u1', 10.0, server_payout=20.0,
                             age_seconds=_SNATCH_SESSION_TTL + 5)
        ok, err = do_end(self.sdb, self.wallet, 'S8', 'u1', score=50)
        self.assertFalse(ok)
        self.assertEqual(err, 'expired')

    def test_wrong_uid_rejected(self):
        self._create_pending('S9', 'u2', 10.0, server_payout=20.0)
        ok, err = do_end(self.sdb, self.wallet, 'S9', 'u1', score=50)
        self.assertFalse(ok)
        self.assertEqual(err, 'mismatch')


class TestRaceSweepVsEnd(SnatchTestCase):
    """Concurrent sweep and /api/snatch/end race: exactly one winner."""

    def test_concurrent_end_and_sweep_exactly_one_wins(self):
        """Only one of (sweep, end) claims the session; balance changes once."""
        self.wallet.ensure_user('u1', 990.0)
        # Session just past TTL so sweep can claim it; server_payout=20 if end wins
        self._create_pending('S10', 'u1', 10.0, server_payout=20.0,
                             age_seconds=_SNATCH_SESSION_TTL + 1)
        results = []
        barrier = threading.Barrier(2)

        def run_end():
            barrier.wait()
            ok, val = do_end(self.sdb, self.wallet, 'S10', 'u1', score=40)
            results.append(('end', ok, val))

        def run_sw():
            barrier.wait()
            run_sweep(self.sdb, self.wallet)
            results.append(('sweep', True, None))

        t1 = threading.Thread(target=run_end)
        t2 = threading.Thread(target=run_sw)
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Refund: 990+10=1000.  Server win payout: 990+20=1010.
        final_bal = self.wallet.get_balance('u1')
        self.assertIn(final_bal, [1000.0, 1010.0],
                      f"Balance {final_bal} must be exactly 1000 or 1010 (not double-credited)")

    def test_duplicate_end_call_blocked(self):
        """Second /api/snatch/end on same session is rejected."""
        self._create_pending('S11', 'u1', 10.0, server_payout=15.0)
        ok1, _ = do_end(self.sdb, self.wallet, 'S11', 'u1', score=30)
        self.assertTrue(ok1)
        ok2, err2 = do_end(self.sdb, self.wallet, 'S11', 'u1', score=30)
        self.assertFalse(ok2)
        self.assertIn('settled', str(err2),
                      f"Second call must be blocked (got err={err2!r})")


class TestCrashRecovery(SnatchTestCase):
    """Crash-and-restart scenarios: intermediate states recovered by sweep."""

    def test_crash_after_settling_cas_before_credit(self):
        """Server crashed: status='settling' but no credit yet.
        Sweep re-issues the server-stored payout (idempotent) and marks settled.
        """
        self.wallet.ensure_user('u1', 990.0)
        self.sdb.snatch_create_session(
            'S12', 'u1', 10.0, None,
            time.time() - _SNATCH_SETTLING_TIMEOUT - 1,
            server_payout=20.0
        )
        self.sdb.snatch_cas_status('S12', 'intent', 'pending')
        self.sdb.snatch_cas_status('S12', 'pending', 'settling', score=40)

        run_sweep(self.sdb, self.wallet)

        sess = self.sdb.snatch_get_session('S12')
        self.assertEqual(sess['status'], 'settled')
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 1010.0)

    def test_crash_after_credit_before_settled_status(self):
        """Server crashed: credit succeeded but status still 'settling'.
        Sweep re-issues credit (idempotent no-op) and marks settled.
        Balance must be credited exactly once.
        """
        # Simulate: credit already applied
        self.wallet.credit_with_idempotency('u1', 20.0, 'snatch_payout_S13',
                                            {'success': True, 'payout': 20.0})
        self.wallet.ensure_user('u1', 1010.0)

        self.sdb.snatch_create_session(
            'S13', 'u1', 10.0, None,
            time.time() - _SNATCH_SETTLING_TIMEOUT - 1,
            server_payout=20.0
        )
        self.sdb.snatch_cas_status('S13', 'intent', 'pending')
        self.sdb.snatch_cas_status('S13', 'pending', 'settling', score=40)

        run_sweep(self.sdb, self.wallet)

        self.assertEqual(self.sdb.snatch_get_session('S13')['status'], 'settled')
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 1010.0,
                               msg="Duplicate credit must be blocked by idempotency")

    def test_crash_after_refunding_cas_before_credit(self):
        """Server crashed: status='refunding' but refund credit not issued."""
        self.wallet.ensure_user('u1', 990.0)
        self._create_pending('S14', 'u1', 10.0, server_payout=20.0,
                             age_seconds=_SNATCH_SESSION_TTL + 5)
        self.sdb.snatch_cas_status('S14', 'pending', 'refunding')

        run_sweep(self.sdb, self.wallet)

        self.assertEqual(self.sdb.snatch_get_session('S14')['status'], 'refunded')
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 1000.0)

    def test_refund_idempotent_after_credit_before_status_update(self):
        """Server crashed: refund credit issued but status still 'refunding'."""
        self.wallet.credit_with_idempotency('u1', 10.0, 'snatch_refund_S15',
                                            {'success': True, 'refunded': True})
        self.wallet.ensure_user('u1', 1000.0)

        self._create_pending('S15', 'u1', 10.0, server_payout=20.0,
                             age_seconds=_SNATCH_SESSION_TTL + 5)
        self.sdb.snatch_cas_status('S15', 'pending', 'refunding')

        run_sweep(self.sdb, self.wallet)

        self.assertEqual(self.sdb.snatch_get_session('S15')['status'], 'refunded')
        self.assertAlmostEqual(self.wallet.get_balance('u1'), 1000.0,
                               msg="Double refund must be blocked by idempotency")


class TestAlgorithmDecisionMapping(unittest.TestCase):
    """Verify the server payout computation correctly maps HouseAlgorithm decisions."""

    def test_allow_win_produces_nonzero_payout(self):
        """allow_win decision must produce a nonzero server_payout stored in session."""
        try:
            import dashboard.app as app_module
            import game_engine
        except ImportError:
            self.skipTest("Flask/dashboard not importable in this environment")
            return

        import json
        from unittest import mock

        # Inject a test user with sufficient balance
        import db_manager as dm
        gdb = dm.GameDB()
        uid = 'algo_test_win_u1'
        try:
            gdb._conn().execute(
                "INSERT OR REPLACE INTO users "
                "(telegram_id, name, game_balance) VALUES (?, 'Test', 500.0)",
                (uid,)
            )
            gdb._conn().commit()
        except Exception:
            pass

        client = app_module.app.test_client()
        app_module.app.config['TESTING'] = True

        # Mock calculate_win_chance to return 'allow_win' deterministically
        fake_result = {
            'decision': 'allow_win',
            'win_chance': 0.9,
            'factors': [],
            'reason': 'test',
        }
        with mock.patch.object(app_module._gm.algorithm, 'calculate_win_chance',
                               return_value=fake_result), \
             mock.patch.object(app_module._gm.algorithm, 'log_decision'), \
             mock.patch.object(app_module, 'BOT_TOKEN', ''):
            resp = client.post('/api/snatch/spin',
                               data=json.dumps({'bet': 10, 'uid': uid}),
                               content_type='application/json')

        if resp.status_code == 503:
            self.skipTest("SQLite not active in this environment")
            return

        self.assertEqual(resp.status_code, 200)
        d = json.loads(resp.data)
        self.assertTrue(d.get('success'), d)
        session_id = d.get('session_id')
        self.assertIsNotNone(session_id)

        # Check the stored server_payout in the session row
        sess = gdb.snatch_get_session(session_id)
        self.assertIsNotNone(sess, "Session must exist in vex_games.db")
        stored_payout = sess.get('payout', 0.0) or 0.0
        self.assertGreater(stored_payout, 0.0,
                           "allow_win decision must produce a nonzero server payout")

        # Cleanup
        try:
            gdb.snatch_delete_session(session_id)
            gdb._conn().execute("DELETE FROM users WHERE telegram_id=?", (uid,))
            gdb._conn().execute("DELETE FROM game_idempotency WHERE uid=?", (uid,))
            gdb._conn().commit()
        except Exception:
            pass

    def test_force_lose_produces_zero_payout(self):
        """force_lose decision must produce a zero server_payout stored in session."""
        try:
            import dashboard.app as app_module
            import game_engine
        except ImportError:
            self.skipTest("Flask/dashboard not importable in this environment")
            return

        import json
        from unittest import mock

        import db_manager as dm
        gdb = dm.GameDB()
        uid = 'algo_test_lose_u1'
        try:
            gdb._conn().execute(
                "INSERT OR REPLACE INTO users "
                "(telegram_id, name, game_balance) VALUES (?, 'Test', 500.0)",
                (uid,)
            )
            gdb._conn().commit()
        except Exception:
            pass

        client = app_module.app.test_client()

        fake_result = {
            'decision': 'force_lose',
            'win_chance': 0.1,
            'factors': [],
            'reason': 'test',
        }
        with mock.patch.object(app_module._gm.algorithm, 'calculate_win_chance',
                               return_value=fake_result), \
             mock.patch.object(app_module._gm.algorithm, 'log_decision'), \
             mock.patch.object(app_module, 'BOT_TOKEN', ''):
            resp = client.post('/api/snatch/spin',
                               data=json.dumps({'bet': 10, 'uid': uid}),
                               content_type='application/json')

        if resp.status_code == 503:
            self.skipTest("SQLite not active in this environment")
            return

        self.assertEqual(resp.status_code, 200)
        d = json.loads(resp.data)
        self.assertTrue(d.get('success'), d)
        session_id = d.get('session_id')

        sess = gdb.snatch_get_session(session_id)
        self.assertIsNotNone(sess)
        stored_payout = sess.get('payout') or 0.0
        self.assertAlmostEqual(stored_payout, 0.0,
                               msg="force_lose decision must produce zero server payout")

        # Cleanup
        try:
            gdb.snatch_delete_session(session_id)
            gdb._conn().execute("DELETE FROM users WHERE telegram_id=?", (uid,))
            gdb._conn().execute("DELETE FROM game_idempotency WHERE uid=?", (uid,))
            gdb._conn().commit()
        except Exception:
            pass


class TestSQLiteGuard(unittest.TestCase):
    """Spin must be rejected when the wallet is not SQLite-backed."""

    def test_spin_blocked_when_game_engine_not_sqlite(self):
        """api_snatch_spin returns 503 when game_engine._USE_SQLITE is False.

        This prevents a player from being charged through the CSV/in-memory
        wallet while their session row is written to SQLite, which would make
        crash recovery impossible (sweep cannot find the wallet idempotency
        record in a different store).
        """
        # Import the Flask app only if available in this environment.
        try:
            import dashboard.app as app_module
        except ImportError:
            self.skipTest("Flask/dashboard not importable in this environment")
            return

        client = app_module.app.test_client()
        app_module.app.config['TESTING'] = True

        import game_engine
        import json

        # Patch _USE_SQLITE to False (simulates db_manager import failure at startup)
        with unittest.mock.patch.object(game_engine, '_USE_SQLITE', False), \
             unittest.mock.patch.object(app_module, 'BOT_TOKEN', ''):
            resp = client.post('/api/snatch/spin',
                               data=json.dumps({'bet': 50, 'uid': 'guard_test_u1'}),
                               content_type='application/json')
        self.assertEqual(resp.status_code, 503,
                         "Spin must return 503 when wallet is not SQLite-backed")
        body = json.loads(resp.data)
        self.assertFalse(body.get('success', True),
                         "Response must indicate failure")


if __name__ == '__main__':
    unittest.main()
