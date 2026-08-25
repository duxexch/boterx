# -*- coding: utf-8 -*-
"""
Comprehensive fix for channels page issues:
1. Fix RTL toggle (add lang to channelsApp)
2. Improve channel card layout (compact, settings in modal)
3. Fix media_urls format in sendChannelMessage
4. Add archiving indicator
"""
import io

PATH = 'dashboard/templates/channels.html'
content = io.open(PATH, 'r', encoding='utf-8').read()
orig_len = len(content)

# ========== FIX 1: Add lang property to channelsApp ==========
old_data = "        tab: 'campaigns', channels: [], groups: [], vaultPosts: [], relayLogs: [],"
new_data = """        tab: 'campaigns', channels: [], groups: [], vaultPosts: [], relayLogs: [],
        lang: localStorage.getItem('lang') || 'ar',"""
if old_data in content:
    content = content.replace(old_data, new_data, 1)
    print('FIX 1 OK: lang property added')
else:
    print('FIX 1 SKIP: already has lang')

# ========== FIX 2: Fix toggleClasses - use CSS logical properties ==========
# The issue: in RTL, translate-x goes wrong direction because CSS transforms
# are physical. We need to flip the logic properly.
old_toggle = """        toggleClasses(isOn) {
            const isRtl = this.lang === 'ar';
            if (isRtl) {
                return isOn ? 'translate-x-1' : 'translate-x-6';
            }
            return isOn ? 'translate-x-6' : 'translate-x-1';
        },"""
new_toggle = """        toggleClasses(isOn) {
            // CSS translate-x is always physical (left-to-right).
            // LTR: dot on right when ON (translate-x-6), left when OFF (translate-x-1)
            // RTL: must mirror - dot on LEFT when ON, RIGHT when OFF
            const isRtl = (this.lang || 'ar') === 'ar';
            if (isRtl) {
                return isOn ? 'translate-x-[-20px]' : 'translate-x-0';
            }
            return isOn ? 'translate-x-6' : 'translate-x-1';
        },"""
if old_toggle in content:
    content = content.replace(old_toggle, new_toggle, 1)
    print('FIX 2 OK: toggleClasses fixed for RTL')
else:
    print('FIX 2 SKIP: toggleClasses not found')

