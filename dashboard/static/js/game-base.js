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
      showToast('Outbox: ' + remaining.length + ' pending', 'info');
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
  if (uid && !url.includes('uid=')) {
    url += (url.includes('?') ? '&' : '?') + 'uid=' + uid;
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

// ---- Chat / Emoji Reactions ----
let _chatSSE = null;
const QUICK_EMOJIS = ['🔥', '💎', '🚀', '💰', '😱', '😂', '💪', '🎉'];

function connectChatStream() {
  const container = document.querySelector('.chat-messages');
  if (!container) return;
  try {
    const url = BASE + '/api/games/chat/stream?uid=' + uid;
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
    const r = await apiFetch(BASE + '/api/games/chat/history?uid=' + uid);
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
      body: JSON.stringify({ uid, message: msg })
    });
  } catch(e) { /* ignore */ }
}

async function sendEmoji(emoji) {
  try {
    await apiFetch(BASE + '/api/games/chat/send', {
      method: 'POST',
      body: JSON.stringify({ uid, emoji: emoji })
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
function injectChatBar() {
  const app = document.getElementById('app');
  if (!app || document.querySelector('.chat-bar')) return;
  const bar = document.createElement('div');
  bar.className = 'chat-bar';
  bar.innerHTML = `
    <div class="chat-header">
      <span>💬 الدردشة</span>
      <button class="chat-toggle" onclick="toggleChat()">‒</button>
    </div>
    <div class="chat-messages"></div>
    <div class="chat-input-row">
      <button class="chat-emoji-btn" onclick="sendEmoji('🔥')">🔥</button>
      <button class="chat-emoji-btn" onclick="sendEmoji('💎')">💎</button>
      <button class="chat-emoji-btn" onclick="sendEmoji('🚀')">🚀</button>
      <input class="chat-input" placeholder="اكتب رسالة..." onkeypress="if(event.key==='Enter')sendChatMessage()">
      <button class="chat-send-btn" onclick="sendChatMessage()">➤</button>
    </div>
  `;
  app.appendChild(bar);
  connectChatStream();
}

// Auto-inject chat on DOM ready (after PF badge)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { setTimeout(injectChatBar, 100); });
} else {
  setTimeout(injectChatBar, 100);
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
      <div class="lp-user"><div class="lp-avatar">${avatar}</div><span>${p.name || '???'}${p.isMe ? ' (أنت)' : ''}</span></div>
      <div style="display:flex;align-items:center;gap:6px"><span style="font-weight:700">${p.bet || 0}</span>${mult}</div>`;
    listEl.appendChild(row);
  });
}

// Connect to real SSE live players stream
function connectLivePlayersStream() {
  try {
    if (_lpSSE) _lpSSE.close();
    const url = BASE + '/api/games/live-players/stream?uid=' + uid;
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
    const r = await apiFetch(BASE + '/api/games/live-players?uid=' + uid);
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
function simulatePlayers() {
  // Try SSE first, fallback to simulation
  if (!_lpSSE && !_lpSSEFallback) {
    connectLivePlayersStream();
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
    const url = BASE + '/api/games/leaderboard/stream?uid=' + uid;
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
      apiFetch(BASE + '/api/games/leaderboard?uid=' + uid).then(r => r.json()).then(d => {
        if (d.leaderboard) renderLeaderboard(containerId, d.leaderboard);
      }).catch(() => {});
    };
  } catch(e) {
    apiFetch(BASE + '/api/games/leaderboard?uid=' + uid).then(r => r.json()).then(d => {
      if (d.leaderboard) renderLeaderboard(containerId, d.leaderboard);
    }).catch(() => {});
  }
}

function renderLeaderboard(containerId, players) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!players || players.length === 0) {
    el.innerHTML = '<div style="text-align:center;color:var(--muted);padding:16px;font-size:12px">لا يوجد لاعبون بعد</div>';
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
      <span class="lb-name">${p.name || '???'}${p.uid === uid ? ' (أنت)' : ''}</span>
      <span class="lb-profit">${profitStr}</span>
      <span class="lb-games">${p.games || 0} لعبة</span>
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
    const r = await apiFetch(`${BASE}/api/provably-fair/seed?uid=${uid}`);
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
  const seedShort = pfRevealedSeed ? pfRevealedSeed.substring(0, 32) + '...' : 'مخفي (سيكشف بعد الجولة)';

  box.innerHTML = `
    <div class="modal-title">🔐 Provably Fair</div>
    <div class="modal-subtitle">نظام عدالة قابل للتحقق</div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">🔐 Server Seed Hash:</div>
      <code style="font-size:11px;color:var(--gold);word-break:break-all">${hashShort}</code>
    </div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">🔑 Client Seed:</div>
      <code style="font-size:12px;color:var(--cyan)">${pfClientSeed || '---'}</code>
    </div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">🎲 Nonce (rolls):</div>
      <code style="font-size:14px;color:var(--green)">${pfNonce}</code>
    </div>
    <div style="background:var(--surface-2);border-radius:8px;padding:10px;margin:6px 0">
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">🔓 Server Seed (revealed):</div>
      <code style="font-size:11px;color:${pfRevealedSeed ? 'var(--green)' : 'var(--muted)'};word-break:break-all">${seedShort}</code>
    </div>
    ${pfRevealedSeed ? `
    <div style="background:rgba(0,231,1,0.08);border:1px solid rgba(0,231,1,0.3);border-radius:8px;padding:8px;margin:6px 0;text-align:center">
      <div style="font-size:11px;color:var(--green)">✅ يمكنك التحقق من النتيجة</div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px">SHA256(server_seed) = seed_hash</div>
    </div>
    <button class="modal-btn-primary" onclick="verifyPF()">🔍 تحقق</button>
    ` : `
    <div style="font-size:11px;color:var(--muted);text-align:center;padding:8px">
      سيتم كشف server seed بعد انتهاء الجولة للتحقق
    </div>
    `}
    <div style="font-size:10px;color:var(--muted);text-align:center;margin-top:8px;line-height:1.5">
      🔐 يتم استخدام HMAC-SHA256 لتوليد نتائج عادلة<br>
      لا يمكن للخادم التلاعب بالنتيجة بعد إرسال seed hash
    </div>
    <button class="modal-btn-secondary" onclick="document.getElementById('pfModal').remove()">إغلاق</button>
  `;
}

async function verifyPF() {
  if (!pfRevealedSeed) {
    showToast('لا يوجد seed مكشوف للتحقق', 'error');
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
        <div class="modal-title">✅ تم التحقق</div>
        <div style="background:rgba(0,231,1,0.08);border:1px solid rgba(0,231,1,0.3);border-radius:8px;padding:12px;margin:8px 0;text-align:center">
          <div style="font-size:28px">✅</div>
          <div style="font-size:13px;color:var(--green);font-weight:700">النتيجة صحيحة!</div>
          <div style="font-size:11px;color:var(--muted);margin-top:4px">SHA256 matched ✓</div>
          <div style="font-size:11px;color:var(--muted)">Results: ${d.results.join(', ')}</div>
        </div>
        <button class="modal-btn-secondary" onclick="document.getElementById('pfModal').remove()">إغلاق</button>
      `;
      soundWin();
    } else {
      showToast('فشل التحقق!', 'error');
    }
  } catch (e) {
    showToast('خطأ في التحقق', 'error');
  }
}

async function revealPFSession() {
  if (!pfSessionId) return;
  try {
    const r = await apiFetch(`${BASE}/api/provably-fair/reveal/${pfSessionId}?uid=${uid}`);
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
      '<div style="font-size:14px;font-weight:700;margin-bottom:12px">\u0627\u0644\u0639\u0628\u0629 \u0642\u064A\u0627\u0645<br>\u0633\u062A\u062E\u0633\u0631 \u0631\u0647\u0627\u0646\u0643 \u0625\u0630\u0627 \u062E\u0631\u062C\u062A</div>' +
      '<div style="display:flex;gap:8px">' +
      '<button id="_stayBtn" style="flex:1;padding:10px;border-radius:8px;border:none;background:var(--green-dim);color:#fff;font-weight:700">\u0628\u0642\u0627\u0621</button>' +
      '<button id="_leaveBtn" style="flex:1;padding:10px;border-radius:8px;border:none;background:var(--red-dim);color:#fff;font-weight:700">\u062E\u0631\u0648\u062C</button>' +
      '</div>';
    c.appendChild(box);
    document.body.appendChild(c);
    document.getElementById('_stayBtn').onclick = function() { c.remove(); };
    document.getElementById('_leaveBtn').onclick = function() { c.remove(); window.location.href = BASE + '/webapp/games?uid=' + uid + '&lang=ar'; };
    return;
  }
  window.location.href = BASE + '/webapp/games?uid=' + uid + '&lang=ar';
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
  btn.title = 'إيداع';
  btn.onclick = function() { showVexDepositModal(0); };
  tr.insertBefore(btn, tr.firstChild);
}

// ---- Balance Check Before Bet ----
// Returns true if balance >= requiredAmount, otherwise shows deposit modal and returns false
function checkBalanceBeforeBet(requiredAmount) {
  var balEl = document.getElementById('bal');
  var currentBal = balEl ? parseFloat(balEl.textContent.replace(/,/g, '')) || 0 : 0;
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
    var r = await apiFetch(BASE + '/api/wallet/balance?uid=' + uid);
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