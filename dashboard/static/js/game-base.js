// ===== VEX Games — Shared Base JavaScript =====
// Core game engine, API, sound, deposit, live players, config

// ---- i18n keys (merged into shared runtime) ----
// Arabic remains default; English is an optional toggle. Reuses COMMON keys
// from i18n.js where possible (close, cancel, error, insufficient, etc.).
window.I18N_EXTRA = Object.assign(window.I18N_EXTRA || {}, {
  gb_you:            { ar: ' (أنت)', en: ' (You)' },
  gb_no_players:     { ar: 'لا يوجد لاعبون بعد', en: 'No players yet' },
  gb_games_count:    { ar: 'لعبة', en: 'games' },
  gb_outbox_pending: { ar: 'قيد الانتظار', en: 'pending' },
  // Provably Fair
  gb_pf_title:       { ar: '🔐 Provably Fair', en: '🔐 Provably Fair' },
  gb_pf_subtitle:    { ar: 'نظام عدالة قابل للتحقق', en: 'Verifiable fairness system' },
  gb_pf_hash_lbl:    { ar: '🔐 Server Seed Hash:', en: '🔐 Server Seed Hash:' },
  gb_pf_client_lbl:  { ar: '🔑 Client Seed:', en: '🔑 Client Seed:' },
  gb_pf_nonce_lbl:   { ar: '🎲 Nonce (rolls):', en: '🎲 Nonce (rolls):' },
  gb_pf_revealed_lbl:{ ar: '🔓 Server Seed (revealed):', en: '🔓 Server Seed (revealed):' },
  gb_pf_hidden:      { ar: 'مخفي (سيكشف بعد الجولة)', en: 'Hidden (revealed after round)' },
  gb_pf_can_verify:  { ar: '✅ يمكنك التحقق من النتيجة', en: '✅ You can verify the result' },
  gb_pf_verify_btn:  { ar: '🔍 تحقق', en: '🔍 Verify' },
  gb_pf_reveal_note: { ar: 'سيتم كشف server seed بعد انتهاء الجولة للتحقق', en: 'The server seed will be revealed after the round for verification' },
  gb_pf_footer:      { ar: '🔐 يتم استخدام HMAC-SHA256 لتوليد نتائج عادلة<br>لا يمكن للخادم التلاعب بالنتيجة بعد إرسال seed hash', en: '🔐 HMAC-SHA256 is used to generate fair results<br>The server cannot tamper with the result after sending the seed hash' },
  gb_pf_verified_title:{ ar: '✅ تم التحقق', en: '✅ Verified' },
  gb_pf_result_ok:   { ar: 'النتيجة صحيحة!', en: 'Result is valid!' },
  gb_pf_results:     { ar: 'النتائج', en: 'Results' },
  gb_pf_no_seed:     { ar: 'لا يوجد seed مكشوف للتحقق', en: 'No revealed seed to verify' },
  gb_pf_verify_fail: { ar: 'فشل التحقق!', en: 'Verification failed!' },
  gb_pf_verify_err:  { ar: 'خطأ في التحقق', en: 'Verification error' },
  // goBack confirmation
  gb_leave_warn:     { ar: 'اللعبة قيام<br>ستخسر رهانك إذا خرجت', en: 'Game in progress<br>You will lose your bet if you leave' },
  gb_stay:           { ar: 'بقاء', en: 'Stay' },
  gb_leave:          { ar: 'خروج', en: 'Leave' },
  // Deposit modal
  gb_dep_title:      { ar: '💰 إيداع محفظة VEX', en: '💰 VEX Wallet Deposit' },
  gb_dep_need:       { ar: 'تحتاج', en: 'You need' },
  gb_dep_enter:      { ar: 'أدخل بيانات الإيداع', en: 'Enter deposit details' },
  gb_dep_choose:     { ar: 'اختر وسيلة الدفع', en: 'Choose a payment method' },
  gb_dep_amount:     { ar: '💵 المبلغ:', en: '💵 Amount:' },
  gb_dep_wallet_lbl: { ar: '🔐 رقم محفظتك:', en: '🔐 Your wallet number:' },
  gb_dep_wallet_ph:  { ar: 'رقم محفظتك', en: 'Your wallet number' },
  gb_dep_mname_lbl:  { ar: '📋 اسم الوسيلة:', en: '📋 Method name:' },
  gb_dep_mname_ph:   { ar: 'اسم الوسيلة', en: 'Method name' },
  gb_dep_mdata_lbl:  { ar: '📋 بيانات الحساب:', en: '📋 Account details:' },
  gb_dep_mdata_ph:   { ar: 'بيانات الحساب', en: 'Account details' },
  gb_dep_method_data:{ ar: '📋 بيانات الوسيلة:', en: '📋 Method details:' },
  gb_dep_save:       { ar: 'حفظ دائم', en: 'Save permanently' },
  gb_dep_confirm:    { ar: '✅ تأكيد الإيداع', en: '✅ Confirm deposit' },
  gb_dep_your_wallet:{ ar: '✓ محفظتك: ', en: '✓ Your wallet: ' },
  gb_dep_enter_amount:{ ar: 'أدخل المبلغ', en: 'Enter the amount' },
  gb_dep_enter_wallet:{ ar: 'أدخل رقم محفظتك', en: 'Enter your wallet number' },
  gb_dep_choose_method:{ ar: 'اختر وسيلة دفع', en: 'Choose a payment method' },
  gb_dep_enter_mname:{ ar: 'أدخل اسم الوسيلة', en: 'Enter the method name' },
  gb_dep_auth_err:   { ar: 'خطأ في المصادقة — أعد فتح اللعبة من البوت', en: 'Authentication error — reopen the game from the bot' },
  gb_dep_sent_title: { ar: 'تم إرسال طلب الإيداع', en: 'Deposit request sent' },
  gb_dep_sent_sub:   { ar: 'بانتظار موافقة الإدارة', en: 'Awaiting admin approval' },
  gb_dep_order_no:   { ar: 'رقم الطلب: ', en: 'Order no: ' },
  gb_dep_failed:     { ar: 'فشل الإيداع', en: 'Deposit failed' },
  gb_dep_conn_err:   { ar: 'خطأ في الاتصال — تحقق من الإنترنت', en: 'Connection error — check your internet' },
  gb_dep_btn_title:  { ar: 'إيداع', en: 'Deposit' }
});

// ---- Telegram WebApp Init ----
const tg = window.Telegram?.WebApp;
if (tg) { tg.expand(); tg.ready(); }

// ---- Config ----
// Encrypted session: ?s=XXX (encrypted, no uid visible, copy-proof)
// Falls back to ?uid=XXX for backward compat during migration
const urlParams = new URLSearchParams(location.search);
const sess = urlParams.get('s') || '';  // encrypted session
const uid = urlParams.get('uid') || ''; // legacy fallback only
const BASE = location.origin;
const initData = tg?.initData || '';
let soundOn = true;
let streakWin = 0;
let gameCurrency = 'EGP';

