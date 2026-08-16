/* VEX auth gate — blocks unregistered visitors: first click opens @vex_otp_bot,
   then a code-entry card stays until a valid 6-digit code is entered. */
(function () {
  'use strict';
  var BOT_URL = 'https://t.me/vex_otp_bot?start=web_auth';

  // Inside Telegram WebApp with initData → already authenticated by the app itself.
  try {
    if (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) return;
  } catch (e) {}

  function t(k, ar, en) {
    try {
      if (window.I18N && I18N.lang && I18N.lang() === 'en') return en;
    } catch (e) {}
    try {
      if ((localStorage.getItem('vex_lang') || 'ar') === 'en') return en;
    } catch (e) {}
    return ar;
  }

  var gated = false, overlayShown = false, botOpened = false;
  var authState = 'unknown', pendingClick = false;

  function buildOverlay() {
    if (document.getElementById('vexAuthGate')) return;
    var ov = document.createElement('div');
    ov.id = 'vexAuthGate';
    ov.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(5,8,11,.92);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;padding:20px';
    ov.innerHTML =
      '<div style="background:#141920;border:1px solid #262e39;border-radius:18px;max-width:340px;width:100%;padding:26px 22px;text-align:center;font-family:Cairo,Tahoma,sans-serif;color:#eef2f6">' +
      '<img src="/static/icons/logo-full.png" alt="VEX" style="height:46px;margin-bottom:14px" onerror="this.style.display=\'none\'">' +
      '<div style="font-size:17px;font-weight:900;margin-bottom:6px">' + t('gate_title', '🔐 تسجيل الدخول مطلوب', '🔐 Login required') + '</div>' +
      '<div style="font-size:12.5px;color:#8794a3;line-height:1.7;margin-bottom:14px">' +
      t('gate_desc', 'افتح البوت وشارك رقمك لتستلم رمز دخول من 6 أرقام، ثم ارجع هنا وأدخله.', 'Open the bot and share your number to receive a 6-digit login code, then come back and enter it.') + '</div>' +
      '<a id="vexGateBot" href="' + BOT_URL + '" target="_blank" rel="noopener" style="display:block;background:linear-gradient(135deg,#00e701,#00c101);color:#04210a;font-weight:900;font-size:14px;border-radius:12px;padding:12px;text-decoration:none;margin-bottom:14px">📲 ' + t('gate_open_bot', 'فتح البوت @vex_otp_bot', 'Open bot @vex_otp_bot') + '</a>' +
      '<input id="vexGateCode" inputmode="numeric" maxlength="6" placeholder="——————" autocomplete="one-time-code" style="width:100%;box-sizing:border-box;background:#0b0e11;border:1px solid #262e39;border-radius:12px;color:#eef2f6;font-size:22px;font-weight:900;letter-spacing:8px;text-align:center;padding:10px;direction:ltr;outline:none;margin-bottom:10px">' +
      '<button id="vexGateGo" style="width:100%;background:transparent;border:1px solid #00e701;color:#00e701;font-weight:900;font-size:14px;border-radius:12px;padding:11px;cursor:pointer;font-family:inherit">' + t('gate_verify', '✅ تحقق من الرمز', '✅ Verify code') + '</button>' +
      '<div id="vexGateMsg" style="font-size:12px;min-height:18px;margin-top:10px;color:#ff4757"></div>' +
      '</div>';
    document.body.appendChild(ov);

    var inp = document.getElementById('vexGateCode'),
        btn = document.getElementById('vexGateGo'),
        msg = document.getElementById('vexGateMsg');

    var botA = document.getElementById('vexGateBot');
    if (botA) botA.addEventListener('click', function () {
      try { localStorage.setItem('vex_gate_pending', '1'); } catch (e) {}
    });

    inp.addEventListener('input', function () {
      this.value = this.value.replace(/\D/g, '').slice(0, 6);
      msg.textContent = '';
    });
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') btn.click(); });

    btn.addEventListener('click', function () {
      var code = inp.value.trim();
      if (code.length !== 6) {
        msg.textContent = t('gate_need6', 'أدخل رمزاً من 6 أرقام', 'Enter a 6-digit code');
        return;
      }
      btn.disabled = true;
      msg.style.color = '#8794a3';
      msg.textContent = t('gate_checking', '⏳ جارٍ التحقق...', '⏳ Verifying...');
      fetch('/api/web/auth-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ code: code })
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (res.ok && res.d && res.d.success) {
            msg.style.color = '#00e701';
            msg.textContent = t('gate_ok', '✅ تم الدخول — جارٍ التحديث...', '✅ Logged in — refreshing...');
            try { localStorage.removeItem('vex_gate_pending'); } catch (e2) {}
            setTimeout(function () { location.reload(); }, 600);
          } else {
            btn.disabled = false;
            inp.value = '';
            msg.style.color = '#ff4757';
            msg.textContent = (res.d && res.d.error) || t('gate_bad', 'رمز غير صالح — أعد العملية من البوت', 'Invalid code — restart from the bot');
          }
        })
        .catch(function () {
          btn.disabled = false;
          msg.style.color = '#ff4757';
          msg.textContent = t('gate_err', 'خطأ في الاتصال — حاول مجدداً', 'Connection error — try again');
        });
    });
  }

  function showOverlay() {
    if (!overlayShown) {
      overlayShown = true;
      buildOverlay();
    }
    var ov = document.getElementById('vexAuthGate');
    if (ov) ov.style.display = 'flex';
  }

  function openBotLink() {
    try { localStorage.setItem('vex_gate_pending', '1'); } catch (e) {}
    // tg:// deep link opens the chat with the START button directly (not the profile page).
    // Fall back to the https link if the Telegram app didn't take over.
    var opened = false;
    try {
      var a = document.createElement('a');
      a.href = 'tg://resolve?domain=vex_otp_bot&start=web_auth';
      document.body.appendChild(a); a.click(); a.remove();
      opened = true;
    } catch (e) {}
    setTimeout(function () {
      // If the app grabbed the link the page is hidden; otherwise use the web link.
      if (!opened || document.visibilityState === 'visible') {
        var b = document.createElement('a');
        b.href = BOT_URL; b.target = '_blank'; b.rel = 'noopener';
        document.body.appendChild(b); b.click(); b.remove();
      }
    }, 700);
  }

  window.VEXGate = {
    open: function () { showOverlay(); openBotLink(); }
  };

  function interceptClicks() {
    document.addEventListener('click', function (e) {
      if (!gated) return;
      var ov = document.getElementById('vexAuthGate');
      if (ov && ov.contains(e.target)) return; // allow interactions inside the gate card
      var el = e.target.closest && e.target.closest('a,button,[onclick],[role="button"],.game-card,.btn,input[type="submit"]');
      if (!el) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      if (authState === 'unknown') { pendingClick = true; return; } // decide after whoami answers
      showOverlay();
      if (!botOpened) {
        botOpened = true;
        openBotLink();
      }
    }, true);
  }

  function init() {
    // Gate immediately — a fast click must never slip through while we ask the server.
    gated = true;
    interceptClicks();
    fetch('/api/web/whoami', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.logged_in) {
          authState = 'in';
          gated = false; // authenticated via Telegram OTP
          var ov = document.getElementById('vexAuthGate');
          if (ov) ov.style.display = 'none'; // hide any race-shown card
          return;
        }
        authState = 'out';
        var pending = false;
        try { pending = localStorage.getItem('vex_gate_pending') === '1'; } catch (e) {}
        if (pending || pendingClick) {
          showOverlay(); // returning from the bot, or a click landed before the check finished
          if (pendingClick && !botOpened) { botOpened = true; openBotLink(); }
        }
      })
      .catch(function () { authState = 'out'; gated = false; /* fail open — don't lock users out on network errors */ });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
