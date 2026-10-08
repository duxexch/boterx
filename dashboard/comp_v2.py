"""
Compensation v2 extensions — wallet, referral, transfer, OTP.
Patched into app.py at import time.
"""

def register_comp_v2_routes(app, globals_dict):
    import os, secrets, threading, re, hashlib, json
    from datetime import datetime
    from flask import request, jsonify, session
    from csv_utils import read_csv, write_csv, append_csv, get_fieldnames

    BASE_DIR = globals_dict.get('BASE_DIR', os.path.dirname(os.path.dirname(__file__)))
    read_csv = globals_dict['read_csv']
    write_csv = globals_dict['write_csv']
    append_csv = globals_dict['append_csv']
    get_fieldnames = globals_dict['get_fieldnames']
    login_required = globals_dict['login_required']
    _comp_tg = globals_dict.get('_comp_tg', lambda uid, msg: None)
    _comp_alert_admins = globals_dict.get('_comp_alert_admins', lambda msg: None)
    _comp_read_accounts = globals_dict['_comp_read_accounts']
    _comp_read_pins = globals_dict['_comp_read_pins']

    _LOCK = threading.Lock()

    # ── Wallet ──
    def _read_wallets():
        return read_csv('compensation_wallets.csv')

    def _write_wallets(rows):
        write_csv('compensation_wallets.csv', rows,
                  ['user_id','company_id','company_name','frozen','available','created_at'])

    def _get_wallet(uid, cid):
        for w in _read_wallets():
            if str(w.get('user_id',''))==str(uid) and str(w.get('company_id',''))==str(cid):
                return w
        return None

    def _update_wallet(uid, cid, cname, frozen_add=0, available_add=0):
        rows = _read_wallets()
        found = False
        for w in rows:
            if str(w.get('user_id',''))==str(uid) and str(w.get('company_id',''))==str(cid):
                w['frozen'] = str(round(float(w.get('frozen',0)) + frozen_add, 2))
                w['available'] = str(round(float(w.get('available',0)) + available_add, 2))
                found = True
                break
        if not found:
            rows.append({'user_id':str(uid),'company_id':str(cid),'company_name':str(cname),
                          'frozen':str(round(max(0,frozen_add),2)),'available':str(round(max(0,available_add),2)),
                          'created_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        _write_wallets(rows)

    # ── Referral ──
    def _read_referrals():
        return read_csv('compensation_referrals.csv')

    def _write_referrals(rows):
        write_csv('compensation_referrals.csv', rows,
                  ['id','referrer_id','referred_id','company_id','company_name',
                   'referral_code','referred_account','status','created_at'])

    def _gen_ref_code(uid, cid):
        return hashlib.md5(f'{uid}:{cid}:vex'.encode()).hexdigest()[:8].upper()

    def _get_referral(code):
        for r in _read_referrals():
            if r.get('referral_code','')==code:
                return r
        return None

    def _has_referred(referrer_id, referred_id, cid):
        for r in _read_referrals():
            if str(r.get('referrer_id',''))==str(referrer_id) and str(r.get('referred_id',''))==str(referred_id) and str(r.get('company_id',''))==str(cid):
                return True
        return False

    # ── Transfer ──
    def _read_transfers():
        return read_csv('compensation_transfers.csv')

    def _write_transfers(rows):
        write_csv('compensation_transfers.csv', rows,
                  ['id','from_user','to_account','company_id','company_name',
                   'amount','status','otp_phone','created_at'])

    # ── OTP ──
    def _read_otp():
        return read_csv('compensation_otp.csv')

    def _write_otp(rows):
        write_csv('compensation_otp.csv', rows,
                  ['user_id','phone','code','used','created_at'])

    def _gen_otp():
        return str(int.from_bytes(os.urandom(2), 'big') % 10000).zfill(4)

    def _company_icons():
        icons = {}
        for c in read_csv('companies.csv'):
            icons[c.get('name', '')] = c.get('icon', '')
        return icons

    # ══════════════════════════════════════════
    # PUBLIC APIs
    # ══════════════════════════════════════════

    @app.route('/api/comp/public/wallet')
    def api_wallet():
        uid = request.args.get('user_id','').strip()
        if not uid: return jsonify({'wallets':[]})
        wallets = [w for w in _read_wallets() if str(w.get('user_id',''))==uid]
        icons = _company_icons()
        for w in wallets: w['icon'] = icons.get(w.get('company_name',''),'')
        return jsonify({'wallets':wallets})

    @app.route('/api/comp/public/request', methods=['POST'])
    def api_request():
        d = request.get_json(silent=True) or {}
        uid = str(d.get('user_id','')).strip()
        cid = str(d.get('company_id','')).strip()
        cname = str(d.get('company_name','')).strip()
        amount = str(d.get('amount','')).strip()
        if not uid: return jsonify({'error':'معرّف المستخدم مفقود'}), 400
        if not cid: return jsonify({'error':'اختر الشركة'}), 400
        try:
            amt = float(amount)
            if amt <= 0: raise ValueError
        except: return jsonify({'error':'أدخل مبلغ صحيح'}), 400
        rid = f"CR{secrets.token_hex(5).upper()}"
        with _LOCK:
            append_csv('compensation_requests.csv', {
                'id':rid,'user_id':uid,'company_id':cid,'company_name':cname,
                'account_number':'','screenshot':'','status':'pending',
                'amount':str(amt),'note':'',
                'created_at':datetime.now().strftime('%Y-%m-%d %H:%M'),
                'reviewed_at':'','reviewed_by':''
            }, get_fieldnames('compensation_requests.csv',
                ['id','user_id','company_id','company_name','account_number',
                 'screenshot','status','amount','note','created_at','reviewed_at','reviewed_by']))
        _comp_alert_admins(f"💰 <b>طلب تعويض جديد</b>\n👤 <code>{uid}</code>\n🏢 {cname}\n💵 {amt}")
        return jsonify({'ok':True,'id':rid})

    @app.route('/api/comp/public/referrals')
    def api_referrals():
        uid = request.args.get('user_id','').strip()
        if not uid: return jsonify({'referrals':[]})
        refs = [r for r in _read_referrals() if str(r.get('referrer_id',''))==uid]
        icons = _company_icons()
        for r in refs: r['icon'] = icons.get(r.get('company_name',''),'')
        return jsonify({'referrals':refs})

    @app.route('/api/comp/public/referral/link')
    def api_ref_link():
        uid = request.args.get('user_id','').strip()
        cid = request.args.get('company_id','').strip()
        cname = request.args.get('company_name','').strip()
        if not uid or not cid: return jsonify({'error':'missing'}), 400
        code = _gen_ref_code(uid, cid)
        with _LOCK:
            existing = _read_referrals()
            if not any(r.get('referral_code')==code for r in existing):
                append_csv('compensation_referrals.csv', {
                    'id':f"REF{secrets.token_hex(5).upper()}",
                    'referrer_id':uid,'referred_id':'',
                    'company_id':cid,'company_name':cname,
                    'referral_code':code,'referred_account':'',
                    'status':'waiting',
                    'created_at':datetime.now().strftime('%Y-%m-%d %H:%M')
                }, get_fieldnames('compensation_referrals.csv',
                    ['id','referrer_id','referred_id','company_id','company_name',
                     'referral_code','referred_account','status','created_at']))
        return jsonify({'link':f"https://vex.deals/compensation?ref={code}",'code':code})

    @app.route('/api/comp/public/referral/apply', methods=['POST'])
    def api_ref_apply():
        d = request.get_json(silent=True) or {}
        code = str(d.get('code','')).strip()
        uid = str(d.get('user_id','')).strip()
        if not code or not uid: return jsonify({'error':'missing'}), 400
        ref = _get_referral(code)
        if not ref: return jsonify({'error':'رابط الدعوة غير صالح'}), 404
        if ref.get('referrer_id')==uid: return jsonify({'error':'لا يمكنك دعوة نفسك'}), 400
        if _has_referred(ref['referrer_id'], uid, ref['company_id']):
            return jsonify({'error':'لقد سجلت بالفعل عبر هذا الرابط'}), 409
        with _LOCK:
            rows = _read_referrals()
            for r in rows:
                if r.get('referral_code')==code and not r.get('referred_id'):
                    r['referred_id'] = uid
                    r['status'] = 'registered'
                    break
            _write_referrals(rows)
        w = _get_wallet(ref['referrer_id'], ref['company_id'])
        frozen = float(w.get('frozen',0)) if w else 0
        if frozen > 0:
            unlock = round(min(frozen, frozen * 0.10), 2)
            if unlock > 0:
                _update_wallet(ref['referrer_id'], ref['company_id'], ref['company_name'],
                               frozen_add=-unlock, available_add=unlock)
        _comp_alert_admins(f"👥 <b>تسجيل عبر دعوة</b>\n🔗 {code}\n👤 {ref['referrer_id']} → {uid}\n🏢 {ref['company_name']}")
        return jsonify({'ok':True})

    @app.route('/api/comp/public/transfer/init', methods=['POST'])
    def api_transfer_init():
        d = request.get_json(silent=True) or {}
        uid = str(d.get('user_id','')).strip()
        cid = str(d.get('company_id','')).strip()
        cname = str(d.get('company_name','')).strip()
        amount = str(d.get('amount','')).strip()
        to_acc = str(d.get('to_account','')).strip()
        if not uid or not cid: return jsonify({'error':'missing'}), 400
        try:
            amt = float(amount)
            if amt <= 0: raise ValueError
        except: return jsonify({'error':'أدخل مبلغ صحيح'}), 400
        if not to_acc: return jsonify({'error':'أدخل رقم حساب الصديق'}), 400
        w = _get_wallet(uid, cid)
        frozen = float(w.get('frozen',0)) if w else 0
        if frozen <= 0: return jsonify({'error':'لا يوجد رصيد مجمد'}), 400
        if amt > frozen * 0.10:
            return jsonify({'error':f'الحد الأقصى {round(frozen*0.10,2)}'}), 400
        for t in _read_transfers():
            if str(t.get('from_user',''))==uid and str(t.get('to_account',''))==to_acc and str(t.get('company_id',''))==cid and t.get('status')=='completed':
                return jsonify({'error':'لقد حولت بالفعل لهذا الصديق'}), 409
        accts = _comp_read_accounts()
        to_user = ''
        for a in accts:
            if a.get('account_number','')==to_acc and a.get('company_id','')==cid:
                to_user = a.get('user_id',''); break
        if not to_user: return jsonify({'error':'الحساب غير موجود في هذه الشركة'}), 404
        if to_user==uid: return jsonify({'error':'لا يمكنك التحويل لنفسك'}), 400
        otp = _gen_otp()
        with _LOCK:
            otp_rows = _read_otp()
            otp_rows.append({'user_id':uid,'phone':'','code':otp,'used':'0',
                             'created_at':datetime.now().strftime('%Y-%m-%d %H:%M')})
            _write_otp(otp_rows)
        _comp_tg(uid, f"🔐 رمز التحقق للتحويل\n🏢 {cname}\n💵 {amt}\n🔢 {to_acc}\n\nالرمز: <code>{otp}</code>")
        pid = f"TF{secrets.token_hex(5).upper()}"
        with _LOCK:
            append_csv('compensation_transfers.csv', {
                'id':pid,'from_user':uid,'to_account':to_acc,
                'company_id':cid,'company_name':cname,
                'amount':str(amt),'status':'otp_pending',
                'otp_phone':'','created_at':datetime.now().strftime('%Y-%m-%d %H:%M')
            }, get_fieldnames('compensation_transfers.csv',
                ['id','from_user','to_account','company_id','company_name',
                 'amount','status','otp_phone','created_at']))
        return jsonify({'ok':True,'pending_id':pid,'msg':'تم إرسال رمز التحقق على التليجرام'})

    @app.route('/api/comp/public/transfer/verify', methods=['POST'])
    def api_transfer_verify():
        d = request.get_json(silent=True) or {}
        pid = str(d.get('pending_id','')).strip()
        otp = str(d.get('otp','')).strip()
        uid = str(d.get('user_id','')).strip()
        if not pid or not otp or not uid: return jsonify({'error':'missing'}), 400
        with _LOCK:
            otp_rows = _read_otp()
            valid = False
            for o in otp_rows:
                if o.get('code')==otp and o.get('user_id')==uid and o.get('used')=='0':
                    valid = True; o['used']='1'; break
            if not valid: return jsonify({'error':'الرمز غير صحيح'}), 400
            _write_otp(otp_rows)
            ts = _read_transfers()
            pending = None
            for t in ts:
                if t.get('id')==pid and t.get('status')=='otp_pending':
                    pending = t; break
            if not pending: return jsonify({'error':'الطلب غير موجود'}), 404
            cid = pending['company_id']; cname = pending['company_name']
            amt = float(pending['amount']); to_acc = pending['to_account']
            w = _get_wallet(uid, cid)
            frozen = float(w.get('frozen',0)) if w else 0
            if frozen < amt: return jsonify({'error':'الرصيد غير كافٍ'}), 400
            accts = _comp_read_accounts()
            to_user = ''
            for a in accts:
                if a.get('account_number','')==to_acc and a.get('company_id','')==cid:
                    to_user = a.get('user_id',''); break
            if not to_user: return jsonify({'error':'حساب الصديق غير موجود'}), 404
            _update_wallet(uid, cid, cname, frozen_add=-amt)
            _update_wallet(to_user, cid, cname, available_add=amt)
            for t in ts:
                if t.get('id')==pid: t['status']='completed'; break
            _write_transfers(ts)
        _comp_alert_admins(f"💸 تحويل مكتمل\n👤 {uid} → {to_user}\n🏢 {cname}\n💵 {amt}")
        return jsonify({'ok':True,'msg':'تم التحويل بنجاح'})

    @app.route('/api/comp/public/transfers')
    def api_my_transfers():
        uid = request.args.get('user_id','').strip()
        if not uid: return jsonify({'transfers':[]})
        ts = [t for t in _read_transfers() if str(t.get('from_user',''))==uid]
        return jsonify({'transfers':ts})

    # ══════════════════════════════════════════
    # ADMIN APIs
    # ══════════════════════════════════════════

    @app.route('/api/comp/admin/wallets')
    @login_required
    def api_admin_wallets():
        wallets = _read_wallets()
        icons = _company_icons()
        for w in wallets: w['icon'] = icons.get(w.get('company_name',''),'')
        return jsonify({'wallets':sorted(wallets, key=lambda w:w.get('created_at',''),reverse=True)})

    @app.route('/api/comp/admin/referrals')
    @login_required
    def api_admin_referrals():
        return jsonify({'referrals':sorted(_read_referrals(), key=lambda r:r.get('created_at',''),reverse=True)})

    @app.route('/api/comp/admin/transfers')
    @login_required
    def api_admin_transfers():
        return jsonify({'transfers':sorted(_read_transfers(), key=lambda t:t.get('created_at',''),reverse=True)})

    print("[comp-v2] wallet/referral/transfer routes registered")