// ---- Device Fingerprint ----
function getDeviceFP() {
  var ua = navigator.userAgent || '';
  var sw = window.screen ? window.screen.width : 0;
  var sh = window.screen ? window.screen.height : 0;
  var tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  var raw = ua + '|' + sw + 'x' + sh + '|' + tz;
  var hash = 0;
  for (var i = 0; i < raw.length; i++) {
    hash = ((hash << 5) - hash) + raw.charCodeAt(i);
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16);
}

// ---- Send fingerprint to bind session to device ----
if (sess) {
  var fp = getDeviceFP();
  fetch(BASE + '/api/auth/fingerprint', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({s: sess, fp: fp})
  }).catch(function(){});
}

// ---- API Client ----
// Uses encrypted session if available, falls back to uid
function _getAuthParam() {
  if (sess) return 's=' + sess;
  if (uid) return 'uid=' + uid;
  return '';
}

async function apiFetch(url, opts = {}) {
  opts.headers = opts.headers || {};
  opts.headers['X-Telegram-Init-Data'] = initData;
  // Always send device fingerprint — needed by the nonce check to distinguish
  // same-device reuse (allowed) from cross-device replay (blocked).
  opts.headers['X-Device-FP'] = getDeviceFP();
  if (opts.body && typeof opts.body === 'string') {
    opts.headers['Content-Type'] = 'application/json';
  }
  var authParam = _getAuthParam();
  var authKey = sess ? 's=' : 'uid=';
  if (authParam && !url.includes(authKey)) {
    url += (url.includes('?') ? '&' : '?') + authParam;
  }
  return fetch(url, opts);
}

// ---- Offline Outbox (Constitution §3.2) ----
// Critical POST requests (bet, cashout) that fail due to network drop
// are saved in localStorage and auto-retried on reconnect.
var _outboxKey = 'vex_outbox_' + uid;
var _isOnline = navigator.onLine;

function _saveToOutbox(url, opts) {
  try {
    var queue = JSON.parse(localStorage.getItem(_outboxKey) || '[]');
    queue.push({ url: url, opts: opts, ts: Date.now() });
    localStorage.setItem(_outboxKey, JSON.stringify(queue));
  } catch(e) {}
}

function _processOutbox() {
  try {
    var queue = JSON.parse(localStorage.getItem(_outboxKey) || '[]');
    if (queue.length === 0) return;
    var remaining = [];
    var processed = 0;
    queue.forEach(function(item) {
      if (processed >= 5) { remaining.push(item); return; }
      fetch(item.url, item.opts).then(function(r) {
        if (!r.ok) remaining.push(item);
      }).catch(function() { remaining.push(item); });
      processed++;
    });
    // Save any that failed again, plus unprocessed ones
    localStorage.setItem(_outboxKey, JSON.stringify(remaining));
    if (remaining.length > 0) {
      showToast('Outbox: ' + remaining.length + ' ' + I18N.t('gb_outbox_pending'), 'info');
    }
  } catch(e) {}
}

// Listen for online/offline events
window.addEventListener('online', function() {
  _isOnline = true;
  var ci = document.getElementById('connIndicator');
  if (ci) ci.textContent = '\uD83D\uDFE2';
  setTimeout(_processOutbox, 1000);
});
window.addEventListener('offline', function() {
  _isOnline = false;
  var ci = document.getElementById('connIndicator');
  if (ci) ci.textContent = '\uD83D\uDD34';
});

// Wrapper for critical POST requests (bet, cashout) — saves to outbox on failure.
// Auto-generates a stable X-Request-Id per logical action so the server can
// deduplicate retries (outbox or manual). The ID is injected into headers and
// body before the first attempt so it survives unchanged across all retries.
function _genRequestId() {
  return 'rid_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
}

async function apiFetchCritical(url, opts) {
  opts = opts || {};
  opts.headers = opts.headers || {};
  opts.headers['X-Telegram-Init-Data'] = initData;
  opts.method = opts.method || 'POST';

  // Inject a stable request_id once (idempotent if already present for retries)
  if (!opts.headers['X-Request-Id']) {
    var rid = _genRequestId();
    opts.headers['X-Request-Id'] = rid;
    // Also embed in JSON body so server can read it from either location
    if (opts.body && typeof opts.body === 'string') {
      try {
        var bodyObj = JSON.parse(opts.body);
        if (!bodyObj.request_id) {
          bodyObj.request_id = rid;
          opts.body = JSON.stringify(bodyObj);
        }
      } catch(e) { /* non-JSON body — header is enough */ }
    }
  }

  if (opts.body && typeof opts.body === 'string') {
    opts.headers['Content-Type'] = 'application/json';
  }
  if (sess) opts.headers['X-Device-FP'] = getDeviceFP();
  var authParam = _getAuthParam();
  var authKey = sess ? 's=' : 'uid=';
  if (authParam && !url.includes(authKey)) {
    url += (url.includes('?') ? '&' : '?') + authParam;
  }
  try {
    var r = await fetch(url, opts);
    if (!r.ok && r.status >= 500) {
      _saveToOutbox(url, opts);
    }
    return r;
  } catch(e) {
    // Network error — save to outbox for retry (opts already has X-Request-Id)
    _saveToOutbox(url, opts);
    throw e;
  }
}

// ---- Audio Engine ----
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
let audioMuted = false;

function beep(f, d, t = 'sine', v = 0.12) {
  if (!soundOn || audioMuted) return;
  try {
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.connect(g); g.connect(audioCtx.destination);
    o.frequency.value = f; o.type = t;
    g.gain.setValueAtTime(v, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + d);
    o.start(); o.stop(audioCtx.currentTime + d);
  } catch (e) { /* ignore */ }
}

function soundWin(big = false) {
  const base = big ? 660 : 523;
  beep(base, 0.08); setTimeout(() => beep(base * 1.5, 0.12), 60);
  setTimeout(() => beep(base * 2, 0.15), 120);
  if (big) setTimeout(() => beep(base * 3, 0.2), 180);
}

function soundLose() { beep(200, 0.3, 'sawtooth', 0.15); }
function soundTick() { beep(660, 0.02, 'sine', 0.04); }
function soundCrash() { beep(200, 0.3, 'sawtooth', 0.25); setTimeout(() => beep(100, 0.2, 'square', 0.15), 100); }
function soundCashOut() { beep(523, 0.08); setTimeout(() => beep(784, 0.12), 60); setTimeout(() => beep(1047, 0.15), 120); }

function toggleSound() {
  soundOn = !soundOn;
  const btn = document.getElementById('soundBtn');
  if (btn) btn.textContent = soundOn ? '🔊' : '🔇';
  localStorage.setItem('vex_sound', soundOn ? '1' : '0');
}

// Load sound pref
soundOn = localStorage.getItem('vex_sound') !== '0';

