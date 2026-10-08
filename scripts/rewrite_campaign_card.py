# -*- coding: utf-8 -*-
"""Rewrite campaign modal to be dynamic — show options based on selections."""
import io

CH = 'dashboard/templates/channels.html'
ch = io.open(CH, 'r', encoding='utf-8').read()
orig = len(ch)

# ========== 1. Replace cmpForm definition ==========
old_cmp = "        cmpForm: { name: '', message: '', mediaList: [], target: 'both', recipient: 'all', priority: 'normal', country: 'all', repeat: 'once', scheduled_at: '', platform_account_id: '', uploading: false },"
new_cmp = """        cmpForm: { name: '', message: '', mediaList: [], target: 'telegram', recipient: 'all', priority: 'normal', country: 'all', repeat: 'once', scheduled_at: '', platform_account_id: '', uploading: false, selectedChannels: [], selectedGroups: [], whatsappApi: '', whatsappContacts: '', whatsappGroups: '' },"""
if old_cmp in ch:
    ch = ch.replace(old_cmp, new_cmp, 1)
    print('OK: cmpForm updated')

# ========== 2. Replace the entire campaign modal HTML ==========
old_modal_start = """        <!-- Create Campaign Modal -->
        <div x-show="showCampaignModal" class="modal-overlay" @click.self="showCampaignModal = false" style="display:none">
            <div class="modal max-w-2xl">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="font-bold text-lg">📊 إنشاء حملة إعلانية</h3>
                    <button @click="showCampaignModal = false" class="text-slate-400 hover:text-white"><i class="fas fa-times"></i></button>
                </div>
                <div class="space-y-4">
                    <!-- Name -->
                    <div><label class="block text-sm text-slate-400 mb-1">📝 اسم الحملة</label><input x-model="cmpForm.name" class="input w-full" placeholder="مثال: حملة لعبة Aviator"></div>
                    <!-- Message -->
                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <label class="block text-sm text-slate-400">💬 نص الإعلان</label>
                            <button @click="generateContent()" type="button" class="text-xs px-2 py-1 rounded-lg bg-purple-600/20 text-purple-400 hover:bg-purple-600 hover:text-white transition flex items-center gap-1"><i class="fas fa-magic-wand-sparkles"></i> توليد بالـ AI</button>
                        </div>
                        <textarea x-model="cmpForm.message" rows="4" class="input w-full" placeholder="اكتب نص الإعلان هنا... أو اضغط توليد بالـ AI"></textarea>
                    </div>
                    <!-- Media -->
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">📎 المرفقات</label>
                        <div class="flex flex-wrap gap-2">
                            <template x-for="(media, idx) in cmpForm.mediaList" :key="idx">
                                <div class="relative w-16 h-16 rounded-lg overflow-hidden bg-slate-700 border border-slate-600 group">
                                    <img x-show="media.type.startsWith('image')" :src="media.url" class="w-full h-full object-cover">
                                    <div x-show="!media.type.startsWith('image')" class="w-full h-full flex items-center justify-center"><i class="fas fa-file text-xl text-slate-400"></i></div>
                                    <button @click="cmpForm.mediaList.splice(idx, 1)" class="absolute inset-0 bg-red-600/80 flex items-center justify-center opacity-0 group-hover:opacity-100 transition"><i class="fas fa-trash text-white"></i></button>
                                </div>
                            </template>
                            <label class="w-16 h-16 rounded-lg border-2 border-dashed border-slate-500 flex items-center justify-center cursor-pointer hover:border-green-500 transition" :class="cmpForm.uploading ? 'opacity-50 pointer-events-none' : ''">
                                <i class="fas fa-plus text-xl text-slate-400"></i>
                                <input type="file" class="hidden" accept="image/*,video/*" @change="uploadCampaignMedia($event)">
                            </label>
                        </div>
                    </div>
                    <!-- Target + Recipient -->
                    <div class="grid grid-cols-2 gap-3">
                        <div><label class="block text-sm text-slate-400 mb-1">🎯 المنصة</label><select x-model="cmpForm.target" class="input w-full"><option value="telegram">📱 تيليغرام</option><option value="whatsapp">🟢 واتساب</option><option value="web">🌐 الموقع</option><option value="both">📱🌐 الاثنين</option><option value="all">📱🌐🟢 الكل</option></select></div>
                        <div><label class="block text-sm text-slate-400 mb-1">👥 الجمهور</label><select x-model="cmpForm.recipient" class="input w-full"><option value="all">👥 الكل</option><option value="single">📱 فردي (قنوات محددة)</option><option value="group">👥 مجموعة قنوات</option></select></div>
                    </div>
                    <div class="grid grid-cols-3 gap-3">
                        <div><label class="block text-sm text-slate-400 mb-1">⚡ الأولوية</label><select x-model="cmpForm.priority" class="input w-full"><option value="normal">🔔 عادية</option><option value="high">⚡ عالية</option><option value="urgent">🚨 عاجلة</option></select></div>
                        <div><label class="block text-sm text-slate-400 mb-1">🌍 الدولة</label><select x-model="cmpForm.country" class="input w-full"><option value="all">🌍 الكل</option><option value="EG">🇪🇬 مصر</option><option value="SA">🇸🇦 السعودية</option><option value="AE">🇦🇪 الإمارات</option><option value="JO">🇯🇴 الأردن</option><option value="MA">🇲🇦 المغرب</option><option value="DZ">🇩🇿 الجزائر</option></select></div>
                        <div><label class="block text-sm text-slate-400 mb-1">🔁 التكرار</label><select x-model="cmpForm.repeat" class="input w-full"><option value="once">مرة واحدة</option><option value="daily">يومي</option><option value="weekly">أسبوعي</option></select></div>
                    </div>
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">🔐 حساب المنصة (اختياري)</label>
                        <select x-model="cmpForm.platform_account_id" class="input w-full">
                            <option value="">— تلقائي —</option>
                            <template x-for="acc in platformAccounts" :key="acc.id">
                                <option :value="acc.id" x-text="acc.account_name + ' (' + acc.platform + ')'" :disabled="acc.is_active !== 'yes'"></option>
                            </template>
                        </select>
                    </div>
                    <!-- Schedule -->
                    <div><label class="block text-sm text-slate-400 mb-1">⏰ الجدولة (اتركه فارغاً للإرسال فوراً)</label><input type="datetime-local" x-model="cmpForm.scheduled_at" class="input w-full"></div>
                </div>
                <div class="flex gap-2 justify-end mt-4">
                    <button @click="showCampaignModal = false" class="btn btn-sm" style="background:#475569">إلغاء</button>
                    <button @click="createCampaign()" class="btn btn-primary btn-sm" x-text="cmpForm.scheduled_at ? '⏰ جدولة الحملة' : '🚀 إطلاق فوراً'"></button>
                </div>
            </div>
        </div>"""

