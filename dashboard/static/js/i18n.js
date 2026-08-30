/* VEX i18n — shared AR/EN translation runtime for all player pages.
 *
 * Usage per page:
 *   1. <script src="/static/js/i18n.js"></script> (early, before page scripts)
 *   2. Mark static elements:  <span data-i18n="key">النص العربي</span>
 *      Placeholders:          <input data-i18n-ph="key">
 *      Titles/aria:           data-i18n-title="key"
 *   3. Page-specific keys: window.I18N_EXTRA = { key: {ar:'…', en:'…'}, … }
 *      (define BEFORE calling I18N.apply(), or call I18N.apply() after)
 *   4. JS strings: I18N.t('key') or I18N.t('key', 'نص افتراضي')
 *   5. Add a toggle button anywhere: <button onclick="I18N.toggle()">…</button>
 *      or call I18N.mountToggle() to inject a floating AR/EN pill.
 *
 * Language persists in localStorage('vex_lang'); default 'ar'.
 * Switching sets <html lang dir> (ar→rtl, en→ltr) and re-applies all
 * data-i18n bindings, then dispatches a 'vex:lang' event for dynamic UIs.
 */
(function () {
  'use strict';

  var COMMON = {
    close:        { ar: 'إغلاق', en: 'Close' },
    back:         { ar: '‹ رجوع', en: '‹ Back' },
    loading:      { ar: '⏳ جارٍ التحميل...', en: '⏳ Loading...' },
    load_failed:  { ar: 'فشل التحميل', en: 'Failed to load' },
    net_error:    { ar: 'خطأ في الشبكة — تحقق من الإنترنت', en: 'Network error — check your connection' },
    auth_error:   { ar: 'خطأ في المصادقة — أعد فتح الصفحة', en: 'Authentication error — reopen the page' },
    confirm:      { ar: 'تأكيد', en: 'Confirm' },
    cancel:       { ar: 'إلغاء', en: 'Cancel' },
    send:         { ar: 'إرسال', en: 'Send' },
    sending:      { ar: '⏳ جاري الإرسال...', en: '⏳ Sending...' },
    copied:       { ar: 'تم النسخ', en: 'Copied' },
    copy:         { ar: '📋 نسخ', en: '📋 Copy' },
    balance:      { ar: 'الرصيد', en: 'Balance' },
    amount:       { ar: 'المبلغ', en: 'Amount' },
    deposit:      { ar: 'إيداع', en: 'Deposit' },
    withdraw:     { ar: 'سحب', en: 'Withdraw' },
    games:        { ar: 'ألعاب', en: 'Games' },
    updated:      { ar: 'تم التحديث', en: 'Updated' },
    error:        { ar: 'خطأ', en: 'Error' },
    soon:         { ar: 'قريباً', en: 'Coming soon' },
    win:          { ar: 'ربح', en: 'Win' },
    lose:         { ar: 'خسارة', en: 'Loss' },
    bet:          { ar: 'رهان', en: 'Bet' },
    cashout:      { ar: 'سحب الأرباح', en: 'Cash out' },
    play:         { ar: 'العب', en: 'Play' },
    insufficient: { ar: 'رصيد غير كافٍ', en: 'Insufficient balance' },
    dashboard:    { ar: 'لوحة التحكم', en: 'Dashboard' },
    transactions: { ar: 'المعاملات', en: 'Transactions' },
    matching:     { ar: 'المطابقة', en: 'Matching' },
    agents:       { ar: 'الوكلاء', en: 'Agents' },
    trading:      { ar: 'التداول', en: 'Trading' },
    users:        { ar: 'المستخدمين', en: 'Users' },
    svrp:         { ar: 'التعويض', en: 'Compensation' },
    lottery:      { ar: 'اليانصيب', en: 'Lottery' },
    wheel:        { ar: 'العجلة', en: 'Wheel' },
    companies:    { ar: 'الشركات', en: 'Companies' },
    payment_methods: { ar: 'طرق الدفع', en: 'Payment Methods' },
    apps:         { ar: 'التطبيقات', en: 'Apps' },
    games_admin:  { ar: 'ألعاب VEX', en: 'VEX Games' },
    referrals:    { ar: 'الإحالات', en: 'Referrals' },
    channels:     { ar: 'القنوات', en: 'Channels' },
    bots:         { ar: 'البوتات', en: 'Bots' },
    browser:      { ar: 'المتصفح', en: 'Browser' },
    clients:      { ar: 'العملاء', en: 'Clients' },
    rental:       { ar: 'نظام التاجير', en: 'Rental System' },
    complaints:   { ar: 'الشكاوى', en: 'Complaints' },
    tickets:      { ar: 'التذاكر', en: 'Tickets' },
    broadcast:    { ar: 'البث', en: 'Broadcast' },
    statistics:   { ar: 'الإحصائيات', en: 'Statistics' },
    admins:       { ar: 'المسؤولين', en: 'Admins' },
    admin_center: { ar: 'مركز الإدارة', en: 'Admin Center' },
    themes:       { ar: 'الثيمات', en: 'Themes' },
    exchange_addresses: { ar: 'عناوين الصرف', en: 'Exchange Addresses' },
    send_message: { ar: 'إرسال رسالة', en: 'Send Message' },
    backup:       { ar: 'النسخ الاحتياطي', en: 'Backup' },
    settings:     { ar: 'الإعدادات', en: 'Settings' },
    ai_api_keys:  { ar: 'مفاتيح AI', en: 'AI API Keys' }
  };

  var LS_KEY = 'vex_lang';
  var lang = 'ar';
  try { lang = localStorage.getItem(LS_KEY) === 'en' ? 'en' : 'ar'; } catch (e) {}

  function dict(key) {
    var extra = window.I18N_EXTRA || {};
    return extra[key] || COMMON[key] || null;
  }

  function t(key, fallback) {
    var d = dict(key);
    if (d && d[lang] != null) return d[lang];
    if (d && d.ar != null) return d.ar;
    return fallback != null ? fallback : key;
  }

  function applyDir() {
    var html = document.documentElement;
    html.setAttribute('lang', lang);
    html.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
  }

  function apply(root) {
    root = root || document;
    applyDir();
    var els = root.querySelectorAll('[data-i18n]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i], k = el.getAttribute('data-i18n'), d = dict(k);
      if (d && d[lang] != null) el.textContent = d[lang];
    }
    els = root.querySelectorAll('[data-i18n-ph]');
    for (i = 0; i < els.length; i++) {
      var p = dict(els[i].getAttribute('data-i18n-ph'));
      if (p && p[lang] != null) els[i].setAttribute('placeholder', p[lang]);
    }
    els = root.querySelectorAll('[data-i18n-title]');
    for (i = 0; i < els.length; i++) {
      var ti = dict(els[i].getAttribute('data-i18n-title'));
      if (ti && ti[lang] != null) els[i].setAttribute('title', ti[lang]);
    }
    var tb = document.getElementById('i18nToggleBtn');
    if (tb) tb.textContent = lang === 'ar' ? 'EN' : 'ع';
    try {
      document.dispatchEvent(new CustomEvent('vex:lang', { detail: { lang: lang } }));
    } catch (e) {}
  }

  function setLang(l) {
    lang = l === 'en' ? 'en' : 'ar';
    try { localStorage.setItem(LS_KEY, lang); } catch (e) {}
    apply();
  }

  function toggle() { setLang(lang === 'ar' ? 'en' : 'ar'); }

  // Floating pill toggle — pages without their own header button call this.
  function mountToggle(opts) {
    if (document.getElementById('i18nToggleBtn')) return;
    opts = opts || {};
    var b = document.createElement('button');
    b.id = 'i18nToggleBtn';
    b.type = 'button';
    b.textContent = lang === 'ar' ? 'EN' : 'ع';
    b.setAttribute('aria-label', 'Switch language');
    b.style.cssText = opts.style ||
      'position:fixed;top:10px;inset-inline-start:10px;z-index:9999;' +
      'background:rgba(20,25,32,.9);border:1px solid #262e39;color:#00e701;' +
      'font-weight:800;font-size:12px;border-radius:999px;padding:6px 12px;' +
      'cursor:pointer;backdrop-filter:blur(6px);font-family:inherit';
    b.onclick = toggle;
    document.body.appendChild(b);
  }

  window.I18N = {
    t: t,
    apply: apply,
    setLang: setLang,
    toggle: toggle,
    mountToggle: mountToggle,
    get lang() { return lang; }
  };

  // Translate dynamically inserted content (modals, lists) when EN is active.
  var _observing = false;
  var _applying = false;
  function observe() {
    if (_observing || !window.MutationObserver || !document.body) return;
    _observing = true;
    new MutationObserver(function (muts) {
      if (_applying || lang === 'ar') return;
      _applying = true;
      try {
        muts.forEach(function (m) {
          for (var i = 0; i < m.addedNodes.length; i++) {
            var n = m.addedNodes[i];
            if (n.nodeType === 1) apply(n);
          }
        });
      } finally { _applying = false; }
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { apply(); observe(); });
  } else {
    apply();
    observe();
  }
})();