// ---- Provably Fair badge auto-inject ----
function injectPFBadge() {
  const topbar = document.querySelector('.topbar-right');
  if (topbar && !document.getElementById('pfBadge')) {
    const badge = document.createElement('span');
    badge.id = 'pfBadge';
    badge.className = 'pf-badge';
    badge.onclick = showProvablyFairModal;
    topbar.insertBefore(badge, topbar.firstChild);
  }
}

// Auto-init provably fair when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { injectPFBadge(); initProvablyFair(); });
} else {
  injectPFBadge(); initProvablyFair();
}

// ---- Haptics ----
function haptic(t = 'light') {
  if (tg?.HapticFeedback?.impactOccurred) {
    try { tg.HapticFeedback.impactOccurred(t); } catch (e) { /* ignore */ }
  }
}

// ---- Balance ----
async function loadBalance() {
  try {
    const r = await apiFetch(`${BASE}/api/wallet/balance`);
    if (r.status === 401 || r.status === 403) {
      // Not a game-authenticated user (e.g. admin viewing the page) — stop polling
      if (window._stopLotteryPolls) window._stopLotteryPolls();
      return;
    }
    const d = await r.json();
    const balEl = document.getElementById('bal');
    const curEl = document.getElementById('cur');
    if (d.balance !== undefined) {
      const prevBal = balEl ? parseFloat(balEl.textContent.replace(/,/g, '')) || 0 : 0;
      if (balEl) {
        balEl.textContent = (d.balance || 0).toLocaleString();
        if (d.balance > prevBal) {
          balEl.classList.add('flash-green');
          setTimeout(() => balEl.classList.remove('flash-green'), 600);
        } else if (d.balance < prevBal) {
          balEl.classList.add('flash-red');
          setTimeout(() => balEl.classList.remove('flash-red'), 600);
        }
      }
      if (curEl && d.currency) { curEl.textContent = d.currency; gameCurrency = d.currency; }
    }
  } catch (e) { /* ignore */ }
}

// ---- Streak ----
function updateStreak(badgeEl) {
  if (!badgeEl) return;
  if (streakWin >= 2) {
    badgeEl.style.display = 'block';
    badgeEl.textContent = '🔥 ' + streakWin;
  } else {
    badgeEl.style.display = 'none';
  }
}

// ---- History ----
function addHistory(containerId, value, isWin, isBig) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'hist-item ' + (isBig ? 'hist-big' : isWin ? 'hist-win' : 'hist-lose');
  el.textContent = value.toFixed(2) + 'x';
  container.insertBefore(el, container.firstChild);
  if (container.children.length > 15) container.removeChild(container.lastChild);
}

// ---- Toast ----
function showToast(msg, type = 'info') {
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = msg;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 2500);
}

// ---- Confetti ----
function fireConfetti(gameAreaEl) {
  if (!gameAreaEl) return;
  const colors = ['#fbbf24', '#00e701', '#a78bfa', '#ff4757', '#3b82f6', '#06b6d4'];
  for (let i = 0; i < 30; i++) {
    const c = document.createElement('div');
    c.className = 'confetti-piece';
    c.style.left = Math.random() * 100 + '%';
    c.style.top = -10 + 'px';
    c.style.background = colors[Math.floor(Math.random() * colors.length)];
    c.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
    gameAreaEl.appendChild(c);
    const angle = (Math.random() - 0.5) * 0.5;
    const dist = 80 + Math.random() * 150;
    const dur = 800 + Math.random() * 600;
    c.animate([
      { transform: 'translate(0,0) rotate(0deg)', opacity: 1 },
      { transform: `translate(${Math.cos(angle) * dist}px, ${-dist}px) rotate(${Math.random() * 720}deg)`, opacity: 0 }
    ], { duration: dur, easing: 'ease-out' });
    setTimeout(() => c.remove(), dur);
  }
}

// ---- Chat / Emoji Reactions ----
let _chatSSE = null;
const QUICK_EMOJIS = ['🔥', '💎', '🚀', '💰', '😱', '😂', '💪', '🎉'];

function connectChatStream() {
  const container = document.querySelector('.chat-messages');
  if (!container) return;
  try {
    const url = BASE + '/api/games/chat/stream?' + _getAuthParam();
    _chatSSE = new EventSource(url);
    _chatSSE.onmessage = function(e) {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'chat' && d.data) {
          addChatMessage(d.data);
        }
      } catch(err) { /* ignore */ }
    };
    _chatSSE.onerror = function() {
      _chatSSE.close();
      _chatSSE = null;
      // Fallback: poll history
      setTimeout(pollChatHistory, 3000);
    };
  } catch(e) {
    pollChatHistory();
  }
}

async function pollChatHistory() {
  try {
    const r = await apiFetch(BASE + '/api/games/chat/history');
    const d = await r.json();
    if (d.messages) {
      d.messages.forEach(m => addChatMessage(m, false));
    }
  } catch(e) { /* ignore */ }
}