new_modal = """        <!-- Create Campaign Modal -->
        <div x-show="showCampaignModal" class="modal-overlay" @click.self="showCampaignModal = false" style="display:none">
            <div class="modal max-w-3xl">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="font-bold text-lg">📊 إنشاء حملة إعلانية</h3>
                    <button @click="showCampaignModal = false" class="text-slate-400 hover:text-white"><i class="fas fa-times"></i></button>
                </div>
                <div class="space-y-4">
                    <!-- Name -->
                    <div><label class="block text-sm text-slate-400 mb-1">📝 اسم الحملة</label><input x-model="cmpForm.name" class="input w-full" placeholder="مثال: حملة لعبة Aviator"></div>

                    <!-- Content Type Quick Insert -->
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">💬 نص الإعلان</label>
                        <div class="flex flex-wrap gap-2 mb-2">
                            <button @click="insertCampaignContent('promo')" class="px-3 py-1.5 rounded-lg text-xs bg-green-500/20 border border-green-500/30 text-green-300 hover:bg-green-500/30">🎁 عرض/برومو</button>
                            <button @click="insertCampaignContent('info')" class="px-3 py-1.5 rounded-lg text-xs bg-blue-500/20 border border-blue-500/30 text-blue-300 hover:bg-blue-500/30">📊 معلومة</button>
                            <button @click="insertCampaignContent('event')" class="px-3 py-1.5 rounded-lg text-xs bg-purple-500/20 border border-purple-500/30 text-purple-300 hover:bg-purple-500/30">🎉 حدث</button>
                            <button @click="insertCampaignContent('live')" class="px-3 py-1.5 rounded-lg text-xs bg-red-500/20 border border-red-500/30 text-red-300 hover:bg-red-500/30">🔴 مباشر</button>
                            <button @click="generateContent()" class="px-3 py-1.5 rounded-lg text-xs bg-purple-600/20 border border-purple-600/30 text-purple-400 hover:bg-purple-600 hover:text-white transition"><i class="fas fa-magic"></i> AI توليد</button>
                        </div>
                        <textarea x-model="cmpForm.message" rows="4" class="input w-full" placeholder="اكتب نص الإعلان هنا..."></textarea>
                        <div class="flex flex-wrap gap-1 mt-1">
                            <button @click="cmpForm.message += '{company_name}'" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{company_name}</button>
                            <button @click="cmpForm.message += '{download_link}'" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{download_link}</button>
                            <button @click="cmpForm.message += '{promo_code}'" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{promo_code}</button>
                            <button @click="cmpForm.message += '{affiliate_link}'" class="text-[10px] px-1.5 py-0.5 bg-slate-700 rounded hover:bg-slate-600">{affiliate_link}</button>
                        </div>
                    </div>

                    <!-- Media -->
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">📎 المرفقات</label>
                        <div class="flex flex-wrap gap-2">
                            <template x-for="(media, idx) in cmpForm.mediaList" :key="idx">
                                <div class="relative w-16 h-16 rounded-lg overflow-hidden bg-slate-700 border border-slate-600 group">
                                    <img x-show="media.type && media.type.startsWith('image')" :src="media.url" class="w-full h-full object-cover">
                                    <video x-show="media.type && media.type.startsWith('video')" :src="media.url" class="w-full h-full object-cover"></video>
                                    <div x-show="!media.type || (!media.type.startsWith('image') && !media.type.startsWith('video'))" class="w-full h-full flex items-center justify-center"><i class="fas fa-file text-xl text-slate-400"></i></div>
                                    <button @click="cmpForm.mediaList.splice(idx, 1)" class="absolute inset-0 bg-red-600/80 flex items-center justify-center opacity-0 group-hover:opacity-100 transition"><i class="fas fa-trash text-white"></i></button>
                                </div>
                            </template>
                            <label class="w-16 h-16 rounded-lg border-2 border-dashed border-slate-500 flex items-center justify-center cursor-pointer hover:border-green-500 transition" :class="cmpForm.uploading ? 'opacity-50 pointer-events-none' : ''">
                                <i class="fas fa-plus text-xl text-slate-400"></i>
                                <input type="file" class="hidden" accept="image/*,video/*" @change="uploadCampaignMedia($event)" multiple>
                            </label>
                        </div>
                    </div>

                    <!-- Platform + Recipient -->
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-sm text-slate-400 mb-1">🎯 المنصة</label>
                            <select x-model="cmpForm.target" class="input w-full">
                                <option value="telegram">📱 تيليغرام</option>
                                <option value="whatsapp">🟢 واتساب</option>
                                <option value="web">🌐 الموقع</option>
                                <option value="both">📱🌐 الاثنين</option>
                                <option value="all">📱🌐🟢 الكل</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm text-slate-400 mb-1">👥 الجمهور</label>
                            <select x-model="cmpForm.recipient" class="input w-full">
                                <option value="all">👥 الكل</option>
                                <option value="single">📱 قنوات محددة</option>
                                <option value="group">👥 مجموعة قنوات</option>
                            </select>
                        </div>
                    </div>

                    <!-- Dynamic: Telegram Channel Selector (when recipient=single) -->
                    <div x-show="cmpForm.recipient === 'single' && (cmpForm.target === 'telegram' || cmpForm.target === 'both' || cmpForm.target === 'all')" class="bg-slate-900/50 rounded-xl border border-slate-700 p-3">
                        <label class="block text-sm text-slate-400 mb-2">📢 اختر القنوات</label>
                        <div class="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-48 overflow-auto">
                            <template x-for="ch in channels" :key="ch.id">
                                <label class="flex items-center gap-2 p-2 rounded-lg cursor-pointer transition text-sm" :class="cmpForm.selectedChannels.includes(ch.id) ? 'bg-green-500/20 border border-green-500/30' : 'bg-slate-800 border border-transparent hover:border-slate-600'">
                                    <input type="checkbox" :value="ch.id" @change="toggleCampaignChannel(ch.id)" class="accent-green-500" :checked="cmpForm.selectedChannels.includes(ch.id)">
                                    <span x-text="ch.title || ch.chat_id"></span>
                                </label>
                            </template>
                        </div>
                        <div class="flex gap-2 mt-2">
                            <button @click="cmpForm.selectedChannels = channels.map(c => c.id)" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">اختيار الكل</button>
                            <button @click="cmpForm.selectedChannels = []" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">إلغاء الكل</button>
                            <span class="text-xs text-slate-500 self-center" x-text="(cmpForm.selectedChannels.length || 0) + ' محدد'"></span>
                        </div>
                    </div>

                    <!-- Dynamic: Group Selector (when recipient=group) -->
                    <div x-show="cmpForm.recipient === 'group'" class="bg-slate-900/50 rounded-xl border border-slate-700 p-3">
                        <label class="block text-sm text-slate-400 mb-2">👥 اختر المجموعات</label>
                        <div class="flex flex-wrap gap-2">
                            <template x-for="grp in groups" :key="grp.id">
                                <button @click="toggleCampaignGroup(grp)" class="px-3 py-1.5 rounded-lg text-sm transition" :class="cmpForm.selectedGroups.includes(grp.id) ? 'bg-purple-500/20 border border-purple-500/30 text-purple-300' : 'bg-slate-800 border border-slate-600 text-slate-400'" x-text="grp.name"></button>
                            </template>
                        </div>
                        <p x-show="groups.length === 0" class="text-xs text-slate-500 mt-2">لا توجد مجموعات — أنشئ مجموعة من تبويب المجموعات</p>
                    </div>

                    <!-- Dynamic: WhatsApp Options (when target=whatsapp) -->
                    <div x-show="cmpForm.target === 'whatsapp' || cmpForm.target === 'all'" class="bg-slate-900/50 rounded-xl border border-green-500/20 p-3 space-y-2">
                        <h4 class="text-sm font-bold text-green-400">🟢 إعدادات واتساب</h4>
                        <div>
                            <label class="block text-xs text-slate-400 mb-1">🔐 WhatsApp Business API</label>
                            <select x-model="cmpForm.platform_account_id" class="input text-sm w-full">
                                <option value="">— اختر حساب واتساب —</option>
                                <template x-for="acc in platformAccounts.filter(a => a.platform === 'whatsapp')" :key="acc.id">
                                    <option :value="acc.id" x-text="acc.account_name" :disabled="acc.is_active !== 'yes'"></option>
                                </template>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-400 mb-1">📱 جهات اتصال (مفصولة بفواصل)</label>
                            <input type="text" x-model="cmpForm.whatsappContacts" class="input text-sm w-full" placeholder="20111...,20122...,20133...">
                        </div>
                        <div>
                            <label class="block text-xs text-slate-400 mb-1">👥 مجموعات واتساب (مفصولة بفواصل)</label>
                            <input type="text" x-model="cmpForm.whatsappGroups" class="input text-sm w-full" placeholder="group_id_1,group_id_2">
                        </div>
                    </div>

                    <!-- Priority + Country + Repeat + Schedule -->
                    <div class="grid grid-cols-3 gap-3">
                        <div><label class="block text-sm text-slate-400 mb-1">⚡ الأولوية</label><select x-model="cmpForm.priority" class="input w-full"><option value="normal">🔔 عادية</option><option value="high">⚡ عالية</option><option value="urgent">🚨 عاجلة</option></select></div>
                        <div><label class="block text-sm text-slate-400 mb-1">🌍 الدولة</label><select x-model="cmpForm.country" class="input w-full"><option value="all">🌍 الكل</option><option value="EG">🇪🇬 مصر</option><option value="SA">🇸🇦 السعودية</option><option value="AE">🇦🇪 الإمارات</option><option value="JO">🇯🇴 الأردن</option><option value="MA">🇲🇦 المغرب</option><option value="DZ">🇩🇿 الجزائر</option></select></div>
                        <div><label class="block text-sm text-slate-400 mb-1">🔁 التكرار</label><select x-model="cmpForm.repeat" class="input w-full"><option value="once">مرة واحدة</option><option value="daily">يومي</option><option value="weekly">أسبوعي</option></select></div>
                    </div>
                    <div><label class="block text-sm text-slate-400 mb-1">⏰ الجدولة (اتركه فارغاً للإرسال فوراً)</label><input type="datetime-local" x-model="cmpForm.scheduled_at" class="input w-full"></div>
                </div>
                <div class="flex gap-2 justify-end mt-4">
                    <button @click="showCampaignModal = false" class="btn btn-sm" style="background:#475569">إلغاء</button>
                    <button @click="createCampaign()" class="btn btn-primary btn-sm" x-text="cmpForm.scheduled_at ? '⏰ جدولة الحملة' : '🚀 إطلاق فوراً'"></button>
                </div>
            </div>
        </div>"""

