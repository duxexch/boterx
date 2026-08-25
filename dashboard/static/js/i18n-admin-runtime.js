(function () {
  'use strict';

  var AR_RE = /[\u0600-\u06FF]/;
  var EN_RE = /[A-Za-z]/;
  var WS_RE = /\s+/g;
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, CODE: 1, PRE: 1, TEXTAREA: 1 };
  var SKIP_EXACT = { EN: 1, AR: 1, 'ع': 1 };

  var state = {
    lang: getLang(),
    arToEnExact: new Map(),
    enToArExact: new Map(),
    arLexicon: [],
    enLexicon: [],
    observer: null,
  };

  function getLang() {
    try {
      return localStorage.getItem('lang') === 'en' ? 'en' : 'ar';
    } catch (e) {
      return 'ar';
    }
  }

  function norm(s) {
    return String(s || '').replace(/\u00a0/g, ' ').replace(WS_RE, ' ').trim();
  }

  function escapeRegExp(s) {
    return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function addPair(ar, en) {
    ar = norm(ar);
    en = norm(en);
    if (!ar || !en || ar === en) return;
    if (!state.arToEnExact.has(ar)) state.arToEnExact.set(ar, en);
    if (!state.enToArExact.has(en)) state.enToArExact.set(en, ar);
  }

  function buildPairsFromAppDict() {
    if (!window.I18N || !window.I18N.ar || !window.I18N.en) return;
    var ar = window.I18N.ar;
    var en = window.I18N.en;
    var keys = {};
    Object.keys(ar).forEach(function (k) { keys[k] = 1; });
    Object.keys(en).forEach(function (k) { keys[k] = 1; });

    Object.keys(keys).forEach(function (k) {
      var va = ar[k];
      var ve = en[k];
      if (typeof va !== 'string' || typeof ve !== 'string') return;
      if (AR_RE.test(va) && EN_RE.test(ve)) addPair(va, ve);
      else if (AR_RE.test(ve) && EN_RE.test(va)) addPair(ve, va);
    });
  }

  function buildPairsFromLexicon() {
    var lex = window.ADMIN_I18N_LEXICON || {};
    var a2e = lex.arToEn || {};
    var e2a = lex.enToAr || {};

    Object.keys(a2e).forEach(function (ar) {
      addPair(ar, a2e[ar]);
    });
    Object.keys(e2a).forEach(function (en) {
      addPair(e2a[en], en);
    });

    var manual = {
      'Dispute': 'نزاع',
      'Open': 'مفتوح',
      'Muted': 'صامت',
      'Click to go': 'انقر للذهاب',
      'Click to open': 'انقر للفتح',
      'No notifications': 'لا توجد إشعارات',
      'Notifications': 'الإشعارات',
      'Notification': 'إشعار',
      'Now': 'الآن',
      'Pending': 'معلق',
    };
    Object.keys(manual).forEach(function (en) {
      addPair(manual[en], en);
    });
  }

  function compileLexicons() {
    state.arLexicon = Array.from(state.arToEnExact.entries()).sort(function (a, b) {
      return b[0].length - a[0].length;
    });
    state.enLexicon = Array.from(state.enToArExact.entries()).sort(function (a, b) {
      return b[0].length - a[0].length;
    });
  }

  function translateCore(text, targetLang) {
    var core = norm(text);
    if (!core || SKIP_EXACT[core]) return text;

    if (targetLang === 'en') {
      if (state.arToEnExact.has(core)) return state.arToEnExact.get(core);
      if (!AR_RE.test(core)) return core;
      var outEn = core;
      for (var i = 0; i < state.arLexicon.length; i++) {
        var srcA = state.arLexicon[i][0];
        var dstE = state.arLexicon[i][1];
        if (outEn.indexOf(srcA) !== -1) outEn = outEn.split(srcA).join(dstE);
      }
      return outEn;
    }

    if (state.enToArExact.has(core)) return state.enToArExact.get(core);
    if (!EN_RE.test(core)) return core;
    var outAr = core;
    for (var j = 0; j < state.enLexicon.length; j++) {
      var srcE = state.enLexicon[j][0];
      var dstA = state.enLexicon[j][1];
      if (outAr.indexOf(srcE) !== -1) {
        try {
          outAr = outAr.replace(new RegExp(escapeRegExp(srcE), 'gi'), dstA);
        } catch (e) {
          outAr = outAr.split(srcE).join(dstA);
        }
      }
    }
    return outAr;
  }

  function translatePreserveSpacing(raw) {
    if (raw == null) return raw;
    var text = String(raw);
    var core = norm(text);
    if (!core) return text;
    if (/^[0-9\s:|+\-_.%()\[\]{}#,/\\]+$/.test(core)) return text;

    var left = text.match(/^\s*/);
    var right = text.match(/\s*$/);
    left = left ? left[0] : '';
    right = right ? right[0] : '';

    var translated = translateCore(core, state.lang);
    return left + translated + right;
  }

  function translateNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE || !node.nodeValue) return;
    var parent = node.parentNode;
    if (!parent || (parent.tagName && SKIP_TAGS[parent.tagName])) return;
    if (parent.closest && parent.closest('[data-no-i18n="1"]')) return;

    var before = node.nodeValue;
    var after = translatePreserveSpacing(before);
    if (after !== before) node.nodeValue = after;
  }

  function translateAttrs(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return;
    if (SKIP_TAGS[el.tagName]) return;
    if (el.closest && el.closest('[data-no-i18n="1"]')) return;

    ['placeholder', 'title', 'aria-label', 'alt'].forEach(function (attr) {
      if (!el.hasAttribute(attr)) return;
      var v = el.getAttribute(attr);
      var t = translatePreserveSpacing(v);
      if (t !== v) el.setAttribute(attr, t);
    });

    if (el.tagName === 'INPUT') {
      var type = String(el.getAttribute('type') || '').toLowerCase();
      if (type === 'button' || type === 'submit' || type === 'reset') {
        var val = el.getAttribute('value');
        if (val) {
          var tval = translatePreserveSpacing(val);
          if (tval !== val) el.setAttribute('value', tval);
        }
      }
    }
  }

  function walkAndTranslate(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;

    if (root.nodeType === Node.ELEMENT_NODE) translateAttrs(root);

    var children = root.childNodes || [];
    for (var i = 0; i < children.length; i++) {
      var ch = children[i];
      if (ch.nodeType === Node.TEXT_NODE) translateNode(ch);
      else if (ch.nodeType === Node.ELEMENT_NODE) walkAndTranslate(ch);
    }
  }

  function patchDialogs() {
    if (!window.__ADMIN_I18N_DIALOG_PATCHED__) {
      window.__ADMIN_I18N_DIALOG_PATCHED__ = true;

      var oldAlert = window.alert;
      var oldConfirm = window.confirm;
      var oldPrompt = window.prompt;

      window.alert = function (msg) {
        return oldAlert.call(window, translatePreserveSpacing(msg));
      };
      window.confirm = function (msg) {
        return oldConfirm.call(window, translatePreserveSpacing(msg));
      };
      window.prompt = function (msg, defv) {
        return oldPrompt.call(window, translatePreserveSpacing(msg), defv);
      };
    }

    if (typeof window.toast === 'function' && !window.toast.__adminI18nWrapped) {
      var oldToast = window.toast;
      var wrapped = function (message, type) {
        return oldToast.call(window, translatePreserveSpacing(message), type);
      };
      wrapped.__adminI18nWrapped = true;
      window.toast = wrapped;
    }
  }

  function applyAll() {
    state.lang = getLang();
    walkAndTranslate(document.body || document.documentElement);
  }

  function initObserver() {
    if (state.observer || !window.MutationObserver || !document.body) return;
    state.observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var m = mutations[i];
        if (m.type === 'characterData') {
          translateNode(m.target);
          continue;
        }
        if (m.type === 'attributes') {
          translateAttrs(m.target);
          continue;
        }
        for (var j = 0; j < m.addedNodes.length; j++) {
          walkAndTranslate(m.addedNodes[j]);
        }
      }
    });
    state.observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['placeholder', 'title', 'aria-label', 'alt', 'value']
    });
  }

  function boot() {
    buildPairsFromAppDict();
    buildPairsFromLexicon();
    compileLexicons();
    patchDialogs();
    applyAll();
    initObserver();
  }

  window.ADMIN_I18N_RUNTIME = {
    apply: applyAll,
    translate: translatePreserveSpacing,
    addPair: addPair,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.addEventListener('storage', function (e) {
    if (e && e.key === 'lang') applyAll();
  });
})();