function addChatMessage(msg, animate = true) {
  const container = document.querySelector('.chat-messages');
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'chat-msg';
  if (msg.emoji && !msg.message) {
    el.innerHTML = `<span class="chat-name">${msg.name}:</span> <span class="chat-emoji">${msg.emoji}</span>`;
  } else {
    el.innerHTML = `<span class="chat-name">${msg.name}:</span> <span class="chat-text">${msg.message || ''}</span>${msg.emoji ? ' <span class="chat-emoji">' + msg.emoji + '</span>' : ''}`;
  }
  container.appendChild(el);
  if (container.children.length > 30) container.removeChild(container.firstChild);
  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage() {
  const input = document.querySelector('.chat-input');
  if (!input) return;
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  try {
    await apiFetch(BASE + '/api/games/chat/send', {
      method: 'POST',
      body: JSON.stringify({ message: msg })
    });
  } catch(e) { /* ignore */ }
}

async function sendEmoji(emoji) {
  try {
    await apiFetch(BASE + '/api/games/chat/send', {
      method: 'POST',
      body: JSON.stringify({ emoji: emoji })
    });
    haptic('light');
  } catch(e) { /* ignore */ }
}

function toggleChat() {
  const bar = document.querySelector('.chat-bar');
  if (bar) {
    const isHidden = bar.style.display === 'none';
    bar.style.display = isHidden ? 'flex' : 'none';
  }
}

// Auto-inject chat bar into game pages
// Chat bar DISABLED — no user-to-user interaction per user request
// injectChatBar, connectChatStream, sendChatMessage, sendEmoji all removed

// ---- Stars Background ----
function createStars(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  for (let i = 0; i < 30; i++) {
    const s = document.createElement('div');
    s.className = 'star';
    s.style.left = Math.random() * 100 + '%';
    s.style.top = Math.random() * 100 + '%';
    s.style.animationDelay = Math.random() * 3 + 's';
    container.appendChild(s);
  }
}

// ---- Live Players (shared) ----
const livePlayers = [];
let _lpSSE = null;
let _lpSSEFallback = null;

function addPlayer(data) {
  const idx = livePlayers.findIndex(p => p.uid === data.uid);
  if (idx >= 0) livePlayers[idx] = data;
  else { livePlayers.unshift(data); if (livePlayers.length > 20) livePlayers.pop(); }
  renderPlayers();
}

function renderPlayers() {
  const countEl = document.getElementById('lpCount');
  const totalEl = document.getElementById('lpTotal');
  const listEl = document.getElementById('lpList');
  if (!listEl) return;
  if (countEl) countEl.textContent = livePlayers.length;
  if (totalEl) totalEl.textContent = '💰 ' + livePlayers.reduce((s, p) => s + (p.bet || 0), 0).toLocaleString();
  listEl.innerHTML = '';
  livePlayers.forEach(p => {
    const row = document.createElement('div');
    row.className = 'lp-row ' + (p.status || '') + (p.isMe ? ' me' : '');
    const avatar = (p.name || '?')[0].toUpperCase();
    const mult = p.multiplier > 0 ? `<span class="lp-mult ${p.status === 'win' ? 'win' : 'lose'}">${p.multiplier.toFixed(2)}x</span>` : '';
    row.innerHTML = `
      <div class="lp-user"><div class="lp-avatar">${avatar}</div><span>${p.name || '???'}${p.isMe ? I18N.t('gb_you') : ''}</span></div>
      <div style="display:flex;align-items:center;gap:6px"><span style="font-weight:700">${p.bet || 0}</span>${mult}</div>`;
    listEl.appendChild(row);
  });
}

// Connect to real SSE live players stream
function connectLivePlayersStream() {
  try {
    if (_lpSSE) _lpSSE.close();
    const url = BASE + '/api/games/live-players/stream?' + _getAuthParam();
    _lpSSE = new EventSource(url);
    _lpSSE.onmessage = function(e) {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'live_players' && d.players) {
          livePlayers.length = 0;
          d.players.forEach(p => {
            livePlayers.push({
              uid: p.uid,
              name: p.name || '',
              bet: p.bet || 0,
              status: p.status || 'lose',
              multiplier: p.multiplier || 0,
              isMe: p.uid === uid
            });
          });
          renderPlayers();
        }
      } catch(err) { /* ignore parse errors */ }
    };
    _lpSSE.onerror = function() {
      _lpSSE.close();
      _lpSSE = null;
      // Fallback to polling API every 3s
      if (!_lpSSEFallback) {
        _lpSSEFallback = setInterval(pollLivePlayers, 3000);
        pollLivePlayers();
      }
    };
  } catch(e) {
    // SSE not supported, use polling fallback
    if (!_lpSSEFallback) {
      _lpSSEFallback = setInterval(pollLivePlayers, 3000);
      pollLivePlayers();
    }
  }
}

// Polling fallback for live players
async function pollLivePlayers() {
  try {
    const r = await apiFetch(BASE + '/api/games/live-players');
    const d = await r.json();
    if (d.players) {
      livePlayers.length = 0;
      d.players.forEach(p => {
        livePlayers.push({
          uid: p.uid,
          name: p.name || '',
          bet: p.bet || 0,
          status: p.status || 'lose',
          multiplier: p.multiplier || 0,
          isMe: p.uid === uid
        });
      });
      renderPlayers();
    }
  } catch(e) { /* ignore */ }
}

// Simulated players (fallback only when no real data available)
// NOTE: SSE live-players/leaderboard streams DISABLED to prevent thread
// exhaustion on 1-core server. Using polling fallback only.
function simulatePlayers() {
  // Do NOT connect SSE — it exhausts gunicorn threads on 1-core server.
  // Use polling fallback instead (lighter on server resources).
  if (!_lpSSEFallback) {
    _lpSSEFallback = setInterval(pollLivePlayers, 5000);
    pollLivePlayers();
  }
  // Add a fake player occasionally if list is empty
  if (livePlayers.length < 3) {
    const names = ['أحمد', 'عمر', 'محمد', 'خالد', 'سعد', 'فهد', 'ناصر', 'يوسف', 'علي', 'حسن'];
    addPlayer({
      uid: 'sim_' + Math.random().toString(36).substr(2, 5),
      name: names[Math.floor(Math.random() * names.length)],
      bet: [10, 20, 50, 100, 200, 500][Math.floor(Math.random() * 6)],
      status: Math.random() < 0.4 ? 'win' : 'lose',
      multiplier: Math.random() < 0.4 ? 1 + Math.random() * 4 : 0,
      isMe: false
    });
  }
  renderPlayers();
}

// ---- Leaderboard (for games hub) ----
function connectLeaderboardStream(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  try {
    const url = BASE + '/api/games/leaderboard/stream?' + _getAuthParam();
    const es = new EventSource(url);
    es.onmessage = function(e) {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'leaderboard' && d.leaderboard) {
          renderLeaderboard(containerId, d.leaderboard);
        }
      } catch(err) { /* ignore */ }
    };
    es.onerror = function() {
      es.close();
      // Fallback: poll once
      apiFetch(BASE + '/api/games/leaderboard').then(r => r.json()).then(d => {
        if (d.leaderboard) renderLeaderboard(containerId, d.leaderboard);
      }).catch(() => {});
    };
  } catch(e) {
    apiFetch(BASE + '/api/games/leaderboard').then(r => r.json()).then(d => {
      if (d.leaderboard) renderLeaderboard(containerId, d.leaderboard);
    }).catch(() => {});
  }
}

function renderLeaderboard(containerId, players) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!players || players.length === 0) {
    el.innerHTML = '<div style="text-align:center;color:var(--muted);padding:16px;font-size:12px">' + I18N.t('gb_no_players') + '</div>';
    return;
  }
  el.innerHTML = players.map((p, i) => {
    const rank = i + 1;
    const medal = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `<span style="color:var(--muted)">${rank}</span>`;
    const profit = p.profit || 0;
    const profitClass = profit > 0 ? 'win' : profit < 0 ? 'lose' : '';
    const profitStr = (profit >= 0 ? '+' : '') + profit.toFixed(0);
    return `<div class="lb-row ${profitClass}">
      <span class="lb-rank">${medal}</span>
      <span class="lb-name">${p.name || '???'}${p.uid === uid ? I18N.t('gb_you') : ''}</span>
      <span class="lb-profit">${profitStr}</span>
      <span class="lb-games">${p.games || 0} ${I18N.t('gb_games_count')}</span>
    </div>`;
  }).join('');
}

// ---- Bet Panel Helpers ----
function updatePotential(inputId, autoId, outputId) {
  const bet = parseFloat(document.getElementById(inputId || 'betInput').value) || 0;
  const auto = parseFloat(document.getElementById(autoId || 'autoVal').value) || 0;
  const autoChecked = document.getElementById('autoCashout')?.checked;
  const pot = autoChecked && auto > 1 ? (bet * auto) : bet * 2;
  const el = document.getElementById(outputId || 'potVal');
  if (el) el.textContent = pot.toFixed(2);
}

