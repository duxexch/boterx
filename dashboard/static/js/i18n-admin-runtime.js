/* i18n-admin-runtime v2 — EXACT-PHRASE translation only.
   Full text-node match against window.ADMIN_PHRASES. Never does substring
   replacement, so text corruption is impossible. Arabic templates stay
   untouched when lang=ar; when lang=en every matching node is translated. */
(function () {
  'use strict';

  var PHRASES = window.ADMIN_PHRASES || {};
  var PATTERNS = window.ADMIN_PHRASE_PATTERNS || {};
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, CODE: 1, PRE: 1, TEXTAREA: 1 };
  var ATTRS = ['placeholder', 'title', 'aria-label'];
  var observer = null;

  function getLang() {
    try { return localStorage.getItem('lang') === 'en' ? 'en' : 'ar'; }
    catch (e) { return 'ar'; }
  }

  function lookup(txt) {
    var en = PHRASES[txt];
    if (en) return en;
    // digit-normalized pattern match: "وصول: 12" -> "وصول: #"
    if (/[0-9\u0660-\u0669]/.test(txt)) {
      var key = txt.replace(/[0-9\u0660-\u0669]+/g, '#');
      var pen = PATTERNS[key];
      if (pen) {
        var nums = txt.match(/[0-9\u0660-\u0669]+/g) || [];
        var i = 0;
        return pen.replace(/#/g, function () { return nums[i++] !== undefined ? nums[i - 1] : '#'; });
      }
    }
    return null;
  }

  function translateTextNode(node) {
    if (!node || node.nodeType !== 3) return;
    var raw = node.nodeValue;
    if (!raw) return;
    var txt = raw.trim();
    if (!txt || !/[\u0600-\u06FF]/.test(txt)) return;   // only Arabic text
    var en = lookup(txt);
    if (en && en !== txt) {
      // preserve surrounding whitespace exactly
      var idx = raw.indexOf(txt);
      var lead = raw.slice(0, idx);
      var trail = raw.slice(idx + txt.length);
      node.nodeValue = lead + en + trail;
    }
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { translateTextNode(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 11) return;
    if (SKIP_TAGS[root.tagName]) return;
    // translate attributes
    if (root.nodeType === 1 && getLang() === 'en') {
      for (var a = 0; a < ATTRS.length; a++) {
        var val = root.getAttribute && root.getAttribute(ATTRS[a]);
        if (val && /[\u0600-\u06FF]/.test(val)) {
          var t = lookup(val.trim());
          if (t) root.setAttribute(ATTRS[a], t);
        }
      }
    }
    var kids = root.childNodes;
    for (var i = 0; i < kids.length; i++) walk(kids[i]);
  }

  function applyAll() {
    if (getLang() !== 'en') return;   // templates are Arabic-native
    walk(document.body || document.documentElement);
  }

  function initObserver() {
    if (observer || !window.MutationObserver || getLang() !== 'en') return;
    observer = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        if (m.type === 'characterData') translateTextNode(m.target);
        else if (m.type === 'childList') {
          for (var j = 0; j < m.addedNodes.length; j++) walk(m.addedNodes[j]);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  function boot() {
    applyAll();
    initObserver();
  }

  window.ADMIN_I18N_RUNTIME = { apply: applyAll, walk: walk };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
  window.addEventListener('load', applyAll);   // catch late-rendered content
})();