if old_modal_start in ch:
    ch = ch.replace(old_modal_start, new_modal, 1)
    print('OK: Campaign modal rewritten')
else:
    print('WARN: old modal not found — trying line-by-line')

# ========== 3. Add JS functions ==========
old_create = """        async createCampaign() {
            if (!this.cmpForm.name.trim()) return toast('اكتب اسم الحملة', 'warning');
            if (!this.cmpForm.message.trim() && this.cmpForm.mediaList.length === 0) return toast('اكتب نص أو ارفع ملف', 'warning');
            try {
                const payload = {
                    name: this.cmpForm.name, message: this.cmpForm.message,
                    media_urls: this.cmpForm.mediaList.map(m => m.url),
                    target: this.cmpForm.target, recipient: this.cmpForm.recipient,
                    priority: this.cmpForm.priority, country: this.cmpForm.country,
                    repeat: this.cmpForm.repeat, scheduled_at: this.cmpForm.scheduled_at,
                    platform_account_id: this.cmpForm.platform_account_id,
                };
                await api('/api/campaigns', { method: 'POST', body: JSON.stringify(payload) });
                toast(this.cmpForm.scheduled_at ? 'تمت جدولة الحملة' : 'تم إطلاق الحملة', 'success');
                this.showCampaignModal = false;
                this.cmpForm = { name: '', message: '', mediaList: [], target: 'both', recipient: 'all', priority: 'normal', country: 'all', repeat: 'once', scheduled_at: '', platform_account_id: '', uploading: false };
                await this.loadCampaigns();
            } catch(e) { toast('فشل', 'error'); }
        },"""

