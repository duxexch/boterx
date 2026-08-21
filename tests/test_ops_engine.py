import os
import sqlite3

import agent_db


def _setup_temp_db(tmp_path):
    old = agent_db.DB_PATH
    db_path = os.path.join(str(tmp_path), 'ops_test.db')
    agent_db.DB_PATH = db_path
    agent_db.init_agent_tables()
    return old, db_path


def _teardown_temp_db(old_path):
    agent_db.DB_PATH = old_path


def _make_agent_ready():
    created = agent_db.create_agent({
        'bot_name': 'OpsAgent',
        'username': 'ops_agent',
        'security_deposit': 0,
        'traffic_weight': 1,
        'max_daily_transactions': 100,
        'max_concurrent': 20,
    })
    assert 'error' not in created
    aid = created['id']
    upd = agent_db.update_agent(aid, {'security_deposit': 0, 'traffic_on': 1, 'is_active': 1})
    assert upd is True
    bal = agent_db.adjust_balance(aid, 100000, 'credit', 'seed')
    assert bal.get('success')
    return aid


def test_ops_lifecycle_steps_to_completion(tmp_path):
    old_path, _ = _setup_temp_db(tmp_path)
    try:
        aid = _make_agent_ready()

        rid, err, assigned, _ = agent_db.create_match_request_with_agent_assignment(
            user_id='u1', customer_id='u1', req_type='deposit', amount=500,
            currency='EGP', source_type='company'
        )
        assert err is None
        assert assigned is True

        req = agent_db.get_match_request_steps(rid)
        assert req is not None
        assert req['status'] == 'waiting'
        assert req['state'] == 'created'
        assert len(req['steps']) >= 3

        # Agent cannot claim before admin approve
        deny = agent_db.claim_request(rid, 'agent', aid)
        assert 'error' in deny

        ok, err = agent_db.admin_set_match_request_status(rid, 'approved', actor='admin1')
        assert ok and err is None

        cl = agent_db.claim_request(rid, 'agent', aid)
        assert cl.get('success')

        # Execute all non-system steps with mutual confirmations
        detail = agent_db.get_match_request_steps(rid)
        for st in detail['steps']:
            role = st.get('actor_role')
            if role == 'system' or st.get('status') == 'confirmed':
                continue
            if role == 'requester':
                act = agent_db.request_step_action(rid, st['id'], 'user', 'u1', evidence_ref='REF-U')
                assert act.get('success')
                cnf = agent_db.request_step_confirm(rid, st['id'], 'agent', aid, accept=True)
                assert cnf.get('success')
            else:
                act = agent_db.request_step_action(rid, st['id'], 'agent', aid, evidence_ref='REF-A')
                assert act.get('success')
                cnf = agent_db.request_step_confirm(rid, st['id'], 'user', 'u1', accept=True)
                assert cnf.get('success')

        detail2 = agent_db.get_match_request_steps(rid)
        assert detail2['state'] == 'pre_complete'
        assert detail2['status'] == 'approved'

        # Fast-forward precomplete window and run watchdog
        conn = sqlite3.connect(agent_db.DB_PATH)
        try:
            conn.execute(
                "UPDATE match_requests SET precomplete_until='2000-01-01 00:00:00' WHERE id=?",
                (rid,)
            )
            conn.commit()
        finally:
            conn.close()

        out = agent_db.process_ops_deadlines()
        assert out.get('completed', 0) >= 1
        detail3 = agent_db.get_match_request_steps(rid)
        assert detail3['state'] == 'completed'
        assert detail3['status'] == 'matched'
    finally:
        _teardown_temp_db(old_path)


def test_cancel_guard_and_dispute_rules(tmp_path):
    old_path, _ = _setup_temp_db(tmp_path)
    try:
        rid, err, _, _ = agent_db.create_match_request_with_agent_assignment(
            user_id='u2', customer_id='u2', req_type='withdraw', amount=200,
            currency='EGP', source_type='company'
        )
        assert err is None

        ok, err = agent_db.cancel_match_request_atomic(rid, 'u2')
        assert ok is True and err is None

        # Cannot dispute after final cancellation
        dsp = agent_db.open_request_dispute(rid, 'user', 'u2', 'test')
        assert 'error' in dsp
    finally:
        _teardown_temp_db(old_path)


def test_routing_rules_block_agent(tmp_path):
    old_path, _ = _setup_temp_db(tmp_path)
    try:
        aid = _make_agent_ready()
        res = agent_db.upsert_routing_rule(
            '', 'block_agent', {'agent_id': aid}, priority=1, is_active=True
        )
        assert res.get('success')

        rid, err, assigned, _ = agent_db.create_match_request_with_agent_assignment(
            user_id='u3', customer_id='u3', req_type='deposit', amount=50,
            currency='EGP', source_type='company'
        )
        assert err is None
        assert rid
        assert assigned is False
    finally:
        _teardown_temp_db(old_path)
