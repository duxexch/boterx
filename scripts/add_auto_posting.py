# -*- coding: utf-8 -*-
"""
Complete auto-posting system — part 2: inject code into app.py + channels.html
"""
import io

# ===== BACKEND: app.py =====
APP = 'dashboard/app.py'
app = io.open(APP, 'r', encoding='utf-8').read()

# 1. Channel branding fields
old_f = """    'allow_subadmin_publish', 'ai_agent_id', 'platform_account_id'
]"""
new_f = """    'allow_subadmin_publish', 'ai_agent_id', 'platform_account_id',
    'company_name', 'download_link', 'promo_code', 'affiliate_link',
    'auto_post_enabled', 'auto_post_interval_min', 'auto_post_types'
]"""
if old_f in app:
    app = app.replace(old_f, new_f, 1)
    print('OK: _CHANNEL_DEFAULT_FIELDS')

# 2. Normalize defaults
old_n = """    _setdefault('ai_agent_id', '')
    _setdefault('platform_account_id', '')"""
new_n = """    _setdefault('ai_agent_id', '')
    _setdefault('platform_account_id', '')
    _setdefault('company_name', '')
    _setdefault('download_link', '')
    _setdefault('promo_code', '')
    _setdefault('affiliate_link', '')
    _setdefault('auto_post_enabled', 'no')
    _setdefault('auto_post_interval_min', '120')
    _setdefault('auto_post_types', 'info|question|prediction|analysis')"""
if old_n in app:
    app = app.replace(old_n, new_n, 1)
    print('OK: _normalize defaults')

# 3. Settings editable
old_e = """        'allow_subadmin_publish'
    ]"""
new_e = """        'allow_subadmin_publish',
        'company_name', 'download_link', 'promo_code', 'affiliate_link',
        'auto_post_enabled', 'auto_post_interval_min', 'auto_post_types'
    ]"""
if old_e in app:
    app = app.replace(old_e, new_e, 1)
    print('OK: editable list')

# 4. Add channel manual
old_a = """        'platform_account_id': str(data.get('platform_account_id', '') or '').strip(),
    }"""
new_a = """        'platform_account_id': str(data.get('platform_account_id', '') or '').strip(),
        'company_name': str(data.get('company_name', '') or '').strip(),
        'download_link': str(data.get('download_link', '') or '').strip(),
        'promo_code': str(data.get('promo_code', '') or '').strip(),
        'affiliate_link': str(data.get('affiliate_link', '') or '').strip(),
        'auto_post_enabled': 'no',
        'auto_post_interval_min': '120',
        'auto_post_types': 'info|question|prediction|analysis',
    }"""
if old_a in app:
    app = app.replace(old_a, new_a, 1)
    print('OK: add channel manual')

# 5. Add import random if missing
if 'import random' not in app:
    app = app.replace('import secrets', 'import secrets\nimport random', 1)
    print('OK: random import')

# 6. Inject auto-posting engine from separate file
engine_code = io.open('scripts/auto_post_engine_code.py', 'r', encoding='utf-8').read()
# Extract just the code between the triple quotes
start = engine_code.find("AUTO_POST_ENGINE_CODE = '''") + len("AUTO_POST_ENGINE_CODE = '''")
end = engine_code.rfind("'''")
actual_code = engine_code[start:end]

marker = "@app.route('/api/channels', methods=['POST'])\n@api_auth\n@permission_required('send_broadcast')\ndef api_add_channel_manual():"
if marker in app and 'api_auto_post_run' not in app:
    app = app.replace(marker, actual_code + '\n' + marker, 1)
    print('OK: auto-posting engine injected')

io.open(APP, 'w', encoding='utf-8').write(app)
print(f'app.py: {len(app)} chars')

# ===== FRONTEND: channels.html =====
CH = 'dashboard/templates/channels.html'
ch = io.open(CH, 'r', encoding='utf-8').read()

