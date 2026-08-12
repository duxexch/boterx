/**
 * VEX Games FX — Particle system, confetti, sounds, win animations
 * No external dependencies — pure Web APIs only
 */

(function (window) {
  'use strict';

  // ── Web Audio context (created on first user gesture to avoid autoplay block) ──
  let _audioCtx = null;
  function _getAudio() {
    if (!_audioCtx) {
      try { _audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }
      catch(e) { return null; }
    }
    if (_audioCtx.state === 'suspended') _audioCtx.resume();
    return _audioCtx;
  }

  // Unlock audio on first touch (iOS requirement)
  document.addEventListener('touchstart', _getAudio, { once: true });
  document.addEventListener('click',      _getAudio, { once: true });

  // ── Sound generator — pure tones, no audio files required ────────────────
  const Sounds = {
    _play(frequency, type, duration, volume, attack, decay) {
      const ctx = _getAudio();
      if (!ctx) return;
      try {
        const osc  = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(frequency, ctx.currentTime);
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(volume || 0.3, ctx.currentTime + (attack || 0.01));
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + (duration || 0.3));
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + (duration || 0.3) + (decay || 0.05));
      } catch(e) {}
    },

    betPlaced()  { this._play(440, 'sine', 0.15, 0.2); },
    win()        {
      this._play(523, 'sine', 0.1, 0.3);
      setTimeout(() => this._play(659, 'sine', 0.1, 0.3), 120);
      setTimeout(() => this._play(784, 'sine', 0.25, 0.4), 240);
    },
    bigWin() {
      [523,659,784,1047].forEach((f,i) =>
        setTimeout(() => this._play(f,'sine',0.2,0.45), i*100));
    },
    loss()       { this._play(200, 'sawtooth', 0.25, 0.2); },
    spin()       { this._play(330, 'triangle', 0.08, 0.15); },
    coin()       { this._play(880, 'square', 0.05, 0.15, 0.005, 0.02); },
    jackpot() {
      [261,329,392,523,659,784,1047].forEach((f,i) =>
        setTimeout(() => this._play(f,'sine',0.3,0.5), i*80));
    },
    click()      { this._play(600, 'sine', 0.06, 0.1); },
    error()      { this._play(180, 'sawtooth', 0.2, 0.25); },
    deposit()    {
      this._play(660, 'sine', 0.1, 0.3);
      setTimeout(() => this._play(880, 'sine', 0.2, 0.4), 100);
    },
    withdraw()   {
      this._play(440, 'sine', 0.15, 0.3);
      setTimeout(() => this._play(330, 'sine', 0.15, 0.25), 120);
    },
  };

  // ── Coin particle burst ────────────────────────────────────────────────────
  function spawnCoins(x, y, count, direction) {
    count = count || 12;
    const emojis = ['💰','🪙','💵','💴','💶'];
    for (let i = 0; i < count; i++) {
      const el = document.createElement('span');
      el.className = 'coin-particle' + (direction === 'down' ? ' downward' : '');
      el.textContent = emojis[i % emojis.length];

      const angle  = (direction === 'down')
        ? (Math.PI * 0.3 + Math.random() * Math.PI * 0.4)
        : (-(Math.PI * 0.2 + Math.random() * Math.PI * 0.6));
      const speed  = 60 + Math.random() * 120;
      const dx     = Math.cos(angle) * speed * (Math.random() > 0.5 ? 1 : -1);
      const dyMid  = Math.sin(angle) * speed * 0.5;
      const dyEnd  = dyMid * 2.5;

      el.style.cssText = [
        `left:${x}px`, `top:${y}px`,
        `--dx:${dx}px`, `--dy-mid:${dyMid}px`, `--dy-end:${dyEnd}px`,
      ].join(';');

      document.body.appendChild(el);
      setTimeout(() => el.remove(), 1400);
      Sounds.coin();
    }
  }

  // ── Confetti burst ─────────────────────────────────────────────────────────
  const CONFETTI_COLORS = ['#F5C518','#22c55e','#3b82f6','#a855f7','#ef4444','#f97316','#06b6d4'];

  function spawnConfetti(x, y, count, spread) {
    count  = count  || 40;
    spread = spread || 200;
    for (let i = 0; i < count; i++) {
      const el = document.createElement('div');
      el.className = 'confetti-piece';
      el.style.background = CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)];
      el.style.left = x + 'px';
      el.style.top  = y + 'px';

      const dur = 1.2 + Math.random() * 0.8;
      const r   = () => (Math.random() - 0.5) * spread * 2;
      const d   = () => -Math.random() * spread * 1.5;
      el.style.setProperty('--dur',  dur + 's');
      el.style.setProperty('--dx1',  r() + 'px');
      el.style.setProperty('--dy1',  d() * 0.3 + 'px');
      el.style.setProperty('--dx2',  r() + 'px');
      el.style.setProperty('--dy2',  d() * 0.6 + 'px');
      el.style.setProperty('--dx3',  r() + 'px');
      el.style.setProperty('--dy3',  d() * 0.9 + 'px');
      el.style.setProperty('--dx4',  r() + 'px');
      el.style.setProperty('--dy4',  d() + 'px');
      el.style.setProperty('--br',   Math.random() > 0.5 ? '50%' : '2px');
      el.style.width  = (6 + Math.random() * 8) + 'px';
      el.style.height = (6 + Math.random() * 8) + 'px';

      document.body.appendChild(el);
      setTimeout(() => el.remove(), (dur + 0.1) * 1000);
    }
  }

  // Full-screen confetti (used for big wins)
  function confettiBurst(count) {
    const w = window.innerWidth, h = window.innerHeight;
    spawnConfetti(w * 0.3, h * 0.4, Math.floor((count || 60) / 2), 250);
    spawnConfetti(w * 0.7, h * 0.4, Math.floor((count || 60) / 2), 250);
  }

  // ── Win flash on an element ────────────────────────────────────────────────
  function winFlash(el) {
    if (!el) return;
    el.classList.remove('win-flash');
    void el.offsetWidth; // reflow to restart animation
    el.classList.add('win-flash');
    el.addEventListener('animationend', () => el.classList.remove('win-flash'), { once: true });
  }

  function lossFlash(el) {
    if (!el) return;
    el.classList.remove('loss-flash');
    void el.offsetWidth;
    el.classList.add('loss-flash');
    el.addEventListener('animationend', () => el.classList.remove('loss-flash'), { once: true });
  }

  // ── Jackpot overlay ────────────────────────────────────────────────────────
  function showJackpot(amount, currency, onClose) {
    let overlay = document.getElementById('jackpot-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'jackpot-overlay';
      overlay.innerHTML = `
        <div class="jackpot-trophy">🏆</div>
        <div class="jackpot-amount" id="jackpot-amount-val"></div>
        <div class="jackpot-label">🎊 جاك بوت! 🎊</div>
        <button id="jackpot-close"
          style="margin-top:32px;padding:12px 32px;border:none;border-radius:999px;
                 background:var(--gold);color:#000;font-weight:700;font-size:1rem;cursor:pointer;">
          رائع! 🎉
        </button>`;
      document.body.appendChild(overlay);
      document.getElementById('jackpot-close').addEventListener('click', () => {
        overlay.classList.add('hiding');
        setTimeout(() => { overlay.remove(); if (onClose) onClose(); }, 500);
      });
    }
    document.getElementById('jackpot-amount-val').textContent =
      (amount || '') + (currency ? ' ' + currency : '');
    Sounds.jackpot();
    confettiBurst(80);
    // Auto-close after 8 s
    setTimeout(() => {
      if (document.getElementById('jackpot-overlay')) {
        overlay.classList.add('hiding');
        setTimeout(() => { overlay.remove(); if (onClose) onClose(); }, 500);
      }
    }, 8000);
  }

  // ── Deposit / Withdraw button FX ───────────────────────────────────────────
  function triggerDepositFX(btnEl) {
    if (!btnEl) return;
    const rect = btnEl.getBoundingClientRect();
    const cx = rect.left + rect.width  / 2;
    const cy = rect.top  + rect.height / 2;
    spawnCoins(cx, cy, 10, 'up');
    Sounds.deposit();
    btnEl.classList.add('active');
    setTimeout(() => btnEl.classList.remove('active'), 600);
  }

  function triggerWithdrawFX(btnEl) {
    if (!btnEl) return;
    const rect = btnEl.getBoundingClientRect();
    const cx = rect.left + rect.width  / 2;
    const cy = rect.top  + rect.height / 2;
    spawnCoins(cx, cy, 10, 'down');
    Sounds.withdraw();
  }

  // ── Win result helper (use in game result callbacks) ──────────────────────
  function onWin(amount, currency, options) {
    options = options || {};
    const isJackpot = options.jackpot || (amount && amount > 1000);
    if (isJackpot) {
      showJackpot(amount, currency, options.onClose);
    } else {
      const w = window.innerWidth, h = window.innerHeight;
      spawnConfetti(w / 2, h / 3, 40, 180);
      spawnCoins(w / 2, h / 2, 8, 'up');
      Sounds.bigWin();
    }
    if (options.el) winFlash(options.el);
  }

  function onLoss(options) {
    options = options || {};
    if (options.el) lossFlash(options.el);
    Sounds.loss();
  }

  // ── Animated number counter ────────────────────────────────────────────────
  function animateNumber(el, from, to, duration, decimals, suffix) {
    if (!el) return;
    const start = performance.now();
    duration = duration || 800;
    decimals = decimals === undefined ? 2 : decimals;
    suffix   = suffix || '';
    function tick(now) {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3); // cubic ease-out
      const val  = from + (to - from) * ease;
      el.textContent = val.toFixed(decimals) + suffix;
      el.classList.add('roll-up');
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ── Auto-wire btn-deposit / btn-withdraw ──────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.btn-deposit').forEach(btn => {
      btn.addEventListener('click', () => triggerDepositFX(btn));
    });
    document.querySelectorAll('.btn-withdraw').forEach(btn => {
      btn.addEventListener('click', () => triggerWithdrawFX(btn));
    });
    document.querySelectorAll('.btn-fx').forEach(btn => {
      btn.addEventListener('click', () => Sounds.click());
    });
  });

  // ── Public API ─────────────────────────────────────────────────────────────
  window.VexFX = {
    Sounds,
    spawnCoins,
    spawnConfetti,
    confettiBurst,
    winFlash,
    lossFlash,
    showJackpot,
    triggerDepositFX,
    triggerWithdrawFX,
    onWin,
    onLoss,
    animateNumber,
  };

})(window);