function adjustBet(factor, inputId) {
  const inp = document.getElementById(inputId || 'betInput');
  let v = parseFloat(inp.value) || 0;
  v = Math.max(1, Math.floor(v * factor));
  inp.value = v;
  updatePotential();
}

function setBet(type, inputId, min, max) {
  const inp = document.getElementById(inputId || 'betInput');
  inp.value = type === 'min' ? (min || 10) : (max || 5000);
  updatePotential();
}

// ---- Provably Fair (shared) ----
let pfSessionId = null;
let pfSeedHash = null;
let pfClientSeed = null;
let pfNonce = 0;
let pfRevealedSeed = null;

async function initProvablyFair() {
  try {
    const r = await apiFetch(`${BASE}/api/provably-fair/seed`);
    const d = await r.json();
    if (d.seed_hash) {
      pfSessionId = d.session_id;
      pfSeedHash = d.seed_hash;
      pfClientSeed = d.client_seed;
      pfNonce = 0;
      updatePFBadge();
    }
  } catch (e) { /* ignore */ }
}

function updatePFBadge() {
  const badge = document.getElementById('pfBadge');
  if (badge && pfSeedHash) {
    badge.style.display = 'block';
    badge.textContent = '🔐 Fair';
    badge.title = 'Provably Fair: ' + pfSeedHash.substring(0, 16) + '...';
  }
}

function showProvablyFairModal() {
  const overlay = document.createElement('div');
  overlay.id = 'pfModal';
  overlay.className = 'modal-overlay';
  overlay.style.display = 'flex';
  overlay.innerHTML = `<div class="modal-box" id="pfBox"></div>`;
  document.body.appendChild(overlay);
  const box = document.getElementById('pfBox');

  const hashShort = pfSeedHash ? pfSeedHash.substring(0, 32) + '...' : '---';
  const seedShort = pfRevealedSeed ? pfRevealedSeed.substring(0, 32) + '...' : I18N.t('gb_pf_hidden');

  box.innerHTML = `
    <div class="modal-title">${I18N.t('gb_pf_title')}</div>
    <div class="modal-subtitle">${I18N.t('gb_pf_subtitle')}</div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">${I18N.t('gb_pf_hash_lbl')}</div>
      <code style="font-size:11px;color:var(--gold);word-break:break-all">${hashShort}</code>
    </div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">${I18N.t('gb_pf_client_lbl')}</div>
      <code style="font-size:12px;color:var(--cyan)">${pfClientSeed || '---'}</code>
    </div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">${I18N.t('gb_pf_nonce_lbl')}</div>
      <code style="font-size:14px;color:var(--green)">${pfNonce}</code>
    </div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">${I18N.t('gb_pf_revealed_lbl')}</div>
      <code style="font-size:11px;color:${pfRevealedSeed ? 'var(--green)' : 'var(--muted)'};word-break:break-all">${seedShort}</code>
    </div>
    ${pfRevealedSeed ? `
    <div style="background:rgba(0,231,1,0.08);border:1px solid rgba(0,231,1,0.3);border-radius:8px;padding:8px;margin:6px 0;text-align:center">
      <div style="font-size:11px;color:var(--green)">${I18N.t('gb_pf_can_verify')}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px">SHA256(server_seed) = seed_hash</div>
    </div>
    <button class="modal-btn-primary" onclick="verifyPF()">${I18N.t('gb_pf_verify_btn')}</button>
    ` : `
    <div style="font-size:11px;color:var(--muted);text-align:center;padding:8px">
      ${I18N.t('gb_pf_reveal_note')}
    </div>
    `}
    <div style="font-size:10px;color:var(--muted);text-align:center;margin-top:8px;line-height:1.5">
      ${I18N.t('gb_pf_footer')}
    </div>
    <button class="modal-btn-secondary" onclick="document.getElementById('pfModal').remove()">${I18N.t('close')}</button>
  `;
}

async function verifyPF() {
  if (!pfRevealedSeed) {
    showToast(I18N.t('gb_pf_no_seed'), 'error');
    return;
  }
  try {
    const r = await apiFetch(`${BASE}/api/provably-fair/verify`, {
      method: 'POST',
      body: JSON.stringify({
        server_seed: pfRevealedSeed,
        client_seed: pfClientSeed,
        nonce: pfNonce,
        max_value: 10000
      })
    });
    const d = await r.json();
    if (d.valid) {
      const box = document.getElementById('pfBox');
      box.innerHTML = `
        <div class="modal-title">${I18N.t('gb_pf_verified_title')}</div>
        <div style="background:rgba(0,231,1,0.08);border:1px solid rgba(0,231,1,0.3);border-radius:8px;padding:12px;margin:8px 0;text-align:center">
          <div style="font-size:28px">✅</div>
          <div style="font-size:13px;color:var(--green);font-weight:700">${I18N.t('gb_pf_result_ok')}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:4px">SHA256 matched ✓</div>
          <div style="font-size:11px;color:var(--muted)">Results: ${d.results.join(', ')}</div>
        </div>
        <button class="modal-btn-secondary" onclick="document.getElementById('pfModal').remove()">${I18N.t('close')}</button>
      `;
      soundWin();
    } else {
      showToast(I18N.t('gb_pf_verify_fail'), 'error');
    }
  } catch (e) {
    showToast(I18N.t('gb_pf_verify_err'), 'error');
  }
}

async function revealPFSession() {
  if (!pfSessionId) return;
  try {
    const r = await apiFetch(`${BASE}/api/provably-fair/reveal/${pfSessionId}`);
    const d = await r.json();
    if (d.server_seed) {
      pfRevealedSeed = d.server_seed;
    }
  } catch (e) { /* ignore */ }
}

// ---- Deposit URL ----
function goBack() {
  // Constitution §4.2: BackButton MUST intercept if game is in progress
  // Check if any game is active (Aviator/Crash flying, Mines playing, etc.)
  var gameActive = typeof roundPhase !== 'undefined' && (roundPhase === 'flying' || roundPhase === 'playing');
  if (typeof gameState !== 'undefined' && gameState === 'playing') gameActive = true;
  if (gameActive) {
    // Show confirmation modal instead of closing
    var c = document.createElement('div');
    c.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:500;display:flex;align-items:center;justify-content:center';
    var box = document.createElement('div');
    box.style.cssText = 'background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;max-width:300px;text-align:center';
    box.innerHTML = '<div style="font-size:28px;margin-bottom:8px">\u26A0\uFE0F</div>' +
      '<div style="font-size:14px;font-weight:700;margin-bottom:12px">' + I18N.t('gb_leave_warn') + '</div>' +
      '<div style="display:flex;gap:8px">' +
      '<button id="_stayBtn" style="flex:1;padding:10px;border-radius:8px;border:none;background:var(--green-dim);color:#fff;font-weight:700">' + I18N.t('gb_stay') + '</button>' +
      '<button id="_leaveBtn" style="flex:1;padding:10px;border-radius:8px;border:none;background:var(--red-dim);color:#fff;font-weight:700">' + I18N.t('gb_leave') + '</button>' +
      '</div>';
    c.appendChild(box);
    document.body.appendChild(c);
    document.getElementById('_stayBtn').onclick = function() { c.remove(); };
    document.getElementById('_leaveBtn').onclick = function() { c.remove(); window.location.href = BASE + '/webapp/games?' + _getAuthParam() + '&lang=ar'; };
    return;
  }
  window.location.href = BASE + '/webapp/games?' + _getAuthParam() + '&lang=ar';
}