# ========== FIX 3: Simplify channel card layout ==========
# Replace the huge settings block inside each card with a compact summary
old_card_body = """                    <div class="space-y-2 text-sm">
                        <div class="flex justify-between p-2 bg-slate-900/50 rounded">
                            <span class="text-slate-400">⚙️ تفعيل</span>
                            <button @click="toggleChannel(ch.id)" class="relative inline-flex h-6 w-11 items-center rounded-full transition" :class="ch.is_active === 'yes' ? 'bg-green-500' : 'bg-slate-600'"><span class="inline-block h-4 w-4 transform rounded-full bg-white transition" :class="toggleClasses(ch.is_active === 'yes')"></span></button>
                        </div>
                        <div class="flex justify-between p-2 bg-slate-900/50 rounded">
                            <span class="text-slate-400">👥 للمستخدمين</span>
                            <button @click="toggleSetting(ch, 'relay_to_users')" class="relative inline-flex h-6 w-11 items-center rounded-full transition" :class="ch.relay_to_users === 'yes' ? 'bg-green-500' : 'bg-slate-600'"><span class="inline-block h-4 w-4 transform rounded-full bg-white transition" :class="toggleClasses(ch.relay_to_users === 'yes')"></span></button>
                        </div>
                        <div class="flex justify-between p-2 bg-slate-900/50 rounded">
                            <span class="text-slate-400">📢 للقنوات</span>
                            <button @click="toggleSetting(ch, 'relay_to_channels')" class="relative inline-flex h-6 w-11 items-center rounded-full transition" :class="ch.relay_to_channels === 'yes' ? 'bg-green-500' : 'bg-slate-600'"><span class="inline-block h-4 w-4 transform rounded-full bg-white transition" :class="toggleClasses(ch.relay_to_channels === 'yes')"></span></button>
                        </div>
                        <div class="flex justify-between p-2 bg-slate-900/50 rounded">
                            <span class="text-slate-400">🤖 AI</span>
                            <button @click="toggleAI(ch.id)" class="relative inline-flex h-6 w-11 items-center rounded-full transition" :class="ch.ai_enabled === 'yes' ? 'bg-blue-500' : 'bg-slate-600'"><span class="inline-block h-4 w-4 transform rounded-full bg-white transition" :class="toggleClasses(ch.ai_enabled === 'yes')"></span></button>
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs text-slate-400 mb-1">🌐 المنصة</label>
                                <select x-model="ch.platform" @change="saveSetting(ch.id, 'platform', ch.platform)" class="input text-sm py-1 w-full">
                                    <option value="telegram">Telegram</option>
                                    <option value="whatsapp">WhatsApp</option>
                                    <option value="webhook">Webhook</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs text-slate-400 mb-1">🎭 الدور</label>
                                <select x-model="ch.channel_role" @change="saveSetting(ch.id, 'channel_role', ch.channel_role)" class="input text-sm py-1 w-full">
                                    <option value="both">Source + Publish</option>
                                    <option value="source">Source only</option>
                                    <option value="publish">Publish only</option>
                                </select>
                            </div>
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded grid grid-cols-1 gap-2">
                            <div>
                                <label class="block text-xs text-slate-400 mb-1">🤖 وكيل AI</label>
                                <select x-model="ch.ai_agent_id" @change="saveSetting(ch.id, 'ai_agent_id', ch.ai_agent_id)" class="input text-sm py-1 w-full">
                                    <option value="">— افتراضي —</option>
                                    <template x-for="agent in aiAgents" :key="agent.id">
                                        <option :value="agent.id" x-text="agent.name + ' (' + (agent.provider || 'auto') + ')'" :disabled="agent.is_active !== 'yes'"></option>
                                    </template>
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs text-slate-400 mb-1">🔐 حساب المنصة</label>
                                <select x-model="ch.platform_account_id" @change="saveSetting(ch.id, 'platform_account_id', ch.platform_account_id)" class="input text-sm py-1 w-full">
                                    <option value="">— تلقائي —</option>
                                    <template x-for="acc in platformAccounts" :key="acc.id">
                                        <option :value="acc.id" x-text="acc.account_name + ' (' + acc.platform + ')'" :disabled="acc.is_active !== 'yes'"></option>
                                    </template>
                                </select>
                            </div>
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">👤 Owner Admin ID</label>
                            <input type="text" x-model="ch.owner_admin_id" @change="saveSetting(ch.id, 'owner_admin_id', ch.owner_admin_id)" class="input text-sm py-1 w-full" placeholder="admin id">
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">👥 Manager Admin IDs (|)</label>
                            <input type="text" x-model="ch.managed_by_admin_ids" @change="saveSetting(ch.id, 'managed_by_admin_ids', ch.managed_by_admin_ids)" class="input text-sm py-1 w-full" placeholder="2|7|9">
                        </div>
                        <div class="flex justify-between p-2 bg-slate-900/50 rounded">
                            <span class="text-slate-400">🛡️ سماح نشر Subadmin</span>
                            <button @click="toggleSetting(ch, 'allow_subadmin_publish')" class="relative inline-flex h-6 w-11 items-center rounded-full transition" :class="ch.allow_subadmin_publish === 'yes' ? 'bg-amber-500' : 'bg-slate-600'"><span class="inline-block h-4 w-4 transform rounded-full bg-white transition" :class="ch.allow_subadmin_publish === 'yes' ? 'translate-x-6' : 'translate-x-1'"></span></button>
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded">
                            <label class="block text-xs text-slate-400 mb-1">📂 الفئة</label>
                            <select x-model="ch.category" @change="setCategory(ch.id, ch.category)" class="input text-sm py-1 w-full">
                                <option value="" data-i18n="uncategorized">Uncategorized</option>
                                <option value="رياضة">⚽ رياضة</option>
                                <option value="مال">💰 مال</option>
                                <option value="تداول">💱 تداول</option>
                                <option value="ألعاب">🎮 ألعاب</option>
                                <option value="أخبار">📰 أخبار</option>
                                <option value="تسويق">📣 تسويق</option>
                                <option value="ترفيه">🎬 ترفيه</option>
                                <option value="أخرى">📦 أخرى</option>
                            </select>
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded flex gap-2">
                            <input type="text" x-model="ch.postText" class="input text-sm py-1 flex-1" placeholder="📨 رسالة">
                            <button @click="postToChannel(ch)" class="btn btn-primary btn-sm" data-i18n="send">Send</button>
                        </div>
                    </div>"""