# 1. Channel branding in detail modal
old_s = """                    <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">📂 الفئة</label>"""
new_s = """                    <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">🏢 اسم الشركة</label>
                            <input type="text" x-model="selectedChannel.company_name" @change="saveChannelSetting('company_name', selectedChannel.company_name)" class="input text-sm py-1 w-full" placeholder="VEX Games">
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">📱 رابط التحميل</label>
                            <input type="text" x-model="selectedChannel.download_link" @change="saveChannelSetting('download_link', selectedChannel.download_link)" class="input text-sm py-1 w-full" placeholder="https://...">
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">🎁 كود الخصم</label>
                            <input type="text" x-model="selectedChannel.promo_code" @change="saveChannelSetting('promo_code', selectedChannel.promo_code)" class="input text-sm py-1 w-full" placeholder="VEX50">
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">🔗 رابط الأفلييت</label>
                            <input type="text" x-model="selectedChannel.affiliate_link" @change="saveChannelSetting('affiliate_link', selectedChannel.affiliate_link)" class="input text-sm py-1 w-full" placeholder="https://...">
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">📂 الفئة</label>"""
if old_s in ch:
    ch = ch.replace(old_s, new_s, 1)
    print('OK: branding in modal')

# 2. Auto-post settings in detail modal
old_send = """            <div class="bg-slate-800 rounded-xl border border-slate-700 p-4">
                <h4 class="font-bold mb-3">📨 إرسال رسالة</h3>"""
new_send = """            <div class="bg-slate-800 rounded-xl border border-slate-700 p-4">
                <h4 class="font-bold mb-3">🤖 النشر التلقائي</h4>
                <div class="space-y-2">
                    <div class="flex justify-between items-center p-2 bg-slate-900/50 rounded">
                        <span class="text-slate-400">فعّل النشر التلقائي</span>
                        <button @click="selectedChannel.auto_post_enabled = selectedChannel.auto_post_enabled === 'yes' ? 'no' : 'yes'; saveChannelSetting('auto_post_enabled', selectedChannel.auto_post_enabled)" class="relative inline-flex h-6 w-11 items-center rounded-full transition" :class="selectedChannel.auto_post_enabled === 'yes' ? 'bg-green-500' : 'bg-slate-600'"><span class="inline-block h-4 w-4 transform rounded-full bg-white transition" :class="toggleClasses(selectedChannel.auto_post_enabled === 'yes')"></span></button>
                    </div>
                    <div x-show="selectedChannel.auto_post_enabled === 'yes'" class="space-y-2">
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">⏰ الفاصل الزمني</label>
                            <select x-model="selectedChannel.auto_post_interval_min" @change="saveChannelSetting('auto_post_interval_min', selectedChannel.auto_post_interval_min)" class="input text-sm py-1 w-full">
                                <option value="30">كل 30 دقيقة</option>
                                <option value="60">كل ساعة</option>
                                <option value="90">كل ساعة ونص</option>
                                <option value="120">كل ساعتين</option>
                                <option value="180">كل 3 ساعات</option>
                                <option value="240">كل 4 ساعات</option>
                            </select>
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">📝 أنواع المحتوى</label>
                            <div class="flex flex-wrap gap-1">
                                <template x-for="tp in ['info','question','prediction','analysis','live','result']" :key="tp">
                                    <button @click="toggleAutoPostType(tp)" class="px-2 py-1 rounded text-xs transition" :class="(selectedChannel.auto_post_types || '').includes(tp) ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-slate-700 text-slate-400 border border-transparent'" x-text="tp"></button>
                                </template>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-slate-800 rounded-xl border border-slate-700 p-4">
                <h4 class="font-bold mb-3">📨 إرسال رسالة</h4>"""
if old_send in ch:
    ch = ch.replace(old_send, new_send, 1)
    print('OK: auto-post in modal')