// ---- Constitution §4: Telegram Mini App Integration ----
// MainButton sync with game state
function syncMainButton(text, onClick) {
  if (!tg || !tg.MainButton) return;
  try {
    tg.MainButton.setText(text);
    tg.MainButton.show();
    tg.MainButton.onClick(onClick);
  } catch(e) {}
}

function hideMainButton() {
  if (!tg || !tg.MainButton) return;
  try { tg.MainButton.hide(); } catch(e) {}
}

// BackButton intercept (Constitution §4.2)
function enableBackButton() {
  if (!tg || !tg.BackButton) return;
  try { tg.BackButton.show(); tg.BackButton.onClick(function() { goBack(); }); } catch(e) {}
}

function disableBackButton() {
  if (!tg || !tg.BackButton) return;
  try { tg.BackButton.hide(); } catch(e) {}
}

// Theme change listener (Constitution §4.3)
function initThemeListener() {
  if (!tg || !tg.onEvent) return;
  try {
    tg.onEvent('themeChanged', function() {
      var tc = tg.themeParams || {};
      var root = document.documentElement;
      if (tc.bg_color) root.style.setProperty('--bg', tc.bg_color);
      if (tc.text_color) root.style.setProperty('--text', tc.text_color);
      if (tc.button_color) root.style.setProperty('--gold', tc.button_color);
      if (tc.hint_color) root.style.setProperty('--muted', tc.hint_color);
    });
  } catch(e) {}
}

// Auto-init TMA features when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function() { try { initThemeListener(); enableBackButton(); } catch(e) {} });
} else {
  try { initThemeListener(); enableBackButton(); } catch(e) {}
}

// ---- VEX Deposit Modal (shared) ----
let vMethods = [], vSaved = [], vSelected = null;

// أيقونة وسيلة/شركة: صورة مرفوعة → <img>، غير ذلك → نص إيموجي
// (سابقاً كان مسار /static/... يُطبع كنص فيظهر رابطاً بدل الأيقونة)
function _gbIsImg(ic){ return typeof ic === 'string' && (ic.indexOf('/static/') === 0 || ic.indexOf('http') === 0); }
function _gbIcon(ic, fallback, size){
  size = size || 20;
  if (_gbIsImg(ic)) return '<img src="' + ic + '" style="width:' + size + 'px;height:' + size + 'px;border-radius:8px;object-fit:cover;flex-shrink:0" alt="">';
  return '<span style="font-size:' + size + 'px">' + (ic || fallback || '💳') + '</span>';
}

async function showVexDepositModal(required) {
  const overlay = document.createElement('div');
  overlay.id = 'modal';
  overlay.className = 'modal-overlay';
  overlay.style.display = 'flex';
  overlay.innerHTML = '<div class="modal-box" id="mb"></div>';
  document.body.appendChild(overlay);
  const mb = document.getElementById('mb');

  // الخطوة 1: اختيار مصدر الإيداع — محفظة VEX أو شركة
  mb.innerHTML = `
    <div class="modal-title">${I18N.t('gb_dep_title')}</div>
    <div class="modal-subtitle">${required ? I18N.t('gb_dep_need') + ' ' + required : I18N.t('gb_dep_choose')}</div>
    <div class="method-item" onclick="vChooseWallet()" style="cursor:pointer">
      ${_gbIcon('👛', '👛', 22)}
      <div class="method-info"><div class="method-name">${I18N.t('gb_dep_wallet_title') || '👛 محفظة VEX'}</div>
      <div class="method-type">${I18N.t('gb_dep_wallet_sub') || 'إيداع لمحفظتك — وسائل دفع متعددة'}</div></div>
      <span class="method-arrow">‹</span>
    </div>
    <div class="method-item" onclick="vChooseCompany()" style="cursor:pointer">
      ${_gbIcon('🏢', '🏢', 22)}
      <div class="method-info"><div class="method-name">${I18N.t('gb_dep_company_title') || '🏢 شركة'}</div>
      <div class="method-type">${I18N.t('gb_dep_company_sub') || 'إيداع لحسابك في شركة — اختر الشركة والوسيلة'}</div></div>
      <span class="method-arrow">‹</span>
    </div>
    <button class="modal-btn-secondary" onclick="document.getElementById('modal').remove()">${I18N.t('close')}</button>`;
}

let vCtx = { source: 'wallet', company_id: '', company_name: '' };

// ── مسار المحفظة: الوسائل مباشرة ──
async function vChooseWallet() {
  vCtx = { source: 'wallet', company_id: '', company_name: '' };
  const mb = document.getElementById('mb');
  if (!mb) return;
  mb.innerHTML = '<div class="modal-title">' + I18N.t('gb_dep_title') + '</div><div class="modal-subtitle">⏳</div>';
  try {
    const r = await apiFetch(`${BASE}/api/games/payment-methods`);
    const d = await r.json();
    vMethods = d.methods || [];
    vSaved = d.saved_methods || [];
  } catch (e) { vMethods = []; vSaved = []; }
  vRenderMethods();
}

// ── مسار الشركة: الشركات ← الوسائل ──
async function vChooseCompany() {
  vCtx = { source: 'company', company_id: '', company_name: '' };
  const mb = document.getElementById('mb');
  if (!mb) return;
  mb.innerHTML = '<div class="modal-title">' + I18N.t('gb_dep_title') + '</div><div class="modal-subtitle">⏳</div>';
  let companies = [];
  try {
    const r = await apiFetch(`${BASE}/api/companies/list`);
    const d = await r.json();
    companies = d.companies || [];
  } catch (e) {}
  if (companies.length === 0) {
    mb.innerHTML = '<div class="modal-title">' + I18N.t('gb_dep_title') + '</div>' +
      '<div class="modal-subtitle">' + (I18N.t('gb_dep_no_companies') || 'لا توجد شركات متاحة حالياً') + '</div>' +
      '<button class="modal-btn-secondary" onclick="showVexDepositModal(0)">' + I18N.t('back') + '</button>';
    return;
  }
  const cHtml = companies.map(c => `
    <div class="method-item" onclick="vCompanySel('${c.id}','${(c.name||'').replace(/'/g,"\\'")}')">
      ${_gbIcon(c.icon, '🏢', 24)}
      <div class="method-info"><div class="method-name">${c.name||''}</div>
      <div class="method-type">${c.address||''}</div></div>
      <span class="method-arrow">‹</span>
    </div>`).join('');
  mb.innerHTML = `
    <div class="modal-title">${I18N.t('gb_dep_title')}</div>
    <div class="modal-subtitle">${I18N.t('x236') || '🏢 اختر الشركة'}</div>
    <div id="vc">${cHtml}</div>
    <button class="modal-btn-secondary" onclick="showVexDepositModal(0)">${I18N.t('back')}</button>`;
}

