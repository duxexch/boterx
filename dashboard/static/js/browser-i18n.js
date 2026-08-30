/* ===== VEX Browser i18n — Arabic/English translation for browser.html ===== */
(function(){
  'use strict';
  var LANG = (typeof AdminLang !== 'undefined') ? AdminLang :
             (localStorage.getItem('vex_admin_lang') || 'ar');

  /* ── Translation dictionary: Arabic → English ── */
  var D = {
    // Title
    'المتصفح - VEX': 'Browser - VEX',
    'المتصفح المدمج': 'Integrated Browser',
    'تصفح المواقع والتحكم بالوكلاء — جلسات محفوظة دائماً': 'Browse websites & control agents — sessions always saved',
    // Stats cards
    'النوافذ النشطة': 'Active Windows',
    'الخدمة (Daemon)': 'Service (Daemon)',
    'في النوم': 'Sleeping',
    'الصحة': 'Health',
    'نشط': 'Active',
    'متوقف': 'Stopped',
    ' Daemon نشط': ' Daemon Active',
    ' Daemon متوقف': ' Daemon Stopped',
    // Daemon controls
    'تحكم Daemon': 'Daemon Control',
    'تشغيل Daemon': 'Start Daemon',
    'إيقاف Daemon': 'Stop Daemon',
    'إدخال الكل في النوم': 'Sleep All',
    'إيقاظ الكل': 'Wake All',
    'حفظ Snapshot': 'Save Snapshot',
    'تحديث': 'Refresh',
    'صلاحيات': 'Permissions',
    'جدولة': 'Schedules',
    'قوالب': 'Templates',
    'بروكسي': 'Proxy',
    'مجموعات': 'Groups',
    'إحصائيات': 'Analytics',
    'سجل': 'History',
    'الحافظة': 'Clipboard',
    'نسخ احتياطي': 'Backup',
    'لوحة معلومات': 'Dashboard',
    'حجب الإعلانات': 'Ad Blocker',
    'وحدة التحكم': 'Console',
    'تصدير PDF': 'Export PDF',
    'الأداء': 'Performance',
    'أحداث مباشرة': 'Live Events',
    // Permissions
    'صلاحيات الوكيل في المتصفح': 'Agent Browser Permissions',
    // Schedules
    'المهام المجدولة': 'Scheduled Tasks',
    '+ إضافة': '+ Add',
    'لا توجد مهام مجدولة': 'No scheduled tasks',
    'ث': 's',
    // Templates
    'قوالب المتصفح': 'Browser Templates',
    '+ قالب جديد': '+ New Template',
    'مدمج': 'Built-in',
    // Proxies
    'إدارة البروكسي': 'Proxy Management',
    '+ استيراد': '+ Import',
    'الإجمالي': 'Total',
    'استخدامات': 'Uses',
    // Groups
    'المجموعات': 'Groups',
    '+ مجموعة': '+ Group',
    ' متصفح)': ' browser(s))',
    // Analytics
    'إحصائيات الاستخدام': 'Usage Statistics',
    'أكثر المواقع زيارة:': 'Most Visited Sites:',
    ' مرة': ' time(s)',
    // History
    'سجل التصفح': 'Browsing History',
    'بحث...': 'Search...',
    'مسح': 'Clear',
    'لا يوجد سجل': 'No history',
    'نسخ': 'Copy',
    // Clipboard
    '+ إضافة': '+ Add',
    'مسح غير المثبت': 'Clear Unpinned',
    'الحافظة فارغة': 'Clipboard is empty',
    'تثبيت': 'Pin',
    'حذف': 'Delete',
    // Backups
    'النسخ الاحتياطي': 'Backup',
    '+ نسخة جديدة': '+ New Backup',
    'استعادة': 'Restore',
    'لا توجد نسخ احتياطية': 'No backups found',
    // Dashboard
    'لوحة معلومات المتصفح': 'Browser Dashboard',
    'صفحة مزاراة': 'Pages Visited',
    'رابط فريد': 'Unique URL',
    'معرفة مخزنة': 'Knowledge Stored',
    'المواقع الأكثر زيارة:': 'Most Visited Sites:',
    // Instances
    'النوافذ': 'Windows',
    'خامل:': 'Idle:',
    'لا توجد نوافذ مفتوحة': 'No open windows',
    'إيقاظ': 'Wake',
    'إدخال في النوم': 'Sleep',
    'د': 'm',
    // Profiles
    'الجلسات المحفوظة': 'Saved Sessions',
    'فتح': 'Open',
    'لا توجد جلسات محفوظة': 'No saved sessions',
    ' كوكيز | ': ' cookie(s) | ',
    // URL bar
    'رجوع': 'Go Back',
    'اذهب': 'Go',
    'لقطة شاشة': 'Screenshot',
    'الكوكيز': 'Cookies',
    'التسجيل': 'Recording',
    // Viewport
    'جاري تحميل المتصفح...': 'Loading browser...',
    'المتصفح متوقف': 'Browser is stopped',
    'تشغيل': 'Start',
    'اختر نافذة أو أنشئ نافذة جديدة': 'Select a window or create a new one',
    'نافذة جديدة': 'New Window',
    // Action bar
    'أدوات التحكم': 'Control Tools',
    'صعود': 'Scroll Up',
    'نزول': 'Scroll Down',
    'تنفيذ': 'Execute',
    // Action log
    'آخر الإجراءات': 'Recent Actions',
    'تحليل الصفحة': 'Analyze Page',
    // Site knowledge
    'معرفة الموقع:': 'Site Knowledge:',
    'نماذج': 'Forms',
    'أنماط': 'Patterns',
    'نجاح': 'Success',
    'أفضل Selectors:': 'Top Selectors:',
    // Quick tasks
    '⚡ مهام سريعة': '⚡ Quick Tasks',
    'استخراج محتوى الصفحة': 'Extract Page Content',
    'استخراج': 'Extract',
    'تحليل عناصر الصفحة': 'Analyze Page Elements',
    'تحليل': 'Analyze',
    'حفظ لقطة + تحليل': 'Save Screenshot + Analyze',
    'لقطة+تحليل': 'Screenshot+Analyze',
    'المهام الأخيرة:': 'Recent Tasks:',
    // Cookie manager
    'مزامنة': 'Sync',
    'تصدير': 'Export',
    'مسح الكل': 'Clear All',
    'لا توجد كوكيز': 'No cookies',
    // Session recording
    '🎬 تسجيل الجلسات': '🎬 Session Recording',
    'إيقاف': 'Stop',
    'جاري التسجيل...': 'Recording...',
    'إجراء': 'action(s)',
    ' إجراء)': ' action(s))',
    'لا توجد جلسات مسجلة': 'No recorded sessions',
    'تشغيل': 'Play',
    // Multi-tab
    '📑 النوافذ الفرعية': '📑 Sub-Windows',
    '+ نافذة جديدة': '+ New Window',
    'تبديل': 'Switch',
    // Create modal
    'نافذة متصفح جديدة': 'New Browser Window',
    'اسم النافذة': 'Window Name',
    'مثال: حساب تويتر': 'e.g.: Twitter account',
    'الرابط (اختياري)': 'URL (optional)',
    'بروكسي (اختياري)': 'Proxy (optional)',
    'إنشاء وتشغيل': 'Create & Start',
    'إلغاء': 'Cancel',
    // Toast messages
    'فشل إنشاء النافذة': 'Failed to create window',
    'فشل تشغيل المتصفح': 'Failed to start browser',
    'فشل التنقل': 'Navigation failed',
    'تم أخذ اللقطة': 'Screenshot taken',
    'فشل فتح الجلسة': 'Failed to open session',
    'تم تشغيل Daemon': 'Daemon started',
    'فشل تشغيل Daemon': 'Failed to start Daemon',
    'تم إيقاف Daemon': 'Daemon stopped',
    'فشل إيقاف Daemon': 'Failed to stop Daemon',
    'تم إدخال الكل في النوم': 'All put to sleep',
    'تم إيقاظ الكل': 'All woken up',
    'تم حفظ Snapshot': 'Snapshot saved',
    'جاري تحليل الصفحة...': 'Analyzing page...',
    'تم التحليل بنجاح': 'Analysis completed',
    'فشل التحليل': 'Analysis failed',
    'جاري استخراج المحتوى...': 'Extracting content...',
    'تم الاستخراج: ': 'Extraction complete: ',
    'لم يتم استخراج محتوى': 'No content extracted',
    'فشل الاستخراج': 'Extraction failed',
    // Confirm dialogs
    'مسح كل الكوكيز؟': 'Clear all cookies?',
    'حذف البروكسي؟': 'Delete this proxy?',
    'حذف المجموعة؟': 'Delete this group?',
    'مسح كل السجل؟': 'Clear all history?',
    'استعادة هذه النسخة؟ سيتم استبدال البيانات الحالية': 'Restore this backup? Current data will be replaced',
    'حذف النسخة الاحتياطية؟': 'Delete this backup?',
    // Prompt dialogs
    'أدخل النص:': 'Enter text:',
    'اسم النسخة الاحتياطية:': 'Backup name:',
    // Alert dialogs
    'تمت الاستعادة بنجاح': 'Restore completed successfully',
    'خطأ في الاستعادة': 'Restore error',
    // Misc
    'جلسة يدوية': 'Manual session',
    'بدون عنوان': 'Untitled',
    // Short labels
    'Active': 'نشط',
    'Stopped': 'متوقف',
    'n/a': 'غير متوفر',
  };

  /* ── Reverse map for EN→AR lookups ── */
  var D_REV = {};
  for (var k in D) { if (D.hasOwnProperty(k)) D_REV[D[k]] = k; }

  /* ── Public translate function ── */
  window.bt = function(arabic) {
    if (!arabic) return arabic || '';
    if (LANG === 'en') {
      // If input is Arabic and we have a translation, return English
      return D[arabic] || D_REV[arabic] || arabic;
    }
    // AR mode: if input is English, reverse-translate to Arabic
    if (D_REV[arabic]) return D_REV[arabic];
    return arabic;
  };

  /* ── Get current language ── */
  window.btLang = function() { return LANG; };

  /* ── DOM walker: auto-translate all text nodes ── */
  var SKIP_TAGS = {'SCRIPT':1,'STYLE':1,'NOSCRIPT':1,'TEXTAREA':1,'INPUT':1,'SVG':1};
  var done = new WeakSet();

  function walkTranslate(node) {
    if (!node || done.has(node)) return;
    done.add(node);

    if (node.nodeType === 3) { // Text node
      var txt = node.textContent.trim();
      if (txt && D[txt]) {
        node.textContent = node.textContent.replace(txt, D[txt]);
      }
      return;
    }

    if (node.nodeType !== 1) return;
    if (SKIP_TAGS[node.tagName]) return;

    // Translate title, placeholder, aria-label attributes
    ['title','placeholder','aria-label'].forEach(function(attr){
      var v = node.getAttribute(attr);
      if (v && D[v]) node.setAttribute(attr, D[v]);
    });

    // Translate data-i18n elements
    var di = node.getAttribute('data-i18n');
    if (di && D[di]) node.textContent = D[di];

    // Walk children
    var children = node.childNodes;
    for (var i = 0; i < children.length; i++) {
      walkTranslate(children[i]);
    }
  }

  function translatePage() {
    walkTranslate(document.body);
  }

  /* ── Alpine.js integration ── */
  if (typeof Alpine !== 'undefined') {
    Alpine.magic('bt', function() { return window.bt; });
  }

  /* ── Auto-translate on DOM ready ── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function(){ setTimeout(translatePage, 50); });
  } else {
    setTimeout(translatePage, 50);
  }

  // Re-translate after Alpine initializes (Alpine runs after DOMContentLoaded)
  document.addEventListener('alpine:initialized', function(){ setTimeout(translatePage, 100); });

  window.browserTranslatePage = translatePage;
})();