# 3. Content type buttons in composer
old_label = """            <label class="block text-sm text-slate-400 mb-1">✍️ نص المنشور</label>"""
new_label = """            <label class="block text-sm text-slate-400 mb-1">✍️ نص المنشور</label>
            <div class="flex flex-wrap gap-2 mb-2">
                <button @click="insertContentType('info')" class="px-3 py-1.5 rounded-lg text-xs bg-blue-500/20 border border-blue-500/30 text-blue-300 hover:bg-blue-500/30">📊 معلومة</button>
                <button @click="insertContentType('question')" class="px-3 py-1.5 rounded-lg text-xs bg-purple-500/20 border border-purple-500/30 text-purple-300 hover:bg-purple-500/30">❓ سؤال</button>
                <button @click="insertContentType('prediction')" class="px-3 py-1.5 rounded-lg text-xs bg-amber-500/20 border border-amber-500/30 text-amber-300 hover:bg-amber-500/30">🔮 توقع</button>
                <button @click="insertContentType('analysis')" class="px-3 py-1.5 rounded-lg text-xs bg-green-500/20 border border-green-500/30 text-green-300 hover:bg-green-500/30">📋 تحليل</button>
                <button @click="insertContentType('live')" class="px-3 py-1.5 rounded-lg text-xs bg-red-500/20 border border-red-500/30 text-red-300 hover:bg-red-500/30">🔴 مباشر</button>
                <button @click="insertContentType('result')" class="px-3 py-1.5 rounded-lg text-xs bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/30">🏁 نتيجة</button>
            </div>
            <div class="flex flex-wrap gap-1 mb-2">
                <button @click="insertPlaceholder('company_name')" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{company_name}</button>
                <button @click="insertPlaceholder('download_link')" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{download_link}</button>
                <button @click="insertPlaceholder('promo_code')" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{promo_code}</button>
                <button @click="insertPlaceholder('affiliate_link')" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{affiliate_link}</button>
            </div>"""
if old_label in ch:
    ch = ch.replace(old_label, new_label, 1)
    print('OK: content type buttons')

# 4. JS functions
old_sub = """        async submitPost() {"""
new_sub = """        insertContentType(type) {
            var templates = {
                info: '📊 إحصائيات اليوم: فريقك سجّل {stat_highlight}. تابع التحديثات معنا!',
                question: '🤔 سؤال اليوم: ما رأيك في أداء الفريق؟ اكتب رأيك في التعليقات!',
                prediction: '🔮 توقعاتنا: {prediction_details}. ما رأيك؟',
                analysis: '📋 تحليل مباراة {match_name}:\\n{analysis_details}',
                live: '🔴 مباشر | {live_event}',
                result: '🏁 نتيجة المباراة: {result}',
            };
            this.postForm.message = (this.postForm.message || '') + '\\n' + (templates[type] || '');
        },
        insertPlaceholder(name) {
            this.postForm.message = (this.postForm.message || '') + '{' + name + '}';
        },
        toggleAutoPostType(tp) {
            var types = (this.selectedChannel.auto_post_types || '').split('|').filter(Boolean);
            var idx = types.indexOf(tp);
            if (idx >= 0) types.splice(idx, 1);
            else types.push(tp);
            this.selectedChannel.auto_post_types = types.join('|');
            this.saveChannelSetting('auto_post_types', this.selectedChannel.auto_post_types);
        },
        async runAutoPost() {
            try {
                var d = await api('/api/auto-post/run', { method: 'POST', body: '{}' });
                toast(d.queued ? 'تم جدولة ' + d.queued + ' منشور' : (d.error || 'لا قنوات'), d.queued ? 'success' : 'warning');
            } catch(e) { toast('خطأ', 'error'); }
        },
        async submitPost() {"""
if old_sub in ch:
    ch = ch.replace(old_sub, new_sub, 1)
    print('OK: JS functions')

io.open(CH, 'w', encoding='utf-8').write(ch)
print(f'channels.html: {len(ch)} chars')
print('\n=== ALL DONE ===')