async function vCompanySel(cid, cname) {
  vCtx.company_id = cid; vCtx.company_name = cname;
  const mb = document.getElementById('mb');
  if (!mb) return;
  mb.innerHTML = '<div class="modal-title">' + I18N.t('gb_dep_title') + '</div><div class="modal-subtitle">⏳</div>';
  try {
    const r = await apiFetch(`${BASE}/api/payment-methods/by-company/${cid}`);
    const d = await r.json();
    vMethods = d.methods || [];
  } catch (e) { vMethods = []; }
  vSaved = [];
  vRenderMethods();
}

// ── قائمة الوسائل (بالطبقتين: الاختيار ثم التفاصيل والتأكيد) ──
function vRenderMethods() {
  const mb = document.getElementById('mb');
  if (!mb) return;
  if (vMethods.length === 0) {
    // No methods — manual entry
    mb.innerHTML = `<div class="modal-title">${I18N.t('gb_dep_title')}</div>
      <div class="modal-subtitle">${I18N.t('gb_dep_enter_amount') || 'لا توجد وسائل متاحة — أدخل البيانات يدوياً'}</div>
      <div class="modal-subtitle">${I18N.t('gb_dep_amount')}</div>
      <input class="modal-input" id="vAm" type="number" value="10">
      <div class="modal-subtitle">${I18N.t('gb_dep_wallet_lbl')}</div>
      <input class="modal-input" id="vW" type="text" placeholder="${I18N.t('gb_dep_wallet_ph')}">
      <div class="modal-subtitle">${I18N.t('gb_dep_mname_lbl')}</div>
      <input class="modal-input" id="vMN" type="text" placeholder="${I18N.t('gb_dep_mname_ph')}">
      <div class="modal-subtitle">${I18N.t('gb_dep_mdata_lbl')}</div>
      <input class="modal-input" id="vMD2" type="text" placeholder="${I18N.t('gb_dep_mdata_ph')}">
      <button class="modal-btn-primary" onclick="vSubManual()">${I18N.t('gb_dep_confirm')}</button>
      <button class="modal-btn-secondary" onclick="document.getElementById('modal').remove()">${I18N.t('close')}</button>`;
    return;
  }

  const mHtml = vMethods.map(m => `
    <div class="method-item" onclick="vSel('${m.id}','${(m.method_name||'').replace(/'/g,"\\'")}','${(m.account_data||'').replace(/'/g,"\\'")}')">
      ${_gbIcon(m.icon, '💳', 22)}
      <div class="method-info"><div class="method-name">${m.method_name||''}</div><div class="method-type">${m.method_type||''}</div></div>
      <span class="method-arrow">‹</span>
    </div>`).join('');

  mb.innerHTML = `
    <div class="modal-title">${I18N.t('gb_dep_title')}</div>
    <div class="modal-subtitle">${vCtx.source === 'company' ? (I18N.t('x236') || '🏢 اختر الشركة') + ' — ' + vCtx.company_name : (I18N.t('gb_dep_choose') || 'اختر وسيلة الدفع')}</div>
    <div id="vm">${mHtml}</div>
    <div id="vs2" style="display:none">
      <div class="modal-subtitle" style="margin-top:8px">${I18N.t('gb_dep_method_data')}</div>
      <div class="copy-box" onclick="vCopy()"><code class="copy-data" id="vMD"></code><span class="copy-label" id="vCL">${I18N.t('copy')}</span></div>
      <div class="modal-subtitle">${I18N.t('gb_dep_amount')}</div>
      <input class="modal-input" id="vAm" type="number" value="10">
      <div class="modal-subtitle">${I18N.t('gb_dep_wallet_lbl')}</div>
      <input class="modal-input" id="vW" type="text" placeholder="${I18N.t('gb_dep_wallet_ph')}">
      <div id="vSH" style="display:none;font-size:11px;color:var(--green);margin-bottom:4px"></div>
      <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);margin-bottom:8px;cursor:pointer">
        <input type="checkbox" id="vSv" style="accent-color:var(--gold)"> ${I18N.t('gb_dep_save')}
      </label>
      <button class="modal-btn-primary" onclick="vSub()">${I18N.t('gb_dep_confirm')}</button>
      <button class="modal-btn-secondary" onclick="document.getElementById('vm').style.display='block';document.getElementById('vs2').style.display='none'">${I18N.t('back')}</button>
    </div>
    <button class="modal-btn-secondary" onclick="vChooseBack()">${I18N.t('back')}</button>
    <button class="modal-btn-secondary" onclick="document.getElementById('modal').remove()">${I18N.t('close')}</button>`;
}

function vChooseBack() {
  // رجوع لاختيار المصدر (محفظة/شركة) بدل إغلاق النافذة
  showVexDepositModal(0);
}

let vSelName = '', vSelData = '';
function vSel(id, name, data) {
  vSelected = id; vSelName = name; vSelData = data;
  let sw = '', h = '';
  if (vSaved.length > 0) {
    const m = vSaved.find(w => w.method_name && w.method_name.includes(name));
    if (m) { sw = m.account_number; h = I18N.t('gb_dep_your_wallet') + sw; }
  }
  document.getElementById('vm').style.display = 'none';
  document.getElementById('vs2').style.display = 'block';
  document.getElementById('vMD').textContent = data;
  if (sw) { document.getElementById('vW').value = sw; document.getElementById('vSH').style.display = 'block'; document.getElementById('vSH').textContent = h; }
}

function vCopy() {
  navigator.clipboard.writeText(document.getElementById('vMD').textContent).then(() => {
    if (tg?.HapticFeedback?.impactOccurred) tg.HapticFeedback.impactOccurred('light');
    const lbl = document.getElementById('vCL'); if (lbl) { lbl.textContent = '✓'; setTimeout(() => lbl.textContent = I18N.t('copy'), 1500); }
  });
}