new_create = """        insertCampaignContent(type) {
            var t = {
                promo: '🎁 عرض خاص! استخدم كود {promo_code} واحصل على خصم حصري!\\n📱 حمّل التطبيق: {download_link}\\n🏢 {company_name}',
                info: '📊 معلومة اليوم: {stat_highlight}.\\n\\n📱 تابعنا: {download_link}\\n🏢 {company_name}',
                event: '🎉 حدث كبير قادم!\\n📅 الموعد: {event_date}\\n📱 سجّل الآن: {download_link}\\n🎁 كود: {promo_code}\\n🏢 {company_name}',
                live: '🔴 مباشر الآن! تابع الأحداث لحظة بلحظة.\\n📱 رابط البث المباشر: {download_link}\\n🏢 {company_name}',
            };
            this.cmpForm.message = (this.cmpForm.message || '') + '\\n' + (t[type] || '');
        },
        toggleCampaignChannel(id) {
            var idx = this.cmpForm.selectedChannels.indexOf(id);
            if (idx >= 0) this.cmpForm.selectedChannels.splice(idx, 1);
            else this.cmpForm.selectedChannels.push(id);
        },
        toggleCampaignGroup(grp) {
            var idx = this.cmpForm.selectedGroups.indexOf(grp.id);
            if (idx >= 0) { this.cmpForm.selectedGroups.splice(idx, 1); return; }
            this.cmpForm.selectedGroups.push(grp.id);
            var chIds = (grp.channel_ids || '').split('|').map(function(s){return s.trim()}).filter(Boolean);
            var self = this;
            chIds.forEach(function(cid) { if (self.cmpForm.selectedChannels.indexOf(cid) < 0) self.cmpForm.selectedChannels.push(cid); });
        },
        async createCampaign() {
            if (!this.cmpForm.name.trim()) return toast('اكتب اسم الحملة', 'warning');
            if (!this.cmpForm.message.trim() && this.cmpForm.mediaList.length === 0) return toast('اكتب نص أو ارفع ملف', 'warning');
            try {
                var payload = {
                    name: this.cmpForm.name, message: this.cmpForm.message,
                    media_urls: this.cmpForm.mediaList.map(function(m){return m.url}),
                    target: this.cmpForm.target, recipient: this.cmpForm.recipient,
                    priority: this.cmpForm.priority, country: this.cmpForm.country,
                    repeat: this.cmpForm.repeat, scheduled_at: this.cmpForm.scheduled_at,
                    platform_account_id: this.cmpForm.platform_account_id,
                    selectedChannels: this.cmpForm.selectedChannels,
                    selectedGroups: this.cmpForm.selectedGroups,
                    whatsappContacts: this.cmpForm.whatsappContacts,
                    whatsappGroups: this.cmpForm.whatsappGroups,
                };
                await api('/api/campaigns', { method: 'POST', body: JSON.stringify(payload) });
                toast(this.cmpForm.scheduled_at ? 'تمت جدولة الحملة' : 'تم إطلاق الحملة', 'success');
                this.showCampaignModal = false;
                this.cmpForm = { name: '', message: '', mediaList: [], target: 'telegram', recipient: 'all', priority: 'normal', country: 'all', repeat: 'once', scheduled_at: '', platform_account_id: '', uploading: false, selectedChannels: [], selectedGroups: [], whatsappApi: '', whatsappContacts: '', whatsappGroups: '' };
                await this.loadCampaigns();
            } catch(e) { toast('فشل', 'error'); }
        },"""

if old_create in ch:
    ch = ch.replace(old_create, new_create, 1)
    print('OK: Campaign JS functions updated')
else:
    print('WARN: createCampaign not found')

io.open(CH, 'w', encoding='utf-8').write(ch)
print(f'channels.html: {orig} -> {len(ch)} chars ({len(ch)-orig:+d})')