new_card_body = """                    <div class="space-y-2 text-sm">
                        <div class="flex items-center justify-between p-2 bg-slate-900/50 rounded">
                            <span class="text-slate-400">⚙️ تفعيل</span>
                            <button @click.stop="toggleChannel(ch.id)" class="relative inline-flex h-6 w-11 items-center rounded-full transition" :class="ch.is_active === 'yes' ? 'bg-green-500' : 'bg-slate-600'"><span class="inline-block h-4 w-4 transform rounded-full bg-white transition" :class="toggleClasses(ch.is_active === 'yes')"></span></button>
                        </div>
                        <div class="grid grid-cols-3 gap-1">
                            <span class="text-xs text-center p-1 rounded" :class="ch.relay_to_users === 'yes' ? 'bg-green-500/20 text-green-400' : 'bg-slate-700 text-slate-500'" @click.stop="toggleSetting(ch, 'relay_to_users')">👥 <span x-text="ch.relay_to_users === 'yes' ? 'ON' : 'OFF'"></span></span>
                            <span class="text-xs text-center p-1 rounded" :class="ch.relay_to_channels === 'yes' ? 'bg-green-500/20 text-green-400' : 'bg-slate-700 text-slate-500'" @click.stop="toggleSetting(ch, 'relay_to_channels')">📢 <span x-text="ch.relay_to_channels === 'yes' ? 'ON' : 'OFF'"></span></span>
                            <span class="text-xs text-center p-1 rounded" :class="ch.ai_enabled === 'yes' ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-700 text-slate-500'" @click.stop="toggleAI(ch.id)">🤖 <span x-text="ch.ai_enabled === 'yes' ? 'ON' : 'OFF'"></span></span>
                        </div>
                        <div class="p-2 bg-slate-900/50 rounded flex gap-2">
                            <input type="text" x-model="ch.postText" class="input text-sm py-1 flex-1" placeholder="📨 رسالة سريعة" @click.stop>
                            <button @click.stop="postToChannel(ch)" class="btn btn-primary btn-sm" data-i18n="send">Send</button>
                        </div>
                    </div>"""

if old_card_body in content:
    content = content.replace(old_card_body, new_card_body, 1)
    print('FIX 3 OK: Channel card simplified')
else:
    print('FIX 3 SKIP: card body not found')

# ========== FIX 4: Fix sendChannelMessage to extract URLs from media objects ==========
old_send = """        async sendChannelMessage() {
            if (!this.selectedChannel || !this.msgText) return toast('اكتب رسالة', 'warning');
            try {
                await api(`/api/channels/${this.selectedChannel.id}/post`, { method: 'POST', body: JSON.stringify({ 
                    message: this.msgText, 
                    media_urls: this.msgMedia || [] 
                }) });
                this.msgText = '';
                this.msgMedia = [];
                toast('تم الإرسال', 'success');
                await this.loadVault(); // refresh archive
            } catch(e) { toast('فشل الإرسال', 'error'); }
        },"""

new_send = """        async sendChannelMessage() {
            if (!this.selectedChannel) return;
            if (!this.msgText && (!this.msgMedia || this.msgMedia.length === 0)) return toast('اكتب رسالة أو أضف ملف', 'warning');
            try {
                const urls = (this.msgMedia || []).map(m => m.url || m).filter(Boolean);
                await api(`/api/channels/${this.selectedChannel.id}/post`, { method: 'POST', body: JSON.stringify({ 
                    message: this.msgText, 
                    media_urls: urls
                }) });
                this.msgText = '';
                this.msgMedia = [];
                toast('تم الإرسال — مؤرشفة في post_vault ✅', 'success');
                await this.loadVault();
            } catch(e) { toast('فشل الإرسال: ' + (e.message || ''), 'error'); }
        },"""

if old_send in content:
    content = content.replace(old_send, new_send, 1)
    print('FIX 4 OK: sendChannelMessage fixed')
else:
    print('FIX 4 SKIP: sendChannelMessage not found')

io.open(PATH, 'w', encoding='utf-8').write(content)
print(f'\nDone. {orig_len} -> {len(content)} chars ({len(content)-orig_len:+d})')