async function vSub() {
  var a = parseFloat(document.getElementById('vAm').value) || 0;
  var w = document.getElementById('vW').value.trim();
  var s = document.getElementById('vSv') ? document.getElementById('vSv').checked : false;
  if (a <= 0) { showToast(I18N.t('gb_dep_enter_amount'), 'error'); return; }
  if (!w) { showToast(I18N.t('gb_dep_enter_wallet'), 'error'); return; }
  if (!vSelected) { showToast(I18N.t('gb_dep_choose_method'), 'error'); return; }
  var btn = document.querySelector('.modal-btn-primary');
  if (btn) { btn.disabled = true; btn.textContent = I18N.t('sending'); }
  try {
    var payload = { amount: a, method_id: vSelected, method_name: vSelName, method_account_data: vSelData, player_wallet: w, save_method: s };
    if (vCtx && vCtx.source === 'company' && vCtx.company_id) {
      payload.company_id = vCtx.company_id;
      payload.company_name = vCtx.company_name;
    }
    var r = await apiFetchCritical(BASE + '/api/deposit/quick', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    if (!r.ok && r.status === 403) {
      showToast(I18N.t('gb_dep_auth_err'), 'error');
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('gb_dep_confirm'); }
      return;
    }
    var d = await r.json();
    if (d.success) {
      document.getElementById('mb').innerHTML = '<div style="text-align:center;padding:20px"><div style="font-size:36px">⏳</div><div class="modal-title">' + I18N.t('gb_dep_sent_title') + '</div><div class="modal-subtitle">' + I18N.t('gb_dep_sent_sub') + '</div><div class="modal-subtitle" style="margin-top:8px;color:var(--green)">' + I18N.t('gb_dep_order_no') + (d.deposit_id || d.trans_id || '') + '</div><button onclick="document.getElementById(\'modal\').remove();loadBalance()" class="modal-btn-secondary" style="margin-top:12px">' + I18N.t('close') + '</button></div>';
      if (tg?.HapticFeedback?.notificationOccurred) tg.HapticFeedback.notificationOccurred('success');
    } else {
      showToast(d.error || I18N.t('gb_dep_failed'), 'error');
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('gb_dep_confirm'); }
    }
  } catch (e) {
    showToast(I18N.t('gb_dep_conn_err'), 'error');
    if (btn) { btn.disabled = false; btn.textContent = I18N.t('gb_dep_confirm'); }
  }
}

// Manual deposit submit (when no methods from API)
async function vSubManual() {
  var a = parseFloat(document.getElementById('vAm').value) || 0;
  var w = document.getElementById('vW').value.trim();
  var mn = document.getElementById('vMN') ? document.getElementById('vMN').value.trim() : '';
  var md = document.getElementById('vMD2') ? document.getElementById('vMD2').value.trim()
          : (document.getElementById('vMD') ? document.getElementById('vMD').value.trim() : '');
  if (a <= 0) { showToast(I18N.t('gb_dep_enter_amount'), 'error'); return; }
  if (!w) { showToast(I18N.t('gb_dep_enter_wallet'), 'error'); return; }
  if (!mn) { showToast(I18N.t('gb_dep_enter_mname'), 'error'); return; }
  var btn = document.querySelector('.modal-btn-primary');
  if (btn) { btn.disabled = true; btn.textContent = I18N.t('sending'); }
  try {
    var r = await apiFetchCritical(BASE + '/api/deposit/quick', {
      method: 'POST',
      body: JSON.stringify({ amount: a, method_id: 'manual', method_name: mn, method_account_data: md, player_wallet: w, save_method: false })
    });
    if (!r.ok && r.status === 403) {
      showToast(I18N.t('gb_dep_auth_err'), 'error');
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('gb_dep_confirm'); }
      return;
    }
    var d = await r.json();
    if (d.success) {
      document.getElementById('mb').innerHTML = '<div style="text-align:center;padding:20px"><div style="font-size:36px">⏳</div><div class="modal-title">' + I18N.t('gb_dep_sent_title') + '</div><div class="modal-subtitle">' + I18N.t('gb_dep_sent_sub') + '</div><div class="modal-subtitle" style="margin-top:8px;color:var(--green)">' + I18N.t('gb_dep_order_no') + (d.deposit_id || d.trans_id || '') + '</div><button onclick="document.getElementById(\'modal\').remove();loadBalance()" class="modal-btn-secondary" style="margin-top:12px">' + I18N.t('close') + '</button></div>';
      if (tg?.HapticFeedback?.notificationOccurred) tg.HapticFeedback.notificationOccurred('success');
    } else {
      showToast(d.error || I18N.t('gb_dep_failed'), 'error');
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('gb_dep_confirm'); }
    }
  } catch (e) {
    showToast(I18N.t('gb_dep_conn_err'), 'error');
    if (btn) { btn.disabled = false; btn.textContent = I18N.t('gb_dep_confirm'); }
  }
}

// ===== Phase 2: Shared Game Framework Additions =====

// ---- Deposit Button Injection ----
// Auto-injects a 💰 button into .topbar-right if not already present
function injectDepositButton() {
  var tr = document.querySelector('.topbar-right');
  if (!tr || document.getElementById('depBtnTop')) return;
  var btn = document.createElement('button');
  btn.id = 'depBtnTop';
  btn.className = 'btn-deposit-top';
  btn.innerHTML = '💰';
  btn.title = I18N.t('gb_dep_btn_title');
  btn.onclick = function() { showVexDepositModal(0); };
  tr.insertBefore(btn, tr.firstChild);
}

// ---- Balance Check Before Bet ----
// Returns true if balance >= requiredAmount, otherwise shows deposit modal and returns false
// Async version — fetches balance from server (more reliable than reading DOM)
async function checkBalanceBeforeBet(requiredAmount) {
  // First try reading from DOM (fast path — already loaded)
  var balEl = document.getElementById('bal');
  var currentBal = balEl ? parseFloat(balEl.textContent.replace(/,/g, '')) || 0 : 0;
  // If DOM shows 0, fetch from server (balance might not have loaded yet)
  if (currentBal === 0) {
    try {
      var r = await apiFetch(BASE + '/api/wallet/balance');
      var d = await r.json();
      if (d.balance !== undefined) {
        currentBal = parseFloat(d.balance) || 0;
        if (balEl) balEl.textContent = currentBal.toLocaleString();
        var curEl = document.getElementById('cur');
        if (curEl && d.currency) curEl.textContent = d.currency;
      }
    } catch(e) { /* network error — proceed with 0 */ }
  }
  if (currentBal < requiredAmount) {
    showVexDepositModal(requiredAmount);
    return false;
  }
  return true;
}

// ---- Auto Deposit Check ----
// On page load, fetches balance and shows deposit modal if below minimum
async function autoDepositCheck(minAmount) {
  try {
    var r = await apiFetch(BASE + '/api/wallet/balance');
    var d = await r.json();
    if (d.balance !== undefined) {
      var balEl = document.getElementById('bal');
      if (balEl) balEl.textContent = (d.balance || 0).toLocaleString();
      var curEl = document.getElementById('cur');
      if (curEl && d.currency) curEl.textContent = d.currency;
      if ((d.balance || 0) < (minAmount || 10)) {
        setTimeout(function() { showVexDepositModal(minAmount || 10); }, 1500);
      }
    }
  } catch(e) {}
}

// Auto-init deposit button when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function() { setTimeout(injectDepositButton, 50); });
} else {
  setTimeout(injectDepositButton, 50);
}