// ===== VEX Games — Shared Base JavaScript =====
// Core game engine, API, sound, deposit, live players, config

// ---- Telegram WebApp Init ----
const tg = window.Telegram?.WebApp;
if (tg) { tg.expand(); tg.ready(); }

// ---- Config ----
const uid = new URLSearchParams(location.search).get('uid') || '';
const BASE = location.origin;
const initData = tg?.initData || '';
let soundOn = true;
let streakWin = 0;
let gameCurrency = 'EGP';

// ---- API Client ----
async function apiFetch(url, opts = {}) {
  opts.headers = opts.headers || {};
  opts.headers['X-Telegram-Init-Data'] = initData;
  if (opts.body && typeof opts.body === 'string') {
    opts.headers['Content-Type'] = 'application/json';
  }
  if (uid && !url.includes('uid=')) {
    url += (url.includes('?') ? '&' : '?') + 'uid=' + uid;
  }
  return fetch(url, opts);
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

// ---- Haptics ----
function haptic(t = 'light') {
  if (tg?.HapticFeedback?.impactOccurred) {
    try { tg.HapticFeedback.impactOccurred(t); } catch (e) { /* ignore */ }
  }
}

// ---- Balance ----
async function loadBalance() {
  try {
    const r = await apiFetch(`${BASE}/api/wallet/balance?uid=${uid}`);
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
      <div class="lp-user"><div class="lp-avatar">${avatar}</div><span>${p.name || '???'}${p.isMe ? ' (أنت)' : ''}</span></div>
      <div style="display:flex;align-items:center;gap:6px"><span style="font-weight:700">${p.bet || 0}</span>${mult}</div>`;
    listEl.appendChild(row);
  });
}

function simulatePlayers() {
  const names = ['أحمد', 'عمر', 'محمد', 'خالد', 'سعد', 'فهد', 'ناصر', 'يوسف', 'علي', 'حسن', 'ماجد', 'وليد', 'طارق', 'بدر', 'راشد'];
  if (Math.random() < 0.6 && livePlayers.length < 18) {
    addPlayer({
      uid: 'b' + Math.random().toString(36).substr(2, 5),
      name: names[Math.floor(Math.random() * names.length)],
      bet: [10, 20, 50, 100, 200, 500][Math.floor(Math.random() * 6)],
      status: Math.random() < 0.4 ? 'win' : 'lose',
      multiplier: Math.random() < 0.4 ? 1 + Math.random() * 4 : 0,
      isMe: false
    });
  }
  renderPlayers();
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

// ---- Deposit URL ----
function goBack() {
  window.location.href = `${BASE}/webapp/games?uid=${uid}&lang=ar`;
}

// ---- VEX Deposit Modal (shared) ----
let vMethods = [], vSaved = [], vSelected = null;

async function showVexDepositModal(required) {
  const overlay = document.createElement('div');
  overlay.id = 'modal';
  overlay.className = 'modal-overlay';
  overlay.style.display = 'flex';
  overlay.innerHTML = '<div class="modal-box" id="mb"></div>';
  document.body.appendChild(overlay);
  const mb = document.getElementById('mb');

  try {
    const r = await apiFetch(`${BASE}/api/games/payment-methods?uid=${uid}`);
    const d = await r.json();
    vMethods = d.methods || [];
    vSaved = d.saved_methods || [];
  } catch (e) { /* ignore */ }

  if (vMethods.length === 0) {
    mb.innerHTML = `<div style="text-align:center;padding:16px"><div style="font-size:28px">😢</div><div class="modal-title">لا توجد وسائل دفع</div><button onclick="document.getElementById('modal').remove()" class="modal-btn-secondary">إغلاق</button></div>`;
    return;
  }

  const mHtml = vMethods.map(m => `
    <div class="method-item" onclick="vSel('${m.id}','${(m.method_name||'').replace(/'/g,"\\'")}','${(m.account_data||'').replace(/'/g,"\\'")}')">
      <span class="method-icon">${m.icon||'💳'}</span>
      <div class="method-info"><div class="method-name">${m.method_name||''}</div><div class="method-type">${m.method_type||''}</div></div>
      <span class="method-arrow">‹</span>
    </div>`).join('');

  mb.innerHTML = `
    <div class="modal-title">💰 إيداع محفظة VEX</div>
    <div class="modal-subtitle">${required ? `تحتاج ${required}` : 'اختر وسيلة الدفع'}</div>
    <div id="vm">${mHtml}</div>
    <div id="vs2" style="display:none">
      <div class="modal-subtitle" style="margin-top:8px">📋 بيانات الوسيلة:</div>
      <div class="copy-box" onclick="vCopy()"><code class="copy-data" id="vMD"></code><span class="copy-label" id="vCL">📋 نسخ</span></div>
      <div class="modal-subtitle">💵 المبلغ:</div>
      <input class="modal-input" id="vAm" type="number" value="${required||10}">
      <div class="modal-subtitle">🔐 رقم محفظتك:</div>
      <input class="modal-input" id="vW" type="text" placeholder="رقم محفظتك">
      <div id="vSH" style="display:none;font-size:11px;color:var(--green);margin-bottom:4px"></div>
      <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);margin-bottom:8px;cursor:pointer">
        <input type="checkbox" id="vSv" style="accent-color:var(--gold)"> حفظ دائم
      </label>
      <button class="modal-btn-primary" onclick="vSub()">✅ تأكيد الإيداع</button>
      <button class="modal-btn-secondary" onclick="document.getElementById('vm').style.display='block';document.getElementById('vs2').style.display='none'">‹ رجوع</button>
    </div>
    <button class="modal-btn-secondary" onclick="document.getElementById('modal').remove()">إغلاق</button>`;
}

let vSelName = '', vSelData = '';
function vSel(id, name, data) {
  vSelected = id; vSelName = name; vSelData = data;
  let sw = '', h = '';
  if (vSaved.length > 0) {
    const m = vSaved.find(w => w.method_name && w.method_name.includes(name));
    if (m) { sw = m.account_number; h = '✓ محفظتك: ' + sw; }
  }
  document.getElementById('vm').style.display = 'none';
  document.getElementById('vs2').style.display = 'block';
  document.getElementById('vMD').textContent = data;
  if (sw) { document.getElementById('vW').value = sw; document.getElementById('vSH').style.display = 'block'; document.getElementById('vSH').textContent = h; }
}

function vCopy() {
  navigator.clipboard.writeText(document.getElementById('vMD').textContent).then(() => {
    if (tg?.HapticFeedback?.impactOccurred) tg.HapticFeedback.impactOccurred('light');
    const lbl = document.getElementById('vCL'); if (lbl) { lbl.textContent = '✓'; setTimeout(() => lbl.textContent = '📋 نسخ', 1500); }
  });
}

async function vSub() {
  const a = parseFloat(document.getElementById('vAm').value) || 0;
  const w = document.getElementById('vW').value.trim();
  const s = document.getElementById('vSv').checked;
  if (a <= 0) { alert('أدخل المبلغ'); return; }
  if (!w) { alert('أدخل رقم محفظتك'); return; }
  if (!vSelected) { alert('اختر وسيلة'); return; }
  try {
    const r = await apiFetch(`${BASE}/api/deposit/quick`, {
      method: 'POST',
      body: JSON.stringify({ uid, amount: a, method_id: vSelected, method_name: vSelName, method_account_data: vSelData, player_wallet: w, save_method: s })
    });
    const d = await r.json();
    if (d.success) {
      document.getElementById('mb').innerHTML = `<div style="text-align:center;padding:16px"><div style="font-size:28px">⏳</div><div class="modal-title">تم الإيداع</div><div class="modal-subtitle">بانتظار موافقة الإدارة</div><button onclick="document.getElementById('modal').remove();loadBalance()" class="modal-btn-secondary">إغلاق</button></div>`;
    } else { alert(d.error || 'خطأ'); }
  } catch (e) { alert('خطأ'); }
}